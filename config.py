import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

APP_NAME = "SkyLink"
SOFTWARE_VERSION = "2.0.4"
SOFTWARE_AUTHOR = "Vistory"
GITHUB_REPO = "Vist0ry/SkyLink"

DEFAULT_PORTAL_BASE = "https://skybioml.space"
DEFAULT_API_URL = f"{DEFAULT_PORTAL_BASE}/api/telemetry/skylink"
DEFAULT_HEARTBEAT_URL = f"{DEFAULT_PORTAL_BASE}/api/system/skylinkbeat"


def _load_env():
    if hasattr(sys, "_MEIPASS"):
        load_dotenv(os.path.join(sys._MEIPASS, ".env"))
    load_dotenv()


_load_env()

API_URL = os.getenv("SKYLINK_API_URL", DEFAULT_API_URL)
HEARTBEAT_URL = os.getenv("SKYLINK_HEARTBEAT_URL", DEFAULT_HEARTBEAT_URL)
USER_AGENT = f"SkyLink-Client/{SOFTWARE_VERSION}"

APPDATA_DIR = Path(os.getenv("APPDATA")) / "SkyLink"
APPDATA_DIR.mkdir(parents=True, exist_ok=True)

ACCOUNTS_FILE = APPDATA_DIR / "accounts.json"
DISCOVERY_FILE = APPDATA_DIR / "discovery.json"
SETTINGS_FILE = APPDATA_DIR / "settings.json"
LOG_FILE = APPDATA_DIR / "skylink_client.log"

log_handlers = [logging.StreamHandler(sys.stdout)]
try:
    log_handlers.append(
        RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8")
    )
except OSError as e:
    print(f"Warning: Could not set up file logging: {e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=log_handlers,
)

for _logger_name in ("httpx", "httpcore"):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)

CURRENT_SESSION = {
    "commander": None,
    "api_key": None,
    "gameversion": "",
    "gamebuild": "",
    "star_system": "",
    "star_pos": [],
    "is_horizons": False,
    "is_odyssey": False,
    "is_taxi": False,
    "is_multicrew": False,
}

UI_STATE = {"status": "WAITING", "color": "gray", "commander": None, "auth_required": False}

EDDN_REQUIRED_EVENTS = frozenset({"Scan", "FSDJump", "SAASignalsFound", "FSSBodySignals"})


