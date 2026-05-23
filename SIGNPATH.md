# Code signing policy

Free code signing for this project is provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

## Team roles

| Role | Responsibility | Members |
|------|----------------|---------|
| **Authors** | Maintain source code in the repository | [Vist0ry](https://github.com/Vist0ry) |
| **Reviewers** | Review pull requests before merge | [Vist0ry](https://github.com/Vist0ry) |
| **Approvers** | Approve SignPath signing requests for releases | [Vist0ry](https://github.com/Vist0ry) |

## What is signed

- `SkyLink.exe` — portable Windows build produced by GitHub Actions from tag releases on `main`.
- Binaries are built from this repository only (`Vist0ry/SkyLink`).

## What is not signed by this project

- Third-party Python/runtime libraries bundled by PyInstaller remain upstream components.
- Builds produced locally on a developer machine are **not** submitted to SignPath.

## Release process

1. Version bump in `config.py`, `README.md`, `gui.py`.
2. Push to `main`, create git tag (e.g. `1.03`).
3. GitHub Actions builds unsigned `SkyLink.exe`, submits it to SignPath, publishes the signed artifact to GitHub Releases.
4. Auto-update in the client downloads `SkyLink.exe` from GitHub Releases.

## Privacy

See [PRIVACY.md](PRIVACY.md).

This program does not transfer information to other networked systems unless specifically requested by the user or required for documented features (EDDN, squadron portal, update check).

## Setup (maintainers)

See [docs/SIGNPATH_SETUP.md](docs/SIGNPATH_SETUP.md).
