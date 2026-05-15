import base64
import logging
import threading

import httpx


class HeartbeatService(threading.Thread):
    _STATE_OK = "ok"

    def __init__(self, config, failed_accounts_ref):
        super().__init__(daemon=True)
        self.config = config
        self.failed_accounts = failed_accounts_ref
        self._stop_event = threading.Event()
        self._account_state = {}
        self._startup_logged = False

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            if not self.config.accounts:
                logging.debug("Heartbeat: no accounts configured, skipping beat.")
                self._stop_event.wait(30)
                continue
            all_ok_this_round = True
            for cmdr_name, api_key in self.config.accounts.items():
                if self._stop_event.is_set():
                    break
                prev = self._account_state.get(cmdr_name)
                try:
                    x_commander_value = base64.b64encode(cmdr_name.encode("utf-8")).decode("ascii")
                    headers = {
                        "x-api-key": api_key,
                        "x-commander": x_commander_value,
                        "User-Agent": self.config.USER_AGENT,
                    }
                    response = httpx.post(
                        self.config.HEARTBEAT_URL,
                        headers=headers,
                        timeout=5,
                    )
                    if response.status_code == 200:
                        self.failed_accounts.discard(cmdr_name)
                        self._account_state[cmdr_name] = self._STATE_OK
                        if prev is not None and prev != self._STATE_OK:
                            logging.info("Heartbeat restored for %s", cmdr_name)
                    elif response.status_code in (401, 403):
                        all_ok_this_round = False
                        self.failed_accounts.add(cmdr_name)
                        if prev != "auth_failed":
                            logging.warning(
                                "Heartbeat auth failed for %s: %s",
                                cmdr_name,
                                response.status_code,
                            )
                        self._account_state[cmdr_name] = "auth_failed"
                    else:
                        all_ok_this_round = False
                        if prev != "http_failed":
                            logging.warning(
                                "Heartbeat failed for %s: %s %s",
                                cmdr_name,
                                response.status_code,
                                response.text[:100] if response.text else "",
                            )
                        self._account_state[cmdr_name] = "http_failed"
                except httpx.RequestError as e:
                    all_ok_this_round = False
                    if prev != "network_failed":
                        logging.warning("Heartbeat network error for %s: %s", cmdr_name, e)
                    self._account_state[cmdr_name] = "network_failed"
            if all_ok_this_round and self.config.accounts and not self._startup_logged:
                n = len(self.config.accounts)
                logging.info("Heartbeat: running for %s account(s)", n)
                self._startup_logged = True
            self._stop_event.wait(30)
