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
