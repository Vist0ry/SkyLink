import logging
import time

from config import UI_STATE, Config
from heartbeat import HeartbeatService
from sender import FAILED_ACCOUNTS, Sender
from watcher import JournalWatcher

config = None
sender = None
watcher = None
heartbeat = None


def update_ui_state(status, message):
    UI_STATE["status"] = message or status
    msg = (message or "").lower()
    if (
        status
        and status.lower() == "error"
        and "auth error" in msg
        and ("401" in (message or "") or "403" in (message or ""))
    ):
        UI_STATE["request_show_window"] = True
    st_lower = status.lower()
    if "running" in st_lower or "sent" in st_lower or "monitoring" in st_lower:
        UI_STATE["color"] = "green"
    elif "error" in st_lower or "failed" in st_lower or "invalid" in st_lower:
        UI_STATE["color"] = "red"
    else:
        UI_STATE["color"] = "gray"


def start_background_service(shared_config=None):
    global sender, watcher, config, heartbeat

    logging.info("Starting SkyLink background service...")

    if shared_config:
        config = shared_config
    else:
        config = Config()

    cache_file = config.app_data_dir / "deduplication_cache.json"

    sender = Sender(cache_path=cache_file, config=config)
    sender.set_status_callback(update_ui_state)
    sender.start()

    if config.journal_path:
        watcher = JournalWatcher(
            journal_dir=config.journal_path, sender_instance=sender, config=config
        )
        watcher.start()
        logging.info("Journal watcher started.")
    else:
        logging.error("Could not find the Elite Dangerous journal directory. Watcher not started.")

    heartbeat = HeartbeatService(config, FAILED_ACCOUNTS)
    heartbeat.start()
    logging.info("Heartbeat service started.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_background_service()


def stop_background_service():
    global watcher, sender, heartbeat

    logging.info("Stopping SkyLink background service...")

    if heartbeat:
        heartbeat.stop()
        heartbeat.join(timeout=1.0)
    if watcher:
        watcher.stop()
    if sender:
        sender.stop()
    if sender:
        sender.join(timeout=1.0)

    logging.info("Background services stopped.")


if __name__ == "__main__":
    start_background_service()
