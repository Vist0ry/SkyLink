"""SkyLink messages window — embedded portal chat via pywebview."""

from __future__ import annotations

import base64
import logging
import threading
import time

import httpx

try:
    import webview
except ImportError:
    webview = None  # type: ignore

_loop_started = False
_loop_lock = threading.Lock()
_messages_window = None


def _portal_base(config) -> str:
    api = (config.API_URL or "").rstrip("/")
    suffix = "/api/telemetry/skylink"
    if api.endswith(suffix):
        return api[: -len(suffix)]
    return getattr(config, "PORTAL_BASE", "https://skybioml.space").rstrip("/")


def _resolve_account(config):
    from config import CURRENT_SESSION

    api_key = CURRENT_SESSION.get("api_key")
    cmdr = CURRENT_SESSION.get("commander")
    if api_key and cmdr:
        return cmdr, api_key
    if config.accounts:
        name, key = next(iter(config.accounts.items()))
        return name, key
    return None, None


def _auth_headers(config, cmdr: str, api_key: str) -> dict:
    encoded = base64.b64encode(cmdr.encode("utf-8")).decode("ascii")
    return {
        "x-api-key": api_key,
        "x-commander": encoded,
        "User-Agent": config.USER_AGENT,
    }


def fetch_chat_embed_url(config) -> str:
    cmdr, api_key = _resolve_account(config)
    if not cmdr or not api_key:
        raise RuntimeError("Add an account with a valid API key first.")

    base = _portal_base(config)
    url = f"{base}/api/auth/skylink-chat-token"
    response = httpx.post(url, headers=_auth_headers(config, cmdr, api_key), timeout=20)
    response.raise_for_status()
    data = response.json()
    embed_url = data.get("embedUrl")
    if not embed_url:
        raise RuntimeError("Portal did not return embedUrl")
    return embed_url


def _ensure_webview_loop() -> None:
    global _loop_started
    if webview is None:
        raise RuntimeError("pywebview is not installed")
    with _loop_lock:
        if _loop_started:
            return
        threading.Thread(target=lambda: webview.start(debug=False), daemon=True).start()
        _loop_started = True
        time.sleep(0.8)


def open_messages_window(config) -> None:
    global _messages_window

    def _open():
        global _messages_window
        try:
            embed_url = fetch_chat_embed_url(config)
            _ensure_webview_loop()

            if _messages_window is not None:
                try:
                    _messages_window.load_url(embed_url)
                    _messages_window.show()
                    return
                except Exception:
                    _messages_window = None

            if webview.windows:
                win = webview.windows[0]
                win.load_url(embed_url)
                win.show()
                _messages_window = win
                return

            _messages_window = webview.create_window(
                "SkyLink — Messages",
                embed_url,
                width=980,
                height=720,
                resizable=True,
                min_size=(640, 480),
            )
        except Exception as e:
            logging.error("Messages window error: %s", e)

    threading.Thread(target=_open, daemon=True).start()
