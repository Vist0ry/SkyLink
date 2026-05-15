import logging
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from config import CURRENT_SESSION, EDDN_REQUIRED_EVENTS
from utils import parse_json_line

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

_TRAVEL_EVENTS = (
    'Location', 'Liftoff', 'Touchdown', 'SupercruiseEntry', 'SupercruiseExit',
    'FSDJump', 'Embark', 'Disembark', 'Docked', 'Undocked',
)


class JournalWatcher:

    def __init__(self, journal_dir, sender_instance, config):
        self.journal_dir = Path(journal_dir)
        self.sender = sender_instance
        self.config = config
        self.latest_log_file = None
        self.last_file_position = 0
        self.observer = Observer()

    def find_latest_log_file(self):
        log_files = list(self.journal_dir.glob('Journal.*.log'))
        if not log_files:
            logging.warning('No journal files found in the specified directory.')
            return None
        latest_file = max(log_files, key=lambda f: f.stat().st_mtime)
        logging.info(f'Monitoring latest journal file: {latest_file}')
        return latest_file

    def process_new_lines(self):
        if self.latest_log_file and self.latest_log_file.exists():
            with open(self.latest_log_file, 'r', encoding='utf-8') as f:
                f.seek(self.last_file_position)
                new_lines = f.readlines()
                self.last_file_position = f.tell()
                for line in new_lines:
                    self.process_line(line)

    def process_line(self, line):
        event_data = parse_json_line(line)
        if not event_data or 'event' not in event_data:
            return
        event_type = event_data['event']
        if event_type in ['Commander', 'LoadGame']:
            commander_name = event_data.get('Name') or event_data.get('Commander')
            if commander_name:
                self.update_session(commander_name)
            if event_type == 'LoadGame':
                CURRENT_SESSION['gameversion'] = event_data.get('gameversion') or ''
                CURRENT_SESSION['gamebuild'] = event_data.get('build') or ''
        if event_type in ('FSDJump', 'Location'):
            if event_data.get('StarSystem') is not None:
                CURRENT_SESSION['star_system'] = event_data.get('StarSystem') or ''
            if event_data.get('StarPos') is not None:
                star_pos = event_data.get('StarPos')
                CURRENT_SESSION['star_pos'] = star_pos if isinstance(star_pos, list) else []
        if event_type in ('Fileheader', 'LoadGame'):
            if 'Horizons' in event_data:
                CURRENT_SESSION['is_horizons'] = bool(event_data.get('Horizons'))
            if 'Odyssey' in event_data:
                CURRENT_SESSION['is_odyssey'] = bool(event_data.get('Odyssey'))
        if event_type in _TRAVEL_EVENTS:
            if 'Taxi' in event_data:
                CURRENT_SESSION['is_taxi'] = bool(event_data.get('Taxi'))
            if 'Multicrew' in event_data:
                CURRENT_SESSION['is_multicrew'] = bool(event_data.get('Multicrew'))
        rule = self.config.event_rules.get(event_type)
        if not rule:
            self.config.register_new_event(event_type)
            self.config.update_field_schema(event_type, event_data)
            action = 'ignore'
        else:
            action = rule.get('action', self.config.default_action)
        is_eddn = event_type in EDDN_REQUIRED_EVENTS
        should_queue = action == 'send' or is_eddn
        if should_queue:
            event_data['_send_to_portal'] = action == 'send'
            logging.info(f'Processing event: {event_type} (EDDN Required: {is_eddn})')
            self.sender.queue_event(event_data)
        else:
            logging.debug(f'Ignoring event based on rule or default action: {event_type}')

    def update_session(self, commander_name):
        if CURRENT_SESSION['commander'] == commander_name:
            return
        CURRENT_SESSION['commander'] = commander_name
        api_key = self.config.accounts.get(commander_name)
        if api_key:
            CURRENT_SESSION['api_key'] = api_key
            logging.info(f'Switched session to Commander: {commander_name}')
        else:
            CURRENT_SESSION['api_key'] = None
            logging.warning(
                f'No API Key found for Commander: {commander_name}. Events will not be sent.'
            )

    def _sync_session_from_file(self):
        if not self.latest_log_file or not self.latest_log_file.exists():
            return
        try:
            with open(self.latest_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    event_data = parse_json_line(line)
                    if not event_data or 'event' not in event_data:
                        continue
                    event_type = event_data['event']
                    if event_type in ['Commander', 'LoadGame']:
                        commander_name = event_data.get('Name') or event_data.get('Commander')
                        if commander_name:
                            self.update_session(commander_name)
                        if event_type == 'LoadGame':
                            CURRENT_SESSION['gameversion'] = event_data.get('gameversion') or ''
                            CURRENT_SESSION['gamebuild'] = event_data.get('build') or ''
                    if event_type in ('Fileheader', 'LoadGame'):
                        if 'Horizons' in event_data:
                            CURRENT_SESSION['is_horizons'] = bool(event_data.get('Horizons'))
                        if 'Odyssey' in event_data:
                            CURRENT_SESSION['is_odyssey'] = bool(event_data.get('Odyssey'))
                    if event_type in _TRAVEL_EVENTS:
                        if 'Taxi' in event_data:
                            CURRENT_SESSION['is_taxi'] = bool(event_data.get('Taxi'))
                        if 'Multicrew' in event_data:
                            CURRENT_SESSION['is_multicrew'] = bool(event_data.get('Multicrew'))
                    if event_type in ('FSDJump', 'Location'):
                        if event_data.get('StarSystem'):
                            CURRENT_SESSION['star_system'] = event_data.get('StarSystem')
                        if event_data.get('StarPos'):
                            val = event_data.get('StarPos')
                            CURRENT_SESSION['star_pos'] = val if isinstance(val, list) else []
        except (IOError, OSError) as e:
            logging.warning('Could not sync session from journal: %s', e)

    def start(self):
        self.latest_log_file = self.find_latest_log_file()
        if self.latest_log_file:
            self._sync_session_from_file()
            self.last_file_position = self.latest_log_file.stat().st_size
            event_handler = JournalFileHandler(self)
            self.observer.schedule(event_handler, str(self.journal_dir), recursive=False)
            self.observer.start()
            logging.info(f'Started watching directory: {self.journal_dir}')

    def stop(self):
        self.observer.stop()
        self.observer.join()
        logging.info('Journal watcher stopped.')


class JournalFileHandler(FileSystemEventHandler):

    def __init__(self, watcher):
        self.watcher = watcher

    def on_modified(self, event):
        if not event.is_directory and Path(event.src_path) == self.watcher.latest_log_file:
            self.watcher.process_new_lines()

    def on_created(self, event):
        if not event.is_directory and 'Journal' in Path(event.src_path).name:
            logging.info(f'New journal file detected: {event.src_path}')
            self.watcher.latest_log_file = Path(event.src_path)
            self.watcher.last_file_position = 0
            self.watcher.process_new_lines()
