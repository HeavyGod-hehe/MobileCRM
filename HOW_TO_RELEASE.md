# Easy updates — for you (the vendor)

You do **not** need to email new .exe / .app files anymore.

## One click (easiest)

**Double-click** `Release Everything.command` on your **Desktop** (or in the `Source` folder).

It automatically:
1. Pushes your code to GitHub
2. Starts the release build (Windows + all Mac types)
3. Rebuilds the app on your Desktop
4. Opens GitHub Actions so you can watch progress

For a **new** version number first, double-click and pass `--bump` from Terminal, or edit `Source/VERSION` yourself.

## Your 3-step routine (manual)

1. **Edit one file** — open `Source/VERSION` and change the number  
   Example: `2.3.0` → `2.4.0`

2. **Push to GitHub**
   ```bash
   git add Source/VERSION
   git commit -m "Release 2.4.0"
   git push
   ```

3. **Wait ~15 minutes** — GitHub automatically:
   - Builds Windows + Mac apps
   - Uploads them to **Releases**
   - Updates `version.json` so customer apps see the update

That’s it.

## What your customers see

- Open CRM → **Settings → Software Update**
- If a newer version exists: **Install update** (one click)
- Their **Data** folder (shop database) is **not** deleted

Apps also show a yellow banner at the top when an update is ready.

## Manual release (optional)

GitHub → **Actions** → **Release CRM Update** → **Run workflow**

Use this if you only want to rebuild without changing `VERSION`.

## First-time setup (once)

Make sure your repo is public (or customers cannot download updates without login).

After your first successful release, check:
https://github.com/HeavyGod-hehe/MobileCRM/releases

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Customers don’t see update | Did you bump `Source/VERSION` and push? |
| Install fails | Run release workflow again on GitHub Actions |
| macOS blocks app | `xattr -cr "Phone Reseller CRM.app"` |
