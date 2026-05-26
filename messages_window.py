"""SkyLink messages window — embedded portal chat via pywebview."""

from __future__ import annotations

import base64
import logging
import threading
import webbrowser

import httpx

try:
    import webview
except ImportError:
    webview = None  # type: ignore

_messages_window = None
_webview_thread: threading.Thread | None = None
_webview_lock = threading.Lock()


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
    if response.status_code == 403:
        raise RuntimeError(
            "Messages access denied on the portal. Enable MESSENGER permission for your rank."
        )
    response.raise_for_status()
    data = response.json()
    embed_url = data.get("embedUrl")
    if not embed_url:
        raise RuntimeError("Portal did not return embedUrl")
    return embed_url


def _show_error(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        logging.error("%s: %s", title, message)


def _webview_main(initial_url: str) -> None:
    global _messages_window
    try:
        _messages_window = webview.create_window(
            "SkyLink — Messages",
            initial_url,
            width=980,
            height=720,
            resizable=True,
            min_size=(640, 480),
        )
        webview.start()
    except Exception as e:
        logging.error("Messages webview loop ended: %s", e)
    finally:
        _messages_window = None


def _ensure_webview_thread(initial_url: str) -> None:
    global _webview_thread
    with _webview_lock:
        if _webview_thread is not None and _webview_thread.is_alive() and _messages_window is not None:
            try:
                _messages_window.load_url(initial_url)
                _messages_window.show()
                return
            except Exception as e:
                logging.warning("Messages reload failed, reopening window: %s", e)

        if _webview_thread is not None and _webview_thread.is_alive():
            logging.warning("Messages window busy; opening in browser")
            webbrowser.open(initial_url)
            return

        _webview_thread = threading.Thread(
            target=_webview_main,
            args=(initial_url,),
            name="SkyLinkMessagesWebView",
            daemon=True,
        )
        _webview_thread.start()


def open_messages_window(config) -> None:
    if webview is None:
        _show_error(
            "Messages",
            "pywebview is not installed. Reinstall SkyLink 2.0 or open Messages from the portal in a browser.",
        )
        return

    def _open():
        try:
            embed_url = fetch_chat_embed_url(config)
            _ensure_webview_thread(embed_url)
        except Exception as e:
            logging.error("Messages window error: %s", e)
            _show_error("SkyLink — Messages", str(e))

    threading.Thread(target=_open, daemon=True).start()
