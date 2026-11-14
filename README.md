# dirsync

Bidirectional directory sync that watches two folders and keeps them in sync in real time. Useful for syncing folders between cloud drives (e.g. OneDrive ↔ iCloud).

## Install

Requires Python 3.9+.

```bash
pip3 install -r requirements.txt
```

## Usage

```bash
python3 sync.py [DIR_A] [DIR_B] [OPTIONS]
```

If you omit the directory paths, the app will prompt you for them.

### Options

| Flag | Values | Default | Description |
|---|---|---|---|
| `--conflict`, `-c` | `newest`, `ask` | `newest` | How to resolve conflicts on startup |
| `--include-hidden` | — | off | Sync hidden files and directories |
| `--once` | — | off | Sync once and exit instead of watching for changes |

### Examples

Important Note: these examples use Mac/Linux style conventions. For Windows, paths use backslashes e.g. c:\sample\path and likely would need to be launched using ```python sync.py```.

```bash
# Basic usage — auto-picks the newer file on conflict
python3 sync.py /path/a /path/b 

# Prompt for directories interactively
python3 sync.py

# Ask which version to keep when a conflict is found at startup
python3 sync.py /path/a /path/b --conflict ask

# Also sync hidden files (disabled by default)
python3 sync.py /path/a /path/b --include-hidden

# Reconcile once, then exit
python3 sync.py /path/a /path/b --once

# Example use case: syncing across OneDrive and iCloud
python3 sync.py ~/OneDrive/Music ~/Library/Mobile\ Documents/com\~apple\~CloudDocs/Music
```

## Behavior

### Startup sync
On launch, both directories are compared and brought into sync before watching begins:
- Files that exist on one side only are copied to the other.
- Files that differ on both sides are resolved using the `--conflict` strategy.

### Conflict strategies
- **`newest`** (default) — the file with the later modification time wins and is copied to the other side. The age difference is logged.
- **`ask`** — each conflict is shown with both modification times and you are prompted to choose side A, side B, or skip.

### Live sync
After the initial sync, both directories are watched for changes. Any add, edit, move, or delete is immediately mirrored to the other side.

### One-time sync
Pass `--once` to perform the startup sync and exit without watching for changes. This reconciles files that exist on either side and uses the selected conflict strategy for files that differ on both sides. It does not propagate deletions.

### Schedule a daily sync on macOS
Create a `launchd` LaunchAgent to run the script once each morning. The example below runs at 7:00 AM while you are logged in.

1. From the repository directory, create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

2. Create `~/Library/LaunchAgents/com.dirsync.daily.plist`, replacing the example paths with absolute paths on your Mac. Use the virtual environment's Python so it can find `watchdog`. Do not use `~` in the plist paths.

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.dirsync.daily</string>
       <key>ProgramArguments</key>
       <array>
           <string>/absolute/path/to/dirsync/.venv/bin/python</string>
           <string>/absolute/path/to/dirsync/sync.py</string>
           <string>/absolute/path/to/folder-a</string>
           <string>/absolute/path/to/folder-b</string>
           <string>--once</string>
       </array>
       <key>StartCalendarInterval</key>
       <dict>
           <key>Hour</key>
           <integer>7</integer>
           <key>Minute</key>
           <integer>0</integer>
       </dict>
       <key>StandardOutPath</key>
       <string>/tmp/dirsync.log</string>
       <key>StandardErrorPath</key>
       <string>/tmp/dirsync.err</string>
   </dict>
   </plist>
   ```

3. Load it for your user:

   ```bash
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dirsync.daily.plist
   ```

   To unload it later:

   ```bash
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.dirsync.daily.plist
   ```

LaunchAgents run in your logged-in user session, which is generally appropriate for syncing user folders such as iCloud Drive. If your Mac is asleep at the scheduled time, the job runs when it next becomes available; it does not wake the Mac. The logs in `/tmp/dirsync.log` and `/tmp/dirsync.err` can help diagnose failures.

### Hidden files
Files and directories whose names start with `.` are ignored by default, as are common OS noise files (`.DS_Store`, `Thumbs.db`, `desktop.ini`). Pass `--include-hidden` to sync dot-files too. OS noise files are always ignored regardless of this flag.

### Console output

```
[14:32:01] ADDED      album/track1.mp3  (A → B)
[14:32:01] UPDATED    album/track2.mp3  (A → B, A newer by 42s)
[14:32:05] REMOVED    old-track.mp3
[14:32:10] CONFLICT   notes.txt  A modified 2026-03-20 09:00:00  |  B modified 2026-03-21 11:30:00  |  newer: B
```

## Stop

Press `Ctrl+C` to stop watching.
