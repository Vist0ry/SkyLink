import logging
import os
import subprocess
import sys
import tempfile
from typing import Any, Callable, Optional

import httpx
from packaging.version import parse as parse_version

GITHUB_API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
UPDATE_FILENAME = "SkyLink_Setup_Update.exe"


class UpdateManager:
    def __init__(self, config):
        self.config = config

    def check_for_updates(self) -> Optional[dict[str, Any]]:
        url = GITHUB_API_LATEST.format(repo=self.config.GITHUB_REPO)
        headers = {"User-Agent": self.config.USER_AGENT}
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers)
            if response.status_code == 404:
                logging.debug(
                    "Update check: no releases in %s yet.",
                    self.config.GITHUB_REPO,
                )
                return None
            if response.status_code != 200:
                logging.debug("Update check: GitHub API returned %s", response.status_code)
                return None
            data = response.json()
        except (httpx.HTTPError, Exception) as e:
            logging.debug("Update check failed: %s", e)
            return None
        tag_name = data.get("tag_name") or ""
        tag_stripped = tag_name.lstrip("v")
        if not tag_stripped:
            return None
        try:
            remote_ver = parse_version(tag_stripped)
            local_ver = parse_version(self.config.SOFTWARE_VERSION)
        except Exception:
            return None
        if remote_ver <= local_ver:
            return None
        body = data.get("body") or ""
        return {"version": tag_stripped, "body": body, "assets": data.get("assets") or []}

    def find_installer_url(self, assets: list) -> Optional[str]:
        for asset in assets:
            name = (asset.get("name") or "").lower()
            if "setup" in name and name.endswith(".exe"):
                url = asset.get("browser_download_url")
                if url:
                    return url
        return None

    def download_installer(
        self, url: str, progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        path = os.path.join(tempfile.gettempdir(), UPDATE_FILENAME)
        headers = {"User-Agent": self.config.USER_AGENT}
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or 0)
                written = 0
                with open(path, "wb") as f:
                    for chunk in response.iter_bytes():
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)
                            if progress_callback and total:
                                progress_callback(written, total)
        return path

    def run_installer_and_exit(self, installer_path: str) -> None:
        subprocess.Popen([installer_path])
        sys.exit(0)
