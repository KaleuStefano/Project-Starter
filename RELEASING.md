# Releasing Project Starter

Builds are made by GitHub Actions (`.github/workflows/build.yml`) on a Windows and a macOS runner. You never need a Mac.

## Publish a new version

1. Bump the version in `src/oneclick/__init__.py` and `pyproject.toml` (one number, e.g. `2.3.0`).
2. Commit and push to `main`. The workflow runs the tests and builds both apps as a check.
3. Tag it and push the tag:
   ```
   git tag v2.3.0
   git push origin v2.3.0
   ```
4. In a few minutes a GitHub Release named `v2.3.0` appears with two assets:
   - `ProjectStarter-windows.exe`
   - `ProjectStarter-macos.zip` (Apple Silicon)
5. Edit the release notes on GitHub if you want, then link to the assets from your website.

## Stable download links for the website

These always point at the newest release, so the website never needs updating:

- Windows: `https://github.com/KaleuStefano/kal-motion/releases/latest/download/ProjectStarter-windows.exe`
- macOS:   `https://github.com/KaleuStefano/kal-motion/releases/latest/download/ProjectStarter-macos.zip`
- Release page: `https://github.com/KaleuStefano/kal-motion/releases/latest`

## What to tell users (first-run warnings)

The apps are not code-signed, so each OS warns once:

- **Windows (SmartScreen):** "Windows protected your PC" → *More info* → *Run anyway*.
- **macOS (Gatekeeper):** unzip, move `ProjectStarter.app` to Applications, then **right-click → Open → Open** the first time (double-clicking shows "can't be opened"). On newer macOS it may instead be *System Settings → Privacy & Security → Open Anyway*.
- **Intel Macs:** the CI build is Apple Silicon only. An Intel build needs `bash packaging/build_mac.sh` on an Intel Mac (or a second CI job on an Intel runner).

Signing would remove the warnings: a Microsoft-trusted code-signing certificate for Windows, and an Apple Developer account ($99/yr) with notarization for macOS. Both can be added to the workflow later without changing the app.

## Build locally instead

- Windows: `packaging\build_windows.bat` → `dist\ProjectStarter.exe`
- macOS: `bash packaging/build_mac.sh` → `dist/ProjectStarter.app`

## Checklist before tagging

- `python -m pytest` passes.
- Launch `python run.py`, create a test project, open Settings, open the template editor.
- Version bumped in both files.
