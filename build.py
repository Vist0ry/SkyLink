import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
SEP = os.pathsep


def env_file_for_build() -> Path:
    override = os.getenv("SKYLINK_BUILD_ENV_FILE")
    if override:
        path = Path(override)
        if not path.is_file():
            raise SystemExit(f"SKYLINK_BUILD_ENV_FILE not found: {path}")
        return path
    env = ROOT / ".env"
    if env.is_file():
        return env
    example = ROOT / ".env.example"
    if example.is_file():
        return example
    raise SystemExit("Missing .env and .env.example — cannot bundle portal URLs into the build.")


def main():
    env_file = env_file_for_build()
    args = [
        str(ROOT / "gui.py"),
        "--name=SkyLink",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--windowed",
        f"--icon={ROOT / 'assets' / 'icon.ico'}",
        f"--add-data={ROOT / 'events.json'}{SEP}.",
        f"--add-data={env_file}{SEP}.env",
        "--collect-all=customtkinter",
        "--hidden-import=pystray",
        "--hidden-import=PIL",
        "--hidden-import=PIL._tkinter_finder",
    ]
    assets = ROOT / "assets"
    if assets.is_dir():
        args.append(f"--add-data={assets}{SEP}assets")
    PyInstaller.__main__.run(args)
    exe = ROOT / "dist" / "SkyLink.exe"
    print(f"\nDone: {exe}")


if __name__ == "__main__":
    main()
    sys.exit(0)
