# personal-automations

Small personal tools that live in one repo so they are easy to carry over to a
new Mac. Right now there are two tools:

- **news_bot** — fetches AI/crypto news and posts a Korean newsletter to Slack.
- **storage_optimizer** — finds reclaimable disk space from dev-tool caches
  (npm, yarn, Homebrew, Xcode, Android Studio, Docker, ...) and lets you clean
  only what you choose.

## Setup

```bash
git clone https://github.com/moonhee0507/personal-automations.git
cd personal-automations
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`news_bot` needs a `.env` file in the repo root with `GEMINI_API_KEY` and
`SLACK_WEBHOOK_URL`. `storage_optimizer` does not need any API key.

## storage_optimizer

All commands are run from the repo root, with the venv active
(`source venv/bin/activate`), or by calling `venv/bin/python` directly.

### 1. Scan (read-only, safe to run anytime)

```bash
python -m storage_optimizer.cli scan
```

This checks the size of each cache category, prints a table, saves the
result to `~/.personal-automations/storage_scan_latest.json`, and shows a
macOS notification with the total reclaimable size. It does **not** delete
anything.

### 2. Preview a cleanup (dry run)

```bash
python -m storage_optimizer.cli clean npm-cache --dry-run
```

Shows how much space a category would free, without touching any files.

### 3. Clean, picking items from a checklist

```bash
python -m storage_optimizer.cli clean --interactive
```

Shows a numbered list from the last scan. Type numbers separated by commas
(e.g. `1,3,5`), `all` for everything, or press Enter to cancel. Only the
items you pick get deleted.

### 4. Clean specific categories directly

```bash
python -m storage_optimizer.cli clean npm-cache yarn-cache
```

### Categories

| id | risk | what it is |
|---|---|---|
| `npm-cache` | safe | `~/.npm` |
| `yarn-cache` | safe | Yarn cache |
| `pnpm-store` | safe | pnpm content store |
| `homebrew-cache` | safe | Homebrew download cache |
| `pip-cache` | safe | pip cache |
| `cocoapods-cache` | safe | CocoaPods cache |
| `xcode-derived-data` | safe | Xcode build artifacts (rebuilt automatically) |
| `android-studio-old-cache` | safe | caches from Android Studio versions you no longer have installed |
| `docker-unused` | review | stopped containers, unused networks, dangling images, build cache |

"safe" means the owning tool rebuilds the cache automatically next time you
need it. "review" means check what it would remove before cleaning (you can
always run `--dry-run` first).

### Run it automatically every day (launchd)

```bash
./launchd/install.sh
```

This installs a launchd job that runs `scan` (never `clean`) every day at
09:00 and sends a notification with the total reclaimable size. It is safe
to re-run `install.sh` any time, including after moving the repo to a new
Mac — it fills in the correct paths for wherever the repo currently lives.

Useful commands:

```bash
launchctl list | grep storage-scan              # check it's loaded
launchctl start com.day.storage-scan             # trigger a scan right now
cat ~/Library/Logs/personal-automations/storage-scan.log       # output
cat ~/Library/Logs/personal-automations/storage-scan.err.log   # errors, if any
launchctl unload ~/Library/LaunchAgents/com.day.storage-scan.plist  # stop it
```

## Tests

```bash
python -m pytest -v
```

## Moving to a new Mac

```bash
git clone https://github.com/moonhee0507/personal-automations.git
cd personal-automations
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
./launchd/install.sh
```