def get_resource_path(relative_path):
    base_path = sys._MEIPASS if hasattr(sys, "_MEIPASS") else os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class Config:
    def __init__(self):
        self.app_data_dir = APPDATA_DIR
        self.accounts_file = ACCOUNTS_FILE
        self.discovery_file = DISCOVERY_FILE
        self.settings_file = SETTINGS_FILE

        self.disclaimer_accepted = False
        self.language = "en"
        self.last_accepted_version = ""

        self.event_rules = {}
        self.field_rules = {}
        self.accounts = {}
        self.discovered_fields = {}
        self.default_action = "send"

        self.load_internal_rules()
        self.load_accounts()
        self.load_discovered_fields()
        self.load_settings()

        self.API_URL = API_URL
        self.HEARTBEAT_URL = HEARTBEAT_URL
        self.USER_AGENT = USER_AGENT
        self.SOFTWARE_VERSION = SOFTWARE_VERSION
        self.SOFTWARE_AUTHOR = SOFTWARE_AUTHOR
        self.APP_NAME = APP_NAME
        self.PORTAL_BASE = DEFAULT_PORTAL_BASE
        self.GITHUB_REPO = GITHUB_REPO

        self.journal_path = self.get_saved_games_path()
        if not self.journal_path:
            logging.error("Could not find Elite Dangerous journal directory.")
        else:
            logging.info("Journal directory: %s", self.journal_path)

    def load_settings(self):
        if not self.settings_file.exists():
            return
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                content = f.read()
                if not content:
                    return
                data = json.loads(content)
            self.disclaimer_accepted = data.get("disclaimer_accepted", False)
            self.language = data.get("language", "en")
            self.last_accepted_version = data.get("accepted_version", "")
        except (OSError, json.JSONDecodeError) as e:
            logging.warning("Could not load settings: %s", e)

    def set_setting(self, key, value):
        data = {}
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content:
                        data = json.loads(content)
            except (OSError, json.JSONDecodeError):
                pass
        data[key] = value
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logging.warning("Could not save setting %s: %s", key, e)

    def save_disclaimer_state(self):
        self.set_setting("disclaimer_accepted", self.disclaimer_accepted)
        self.set_setting("language", self.language)

    def get_saved_games_path(self):
        try:
            path = Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
            if path.exists():
                return str(path)
            onedrive_path = (
                Path.home()
                / "OneDrive"
                / "Saved Games"
                / "Frontier Developments"
                / "Elite Dangerous"
            )
            if onedrive_path.exists():
                return str(onedrive_path)
            return None
        except OSError as e:
            logging.error("Error detecting Saved Games path: %s", e)
            return None

    def load_accounts(self):
        if not self.accounts_file.exists():
            self._save_json(self.accounts_file, {"accounts": {}})
            self.accounts = {}
            return
        try:
            with open(self.accounts_file, "r", encoding="utf-8") as f:
                content = f.read()
                data = json.loads(content) if content else {}
                self.accounts = data.get("accounts", {})
        except (OSError, json.JSONDecodeError) as e:
            logging.error("Failed to load accounts.json: %s", e)
            self.accounts = {}

    def save_account(self, commander_name, api_key):
        self.accounts[commander_name] = api_key
        CURRENT_SESSION["api_key"] = api_key
        self._save_json(self.accounts_file, {"accounts": self.accounts})
        logging.info("API key saved for: %s", commander_name)

    def delete_account(self, commander_name):
        if commander_name in self.accounts:
            del self.accounts[commander_name]
            self._save_json(self.accounts_file, {"accounts": self.accounts})

    def _save_json(self, filepath, data):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logging.error("Failed to save JSON to %s: %s", filepath, e)

    def load_internal_rules(self):
        internal_events_path = get_resource_path("events.json")
        try:
            with open(internal_events_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            self.flatten_event_rules(config_data)
        except FileNotFoundError:
            logging.error("events.json not found at %s", internal_events_path)
            self.event_rules = {}
            self.field_rules = {}
        except json.JSONDecodeError as e:
            logging.error("Failed to parse events.json: %s", e)
            self.event_rules = {}
            self.field_rules = {}

    def flatten_event_rules(self, config_data):
        self.event_rules = {}
        self.field_rules = {"filters": {}}
        self.default_action = config_data.get("settings", {}).get("default_action", "send")
        for category, events in config_data.get("categories", {}).items():
            for event_name, rule in events.items():
                self.event_rules[event_name] = {
                    "action": rule.get("action", "send"),
                    "deduplicate": rule.get("deduplicate", False),
                }
                self.field_rules["filters"][event_name] = {
                    key: value
                    for key, value in rule.items()
                    if key not in ["action", "deduplicate", "comment"]
                }

    def load_discovered_fields(self):
        if not self.discovery_file.exists():
            return
        try:
            with open(self.discovery_file, "r", encoding="utf-8") as f:
                content = f.read()
                self.discovered_fields = json.loads(content) if content else {}
        except (OSError, json.JSONDecodeError) as e:
            logging.error("Could not load discovery file: %s", e)
            self.discovered_fields = {}

    def register_new_event(self, event_type):
        if event_type in self.discovered_fields:
            return
        self.discovered_fields[event_type] = []
        self._save_json(self.discovery_file, self.discovered_fields)

    def update_field_schema(self, event_type, event_data):
        known_fields_with_metadata = self.field_rules.get("filters", {}).get(event_type, {})
        known_field_names = known_fields_with_metadata.keys()
        if event_type not in self.discovered_fields:
            self.discovered_fields[event_type] = []
        discovered_in_session = self.discovered_fields[event_type]
        updated = False
        for key in event_data.keys():
            if key not in known_field_names and key not in discovered_in_session:
                self.discovered_fields[event_type].append(key)
                updated = True
        if updated:
            self._save_json(self.discovery_file, self.discovered_fields)
