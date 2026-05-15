import hashlib
import json
import logging

import httpx


def calculate_hash(data, exclude_keys=None):
    if not isinstance(data, dict):
        logging.error("Invalid data type for hashing. Expected a dictionary.")
        return None
    data_to_hash = data.copy()
    if exclude_keys:
        for key in exclude_keys:
            data_to_hash.pop(key, None)
    data_string = json.dumps(data_to_hash, sort_keys=True)
    return hashlib.sha256(data_string.encode("utf-8")).hexdigest()


def filter_event_fields(event_data, field_rules):
    if not isinstance(event_data, dict) or not isinstance(field_rules, dict):
        return event_data
    filtered_data = {}
    if "event" in event_data:
        filtered_data["event"] = event_data["event"]
    if "timestamp" in event_data:
        filtered_data["timestamp"] = event_data["timestamp"]
    for key, value in event_data.items():
        if key in filtered_data:
            continue
        if field_rules.get(key, False):
            filtered_data[key] = value
    return filtered_data


def parse_json_line(line):
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        logging.debug("Could not decode JSON from line: %s", line.strip())
        return None


def verify_api_key(api_key, api_url):
    if not api_key or not api_url:
        return False, "Missing API Key or URL"
    base_url = api_url.rstrip("/")
    verify_url = f"{base_url}/verify"
    try:
        response = httpx.get(verify_url, headers={"x-api-key": api_key}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("valid"):
                return True, data.get("commander")
            return False, "Key is invalid (Server rejected)"
        if response.status_code == 401:
            return False, "Invalid API Key"
        return False, f"Server Error: {response.status_code}"
    except Exception as e:
        logging.error("Verification failed: %s", e)
        return False, "Connection Error"
