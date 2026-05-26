"""SkyLink messages — portal chat (browser; optional embedded webview on main thread)."""

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
_webview_started = False


def _portal_base(config) -> str:
    api = (config.API_URL or "").rstrip("/")
    suffix = "/api/telemetry/skylink"
    if api.endswith(suffix):
        return api[: -len(suffix)]
    return getattr(config, "PORTAL_BASE", "https://skybioml.space").rstrip("/")


def _resolve_account(config) -> tuple[str | None, str | None]:
    """Saved API key is enough — Elite Dangerous / journal not required."""
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
            "You do not need to run Elite Dangerous for Messages."
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
        raise RuntimeError("Invalid API key or commander name. Update key via CHANGE API.")
    response.raise_for_status()
    data = response.json()
    embed_url = data.get("embedUrl")
    if not embed_url:
        raise RuntimeError("Portal did not return embedUrl")
    logging.info("Messages embed for %s", cmdr)
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


def _open_in_browser(embed_url: str) -> None:
    webbrowser.open(embed_url)


def _try_embedded_webview(embed_url: str, gui_app) -> bool:
    """Optional second window; may fail on some Windows setups."""
    global _messages_window, _webview_started
    if webview is None:
        return False

    def run():
        global _messages_window, _webview_started
        try:
            if _messages_window is not None:
                try:
                    _messages_window.load_url(embed_url)
                    _messages_window.show()
                    return
                except Exception:
                    _messages_window = None

            _messages_window = webview.create_window(
                "SkyLink — Messages",
                embed_url,
                width=980,
                height=720,
                resizable=True,
                min_size=(640, 480),
            )
            _webview_started = True
            webview.start()
        except Exception as e:
            logging.error("Embedded Messages webview failed: %s", e)
        finally:
            _messages_window = None
            _webview_started = False

    if _webview_started:
        return False

    try:
        threading.Thread(target=run, daemon=True, name="SkyLinkMessagesWebView").start()
        return True
    except Exception:
        return False


def _deliver_url(config, embed_url: str, gui_app, use_embedded: bool) -> None:
    _open_in_browser(embed_url)
    _show_info(
        "SkyLink — Messages",
        "Chat opened in your browser.\n\n"
        "Elite Dangerous does not need to be running.\n"
        "WAITING FOR SIGNAL only affects telemetry.",
    )
    if use_embedded:
        _try_embedded_webview(embed_url, gui_app)


def open_messages_window(config, gui_app=None, prefer_embedded: bool = False) -> None:
    def worker():
        try:
            embed_url = fetch_chat_embed_url(config)
            if gui_app is not None and hasattr(gui_app, "after"):
                try:
                    if gui_app.winfo_exists():
                        gui_app.after(
                            0,
                            lambda: _deliver_url(config, embed_url, gui_app, prefer_embedded),
                        )
                        return
                except Exception:
                    pass
            _deliver_url(config, embed_url, gui_app, prefer_embedded)
        except Exception as e:
            logging.error("Messages window error: %s", e)
            if gui_app is not None and hasattr(gui_app, "after"):
                try:
                    gui_app.after(0, lambda: _show_error("SkyLink — Messages", str(e)))
                    return
                except Exception:
                    pass
            _show_error("SkyLink — Messages", str(e))

    threading.Thread(target=worker, daemon=True, name="SkyLinkMessagesFetch").start()
