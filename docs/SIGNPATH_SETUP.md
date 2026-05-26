# SignPath setup for SkyLink

> **Не используется.** Проект вернулся к неподписанным релизам (см. `.github/workflows/release.yml`). Документ оставлен для архива.

Follow these steps after merging the SignPath-related files into `Vist0ry/SkyLink`.

## 1. Prepare GitHub repository

- [ ] Public repo: `https://github.com/Vist0ry/SkyLink`
- [ ] `LICENSE` (MIT) present
- [ ] `SIGNPATH.md` and `PRIVACY.md` linked from README
- [ ] **Enable 2FA** on your GitHub account (required by SignPath)

## 2. Apply for free OSS signing

1. Open [SignPath Open Source](https://about.signpath.io/product/open-source)
2. Click **Apply for free**
3. Submit:
   - Repository: `https://github.com/Vist0ry/SkyLink`
   - Description: Windows telemetry agent for Elite Dangerous → SkyBioML squadron portal
   - Reason: remove SmartScreen / Unknown publisher warnings for GitHub downloads
   - Link to [SIGNPATH.md](../SIGNPATH.md) and [PRIVACY.md](../PRIVACY.md)

Wait for approval email from SignPath (may take several days).

## 3. Configure SignPath project

After approval, in SignPath.io:

1. Create project **SkyLink** (slug example: `SkyLink`)
2. **Repository URL:** `https://github.com/Vist0ry/SkyLink`
3. **Trusted build system:** link **GitHub.com**
4. **Artifact configuration:** import [.signpath/artifact-configurations/default.xml](../.signpath/artifact-configurations/default.xml) or create equivalent for `SkyLink.exe`
5. **Signing policy** `release-signing`:
   - Origin verification: enabled
   - Allowed branches/tags: `main` and release tags
   - Manual approval: recommended (you approve each release)

Create an API token with **submitter** permission for the signing policy.

## 4. GitHub repository variables and secrets

In GitHub → **Settings → Secrets and variables → Actions**:

### Secret

| Name | Value |
|------|--------|
| `SIGNPATH_API_TOKEN` | API token from SignPath |

### Variables

| Name | Example | Description |
|------|---------|-------------|
| `SIGNPATH_ORGANIZATION_ID` | *(from SignPath org settings)* | Enables the sign job |
| `SIGNPATH_PROJECT_SLUG` | `SkyLink` | Project slug in SignPath |
| `SIGNPATH_SIGNING_POLICY_SLUG` | `release-signing` | Policy slug |

Until `SIGNPATH_ORGANIZATION_ID` is set, the workflow builds and publishes **unsigned** `SkyLink.exe` (same as today).

## 5. Create a release

```bash
# bump version in config.py, README, gui.py first
git add .
git commit -m "Release 1.03"
git push origin main
git tag 1.03
git push origin 1.03
```

GitHub Actions (`.github/workflows/release.yml`):

1. Builds `SkyLink.exe` on `windows-latest`
2. Submits to SignPath (if configured)
3. Creates GitHub Release with `SkyLink.exe`

Auto-update in the client continues to work — it downloads `SkyLink.exe` from the latest release.

## 6. Verify signature

On a signed build:

```powershell
Get-AuthenticodeSignature dist\SkyLink.exe
```

Properties → **Digital Signatures** → publisher **SignPath Foundation**.

## Troubleshooting

| Problem | Check |
|---------|--------|
| Sign job skipped | Set `SIGNPATH_ORGANIZATION_ID` variable |
| SignPath rejects origin | Build must run on GitHub-hosted runner from tagged commit |
| Wrong product version | Tag name must match `config.py` `SOFTWARE_VERSION` |
| Build fails on `.env` | CI uses `.env.example` automatically via `build.py` |
