import os
import sys
from pathlib import Path

import PyInstaller.__main__

from config import SOFTWARE_AUTHOR, SOFTWARE_VERSION

ROOT = Path(__file__).resolve().parent
SEP = os.pathsep
VERSION_INFO_PATH = ROOT / "build" / "version_info.txt"


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


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in version.split(".") if p.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def write_version_info(path: Path, version: str, company: str) -> Path:
    filevers = version_tuple(version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers},
    prodvers={filevers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'{company}'),
        StringStruct(u'FileDescription', u'SkyLink Agent'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'SkyLink'),
        StringStruct(u'LegalCopyright', u'Copyright (c) {company}'),
        StringStruct(u'OriginalFilename', u'SkyLink.exe'),
        StringStruct(u'ProductName', u'SkyLink'),
        StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return path


def main():
    env_file = env_file_for_build()
    version_file = write_version_info(VERSION_INFO_PATH, SOFTWARE_VERSION, SOFTWARE_AUTHOR)
    args = [
        str(ROOT / "gui.py"),
        "--name=SkyLink",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--windowed",
        f"--version-file={version_file}",
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
