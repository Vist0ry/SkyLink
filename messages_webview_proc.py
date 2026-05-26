"""Child entry: pywebview must run on this process main thread (Windows)."""

from __future__ import annotations

import sys


def run_messages_webview(url: str) -> None:
    import webview

    webview.create_window(
        "SkyLink — Messages",
        url,
        width=980,
        height=720,
        resizable=True,
        min_size=(640, 480),
    )
    webview.start()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(2)
    run_messages_webview(sys.argv[1])
