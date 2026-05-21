import logging
import os
import subprocess
import sys
import tempfile
from typing import Any, Callable, Optional

import httpx
from packaging.version import parse as parse_version

GITHUB_API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
SETUP_UPDATE_FILENAME = "SkyLink_Setup_Update.exe"
PORTABLE_UPDATE_FILENAME = "SkyLink_update.exe"
CREATE_NO_WINDOW = 0x08000000


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

    def find_update_asset(self, assets: list) -> tuple[Optional[str], bool]:
        setup_url = None
        portable_url = None
        for asset in assets:
            name = (asset.get("name") or "").lower()
            if not name.endswith(".exe"):
                continue
            url = asset.get("browser_download_url")
            if not url:
                continue
            if "setup" in name:
                setup_url = url
            elif name == "skylink.exe":
                portable_url = url
        if setup_url:
            return setup_url, False
        if portable_url:
            return portable_url, True
        return None, False

    def download_installer(
        self,
        url: str,
        portable: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        filename = PORTABLE_UPDATE_FILENAME if portable else SETUP_UPDATE_FILENAME
        path = os.path.join(tempfile.gettempdir(), filename)
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

    def run_update_and_exit(self, installer_path: str, portable: bool) -> None:
        if portable:
            self.apply_portable_update_and_exit(installer_path)
        else:
            self.run_setup_installer_and_exit(installer_path)

    def run_setup_installer_and_exit(self, installer_path: str) -> None:
        subprocess.Popen([installer_path])
        sys.exit(0)

    def apply_portable_update_and_exit(self, downloaded_path: str) -> None:
        if not getattr(sys, "frozen", False):
            subprocess.Popen([downloaded_path])
            sys.exit(0)
            return

        target = os.path.abspath(sys.executable)
        if not os.path.isfile(target):
            logging.error("Update failed: cannot resolve running executable path.")
            subprocess.Popen([downloaded_path])
            sys.exit(0)
            return

        pid = os.getpid()
        script_path = os.path.join(tempfile.gettempdir(), f"skylink_update_{pid}.ps1")
        target_ps = target.replace("'", "''")
        new_ps = os.path.abspath(downloaded_path).replace("'", "''")
        script = f"""
$Target = '{target_ps}'
$New = '{new_ps}'
$ProcId = {pid}
while (Get-Process -Id $ProcId -ErrorAction SilentlyContinue) {{
    Start-Sleep -Seconds 1
}}
$replaced = $false
for ($i = 0; $i -lt 30; $i++) {{
    try {{
        Copy-Item -LiteralPath $New -Destination $Target -Force
        $replaced = $true
        break
    }} catch {{
        Start-Sleep -Seconds 1
    }}
}}
if ($replaced) {{
    Start-Process -FilePath $Target
    Remove-Item -LiteralPath $New -Force -ErrorAction SilentlyContinue
}} else {{
    Start-Process -FilePath $New
}}
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script.strip())

        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    script_path,
                ],
                creationflags=CREATE_NO_WINDOW,
                close_fds=True,
            )
        except Exception as e:
            logging.error("Could not start update helper: %s", e)
            subprocess.Popen([downloaded_path])
        sys.exit(0)
