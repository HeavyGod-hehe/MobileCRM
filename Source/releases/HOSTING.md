# Hosting CRM updates

## 1. Bump the version

Edit `Source/VERSION` before each release (e.g. `2.4.0`).

## 2. Build customer packages

```bash
# Windows (on Windows)
python Source/build_customer_windows_copy.py

# Mac Intel
python Source/build_customer_mac.py --arch x86_64

# Mac Apple Silicon
python Source/build_customer_mac.py --arch arm64

# Mac Universal (both chips)
python Source/build_customer_mac.py --arch universal
```

## 3. Zip each deliverable

Customers receive folders like `Phone Reseller CRM/` (Windows) or `Phone Reseller CRM.app` (Mac).
Zip so the **top level inside the zip** is that folder name:

```
PhoneResellerCRM-Windows-2.4.0.zip
  └── Phone Reseller CRM/
        └── Phone Reseller CRM.exe
        └── …

PhoneResellerCRM-UniversalMac-2.4.0.zip
  └── Phone Reseller CRM.app/
        └── Contents/…
```

Do **not** zip the `Data/` folder — users keep their own data next to the app.

## 4. Publish `version.json`

Copy `version.json.example` to a public URL. Options:

| Host | How |
|------|-----|
| **GitHub raw** | Commit `Source/releases/version.json` on `main` and point `CRM_UPDATE_MANIFEST_URL` at the raw URL |
| **GitHub Releases** | Attach zips to a release; put the release asset URLs in `downloads` |
| **S3 / CDN** | Upload zips + `version.json`; use HTTPS URLs |

Example raw URL:

```
https://raw.githubusercontent.com/YOUR_ORG/YOUR_REPO/main/Source/releases/version.json
```

Set at runtime (optional):

```bash
export CRM_UPDATE_MANIFEST_URL="https://your-cdn.com/crm/version.json"
```

## 5. What the app does

1. Settings → **Software Update** calls `/api/update/check`
2. Compares manifest `version` with bundled `VERSION`
3. If newer and `can_auto_install`, user clicks **Install update**
4. App downloads the zip for `windows`, `mac_intel`, `mac_arm64`, or `mac_universal`
5. A helper script in `Data/Updates/` replaces the app after the CRM exits, then relaunches

## 6. Testing locally

1. Build a customer copy at version `2.3.0`
2. Host a test `version.json` with `2.4.0` and a zip URL you control
3. Set `CRM_UPDATE_MANIFEST_URL` to your test manifest
4. Run the frozen app → Settings → Install update

In development (`python launch_crm.py`), the UI shows update info but **Install** is disabled — only compiled builds can self-replace.
