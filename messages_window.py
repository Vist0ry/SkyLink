"""SkyLink messages — opens portal chat in the default browser (no pywebview thread)."""

from __future__ import annotations

import base64
import logging
import threading
import webbrowser

import httpx


def _portal_base(config) -> str:
    api = (config.API_URL or "").rstrip("/")
    suffix = "/api/telemetry/skylink"
    if api.endswith(suffix):
        return api[: -len(suffix)]
    return getattr(config, "PORTAL_BASE", "https://skybioml.space").rstrip("/")


def _resolve_account(config) -> tuple[str | None, str | None]:
    """Saved API key is enough — journal / game session not required."""
    from config import CURRENT_SESSION

    session_cmdr = CURRENT_SESSION.get("commander")
    session_key = (CURRENT_SESSION.get("api_key") or "").strip()
    if session_cmdr and session_key:
        return session_cmdr, session_key

    accounts = getattr(config, "accounts", None) or {}
    for name, key in accounts.items():
        key_s = (key or "").strip()
        if key_s:
            return str(name), key_s

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
        raise RuntimeError(
            "Add an account with API key first (+ ADD ACCOUNT).\n"
            "Elite Dangerous does not need to be running."
        )

    base = _portal_base(config)
    url = f"{base}/api/auth/skylink-chat-token"
    response = httpx.post(url, headers=_auth_headers(config, cmdr, api_key), timeout=25)
    if response.status_code == 403:
        raise RuntimeError(
            "Messages access denied on the portal.\n"
            "Admin → Roles → MESSENGER: enable access for your rank."
        )
    if response.status_code == 401:
        raise RuntimeError("Invalid API key or commander. Use CHANGE API and save again.")
    response.raise_for_status()
    data = response.json()
    embed_url = data.get("embedUrl")
    if not embed_url:
        raise RuntimeError("Portal did not return embedUrl")
    logging.info("Messages token OK for %s, opening browser", cmdr)
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


def _show_info(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except Exception:
        logging.info("%s: %s", title, message)


def _open_chat(embed_url: str) -> None:
    webbrowser.open(embed_url)
    logging.info("Messages opened in browser")


def open_messages_window(config, gui_app=None) -> None:
    def worker():
        try:
            embed_url = fetch_chat_embed_url(config)

            def on_main():
                _open_chat(embed_url)
                _show_info(
                    "SkyLink — Messages",
                    "Chat opened in your browser.\n\n"
                    "Elite Dangerous is not required.\n"
                    "WAITING FOR SIGNAL only affects telemetry.",
                )

            if gui_app is not None and hasattr(gui_app, "after"):
                try:
                    if gui_app.winfo_exists():
                        gui_app.after(0, on_main)
                        return
                except Exception:
                    pass
            on_main()
        except Exception as e:
            logging.error("Messages error: %s", e)

            def on_err():
                _show_error("SkyLink — Messages", str(e))

            if gui_app is not None and hasattr(gui_app, "after"):
                try:
                    gui_app.after(0, on_err)
                    return
                except Exception:
                    pass
            on_err()

    threading.Thread(target=worker, daemon=True, name="SkyLinkMessagesFetch").start()
