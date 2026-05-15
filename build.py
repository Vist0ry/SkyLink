import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
SEP = os.pathsep


def main():
    args = [
        str(ROOT / "gui.py"),
        "--name=SkyLink",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--windowed",
        f"--icon={ROOT / 'assets' / 'icon.ico'}",
        f"--add-data={ROOT / 'events.json'}{SEP}.",
        f"--add-data={ROOT / '.env'}{SEP}.",
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
    ico = ROOT / "assets" / "icon.ico"
    if exe.is_file() and ico.is_file():
        try:
            from PyInstaller.utils.win32 import icon as win_icon

            win_icon.CopyIcons(str(exe), str(ico))
        except Exception as exc:
            print(f"Warning: could not re-apply icon to exe: {exc}")
    print(f"\nDone: {exe}")


if __name__ == "__main__":
    main()
    sys.exit(0)
