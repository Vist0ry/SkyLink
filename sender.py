import asyncio
import base64
import hashlib
import json
import logging
import os
import queue
import threading
import time

import httpx

from config import CURRENT_SESSION, EDDN_REQUIRED_EVENTS
from utils import filter_event_fields

FAILED_ACCOUNTS = set()
OFFLINE_QUEUE_TIMEOUT_SEC = 120
OFFLINE_RETRY_PAUSE_SEC = 10

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class Sender(threading.Thread):
    def __init__(self, cache_path, config):
        super().__init__(daemon=True)
        self.cache_path = cache_path
        self.config = config
        self.event_queue = queue.Queue()
        self.offline_queue = queue.Queue()
        self.hashes = {}
        self.load_hashes()
        self.stop_event = threading.Event()
        self.status_callback = None

    def load_hashes(self):
        marker = self.cache_path.parent / '.clear_dedup_cache'
        if marker.exists():
            try:
                if self.cache_path.exists():
                    self.cache_path.unlink()
                marker.unlink()
                logging.info('Deduplication cache cleared after install/reinstall.')
            except OSError as e:
                logging.warning('Could not clear dedup cache marker: %s', e)
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r') as f:
                    content = f.read()
                    if not content:
                        self.hashes = {}
                    else:
                        self.hashes = json.loads(content)
                        logging.info(
                            'Deduplication cache loaded from: %s',
                            os.path.abspath(self.cache_path),
                        )
            except (json.JSONDecodeError, IOError) as e:
                logging.error('Failed to load deduplication cache: %s', e)
                self.hashes = {}
        else:
            logging.info('Cache file not found. Creating a new one.')
            self.hashes = {}
            self.save_hashes()

    def save_hashes(self):
        abs_path = os.path.abspath(self.cache_path)
        logging.info('Saving cache to: %s', abs_path)
        try:
            with open(self.cache_path, 'w') as f:
                json.dump(self.hashes, f, indent=2)
        except IOError as e:
            logging.error('Failed to save deduplication cache: %s', e)

    def set_status_callback(self, callback):
        self.status_callback = callback

    def update_status(self, status, message):
        if self.status_callback:
            self.status_callback(status, message)
        logging.info('Status: %s - %s', status, message)

    @staticmethod
    def _find_key_insensitive(target_name, accounts_dict):
        if target_name is None:
            return None
        if target_name in accounts_dict:
            return accounts_dict[target_name]
        target_lower = target_name.lower()
        for name, key in accounts_dict.items():
            if name.lower() == target_lower:
                return key
        return None

    def _resolve_api_key(self, commander_name):
        api_key = CURRENT_SESSION.get('api_key')
        if api_key:
            return api_key
        api_key = self._find_key_insensitive(commander_name, self.config.accounts)
        if api_key:
            return api_key
        self.config.load_accounts()
        api_key = self._find_key_insensitive(commander_name, self.config.accounts)
        if api_key:
            CURRENT_SESSION['api_key'] = api_key
            logging.info('Key loaded from disk for: %s', commander_name)
            return api_key
        return None

    @staticmethod
    def purge_commander_cache(commander_name, cache_path):
        if not cache_path.exists():
            return
        try:
            with open(cache_path, 'r') as f:
                content = f.read()
                if not content:
                    hashes = {}
                else:
                    hashes = json.loads(content)
        except (IOError, json.JSONDecodeError):
            return
        keys_to_delete = [key for key in hashes if key.startswith(f'{commander_name}|')]
        if not keys_to_delete:
            return
        for key in keys_to_delete:
            del hashes[key]
        try:
            with open(cache_path, 'w') as f:
                json.dump(hashes, f, indent=2)
            logging.info('Cache purged for commander: %s', commander_name)
        except IOError:
            logging.error('Failed to save purged cache for commander: %s', commander_name)

    def queue_event(self, event):
        self.event_queue.put(event)

    def run(self):
        asyncio.run(self._worker())

    async def _worker(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            while not self.stop_event.is_set():
                try:
                    event = await asyncio.to_thread(self.event_queue.get, timeout=1)
                except queue.Empty:
                    await self.retry_offline_queue(client)
                    continue
                if event:
                    await self.process_event(event, client)

    def stop(self):
        self.stop_event.set()

    async def process_event(self, event, client):
        send_to_portal = event.pop('_send_to_portal', False)
        event_type = event.get('event')
        if not event_type:
            return
        if event.get('CarrierType') == 'SquadronCarrier':
            return
        eddn_ok = False
        if event_type in EDDN_REQUIRED_EVENTS:
            try:
                from src.services.eddn_sender import send_to_eddn
                eddn_ok = await send_to_eddn(client, event, game_state=CURRENT_SESSION)
            except Exception as e:
                logging.warning('EDDN send failed: %s', e)
                eddn_ok = False
        if send_to_portal:
            self.config.update_field_schema(event_type, event)
            field_rules = self.config.field_rules.get('filters', {}).get(event_type, {})
            filtered_event = filter_event_fields(event, field_rules)
            commander_name = CURRENT_SESSION.get('commander', 'Unknown')
            api_key = self._resolve_api_key(commander_name)
            rule = self.config.event_rules.get(event_type)
            cache_key = None
            if rule and rule.get('deduplicate'):
                cache_key = f'{commander_name}|{event_type}'
                if api_key:
                    content_to_hash = filtered_event.copy()
                    content_to_hash.pop('timestamp', None)
                    content_to_hash.pop('event', None)
                    content_str = f'{commander_name}|{json.dumps(content_to_hash, sort_keys=True)}'
                    event_hash = hashlib.sha256(content_str.encode('utf-8')).hexdigest()
                    if self.hashes.get(cache_key) == event_hash:
                        logging.info(
                            'Skipping duplicate event for %s: %s',
                            commander_name,
                            event_type,
                        )
                        return
                    self.hashes[cache_key] = event_hash
            if event_type in EDDN_REQUIRED_EVENTS:
                filtered_event['eddnsent'] = eddn_ok
            success, queue_on_failure = await self._send_to_api(client, filtered_event)
            if not success and cache_key is not None and cache_key in self.hashes:
                self.hashes.pop(cache_key)
                self.save_hashes()
            elif success and cache_key is not None and cache_key in self.hashes:
                self.save_hashes()
            if not success and queue_on_failure:
                self.offline_queue.put((filtered_event, time.time()))

    def _log_event_details(self, event):
        event_type = event.get('event')
        if event_type == 'Location':
            docked_status = 'Docked: True' if event.get('Docked', False) else 'Docked: False'
            logging.info(
                "[>] Location: %s (%s)",
                event.get('StarSystem', 'N/A'),
                docked_status,
            )
        elif event_type == 'Loadout':
            jump_range = event.get('MaxJumpRange', 0)
            logging.info(
                "[>] Loadout: %s (Jump: %.2f ly)",
                event.get('Ship', 'N/A'),
                jump_range,
            )
        elif event_type == 'Materials':
            raw_count = len(event.get('Raw', []))
            encoded_count = len(event.get('Encoded', []))
            logging.info(
                '[>] Materials: Updated (Raw: %s, Encoded: %s)',
                raw_count,
                encoded_count,
            )
        else:
            logging.info('Successfully sent event: %s', event_type)

    async def _send_to_api(self, client, event):
        cmdr_name = CURRENT_SESSION.get('commander') or 'Unknown'
        api_key = CURRENT_SESSION.get('api_key')
        if not api_key:
            api_key = self._find_key_insensitive(cmdr_name, self.config.accounts)
            if not api_key:
                self.config.load_accounts()
                api_key = self._find_key_insensitive(cmdr_name, self.config.accounts)
                if api_key:
                    CURRENT_SESSION['api_key'] = api_key
                    logging.info('Key loaded from disk for: %s', cmdr_name)
        if not api_key:
            logging.warning('Cannot send event: No active API Key for commander %s', cmdr_name)
            return (False, False)
        if not self.config.API_URL:
            logging.error('API URL is not configured. Cannot send event.')
            return (False, False)
        x_commander_value = base64.b64encode(cmdr_name.encode('utf-8')).decode('ascii')
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': self.config.USER_AGENT,
            'x-api-key': api_key,
            'x-commander': x_commander_value,
        }
        try:
            response = await client.post(self.config.API_URL, headers=headers, json=event)
            if response.status_code == 200:
                self._log_event_details(event)
                event_type = event.get('event')
                if event_type == 'Shutdown':
                    logging.info('Game Shutdown detected. Switching to standby.')
                    self.update_status('Waiting', 'Game closed. Waiting for Commander...')
                else:
                    event_type = event.get('event', 'Event')
                    self.update_status('Running', f'Event {event_type} sent')
                FAILED_ACCOUNTS.discard(cmdr_name)
                return (True, False)
            if response.status_code == 429:
                retry_after = 60
                raw = response.headers.get('Retry-After')
                if raw is not None:
                    try:
                        retry_after = int(raw)
                    except ValueError:
                        pass
                logging.warning('Rate limited (429). Sleeping %s s (Retry-After).', retry_after)
                await asyncio.sleep(retry_after)
                return (False, True)
            if response.status_code in [401, 403]:
                logging.error('Auth failed for %s (Status: %s)', cmdr_name, response.status_code)
                FAILED_ACCOUNTS.add(cmdr_name)
                self.update_status('Error', f'Auth Error {response.status_code} for {cmdr_name}')
                return (False, False)
            logging.error('Failed to send event: %s - %s', response.status_code, response.text)
            self.update_status('Error', 'Failed to send event, queuing.')
            return (False, True)
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logging.error('Network error while sending event: %s', e)
            self.update_status('Error', 'Network error, queuing event.')
            return (False, True)
        except Exception:
            logging.exception('Unexpected error in _send_to_api')
            return (False, True)

    async def retry_offline_queue(self, client):
        if self.offline_queue.empty():
            return
        logging.info('Retrying %s events from the offline queue.', self.offline_queue.qsize())
        while not self.offline_queue.empty():
            item = self.offline_queue.get()
            if isinstance(item, tuple):
                event, first_queued = item
            else:
                event, first_queued = (item, time.time())
            if time.time() - first_queued > OFFLINE_QUEUE_TIMEOUT_SEC:
                logging.warning(
                    'Dropping event %s after %ss timeout.',
                    event.get('event', '?'),
                    OFFLINE_QUEUE_TIMEOUT_SEC,
                )
                continue
            success, queue_on_failure = await self._send_to_api(client, event)
            if not success and queue_on_failure:
                self.offline_queue.put((event, first_queued))
        if self.offline_queue.qsize() > 0:
            await asyncio.sleep(OFFLINE_RETRY_PAUSE_SEC)
        else:
            self.update_status('Running', 'Offline queue cleared.')
