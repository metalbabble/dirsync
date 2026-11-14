#!/usr/bin/env python3
"""
dirsync — Bidirectional directory synchronizer

Usage:
  python sync.py [DIR_A] [DIR_B] [--conflict {newest,ask}] [--include-hidden] [--once]

Examples:
  python sync.py ~/OneDrive/Music ~/iCloud/Music
  python sync.py /path/a /path/b --conflict ask
  python sync.py /path/a /path/b --include-hidden
"""

import sys
import os
import shutil
import time
import threading
import argparse
from pathlib import Path
from typing import Dict, Optional, Tuple
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── ANSI colors ──────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# ── Loop-prevention registry ──────────────────────────────────────────────────
# Paths we are currently writing/deleting ourselves; used to suppress
# the echoed filesystem event on the destination side.
_syncing: set[str] = set()
_syncing_lock = threading.Lock()

IGNORE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".Spotlight-V100",
                ".fseventsd", ".TemporaryItems", ".Trashes"}


def mark_syncing(path: str, duration: float = 2.0) -> None:
    """Register a path as one we own, auto-releasing after *duration* seconds."""
    with _syncing_lock:
        _syncing.add(path)

    def release():
        with _syncing_lock:
            _syncing.discard(path)

    threading.Timer(duration, release).start()


def is_syncing(path: str) -> bool:
    with _syncing_lock:
        return path in _syncing


# ── Logging ───────────────────────────────────────────────────────────────────
_log_lock = threading.Lock()


def log(action: str, rel_path, detail: str = "") -> None:
    ts = time.strftime("%H:%M:%S")
    palette = {
        "ADDED":    GREEN,
        "UPDATED":  CYAN,
        "REMOVED":  RED,
        "CONFLICT": YELLOW,
        "SKIPPED":  YELLOW,
    }
    color = palette.get(action, RESET)
    detail_str = f"  {DIM}{detail}{RESET}" if detail else ""
    with _log_lock:
        print(f"{DIM}[{ts}]{RESET} {color}{BOLD}{action:<10}{RESET} {rel_path}{detail_str}")


def fmt_time(mtime: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))


# ── Path helpers ──────────────────────────────────────────────────────────────
def is_hidden(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def should_ignore(rel: Path, include_hidden: bool) -> bool:
    if not include_hidden and is_hidden(rel):
        return True
    if rel.name in IGNORE_NAMES:
        return True
    return False


def safe_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))


# ── Initial sync ──────────────────────────────────────────────────────────────
def initial_sync(dir_a: Path, dir_b: Path, conflict: str, include_hidden: bool) -> None:
    print(f"\n{BOLD}Performing initial sync…{RESET}")

    def collect(base: Path) -> Dict[str, Path]:
        out: dict[str, Path] = {}
        for p in base.rglob("*"):
            if p.is_file():
                rel = p.relative_to(base)
                if not should_ignore(rel, include_hidden):
                    out[str(rel)] = p
        return out

    files_a = collect(dir_a)
    files_b = collect(dir_b)
    changed = 0

    for rel in sorted(set(files_a) | set(files_b)):
        in_a = rel in files_a
        in_b = rel in files_b

        if in_a and not in_b:
            safe_copy(files_a[rel], dir_b / rel)
            log("ADDED", rel, "A → B")
            changed += 1

        elif in_b and not in_a:
            safe_copy(files_b[rel], dir_a / rel)
            log("ADDED", rel, "B → A")
            changed += 1

        else:
            mtime_a = files_a[rel].stat().st_mtime
            mtime_b = files_b[rel].stat().st_mtime

            if abs(mtime_a - mtime_b) < 0.1:
                # Effectively identical — skip
                continue

            if conflict == "ask":
                newer_label = "A" if mtime_a > mtime_b else "B"
                log("CONFLICT", rel,
                    f"A modified {fmt_time(mtime_a)}  |  B modified {fmt_time(mtime_b)}  |  newer: {newer_label}")
                while True:
                    choice = input(
                        f"  Use [{BOLD}A{RESET}]={dir_a.name}  "
                        f"[{BOLD}B{RESET}]={dir_b.name}  "
                        f"[{BOLD}S{RESET}]kip? "
                    ).strip().upper()
                    if choice in ("A", "B", "S"):
                        break
                    print("  Please enter A, B, or S.")

                if choice == "A":
                    safe_copy(files_a[rel], dir_b / rel)
                    log("UPDATED", rel, "A → B")
                    changed += 1
                elif choice == "B":
                    safe_copy(files_b[rel], dir_a / rel)
                    log("UPDATED", rel, "B → A")
                    changed += 1
                else:
                    log("SKIPPED", rel)

            else:  # newest (default)
                if mtime_a > mtime_b:
                    safe_copy(files_a[rel], dir_b / rel)
                    log("UPDATED", rel, f"A → B  (A newer by {int(mtime_a - mtime_b)}s)")
                else:
                    safe_copy(files_b[rel], dir_a / rel)
                    log("UPDATED", rel, f"B → A  (B newer by {int(mtime_b - mtime_a)}s)")
                changed += 1

    if changed == 0:
        print(f"  {DIM}Directories already in sync.{RESET}")
    else:
        print(f"  {changed} file(s) synced.")
    print(f"{BOLD}Initial sync complete.{RESET}\n")


# ── Live sync handler ─────────────────────────────────────────────────────────
class SyncHandler(FileSystemEventHandler):
    def __init__(self, src_base: Path, dst_base: Path, include_hidden: bool) -> None:
        super().__init__()
        self.src_base = src_base
        self.dst_base = dst_base
        self.include_hidden = include_hidden

    def _rel(self, path: str) -> Optional[Path]:
        try:
            return Path(path).relative_to(self.src_base)
        except ValueError:
            return None

    def _eligible(self, path: str) -> Tuple[bool, Optional[Path]]:
        if is_syncing(path):
            return False, None
        rel = self._rel(path)
        if rel is None:
            return False, None
        if should_ignore(rel, self.include_hidden):
            return False, None
        return True, rel

    def _apply(self, src_path: str, operation: str) -> None:
        ok, rel = self._eligible(src_path)
        if not ok:
            return

        src = Path(src_path)
        dst = self.dst_base / rel

        def do() -> None:
            try:
                if operation in ("created", "modified"):
                    if src.is_dir():
                        mark_syncing(str(dst))
                        dst.mkdir(parents=True, exist_ok=True)
                    elif src.is_file():
                        mark_syncing(str(dst))
                        safe_copy(src, dst)
                        log("ADDED" if operation == "created" else "UPDATED", rel)

                elif operation == "deleted":
                    if dst.exists():
                        mark_syncing(str(dst))
                        if dst.is_dir():
                            shutil.rmtree(str(dst))
                        else:
                            dst.unlink()
                        log("REMOVED", rel)

            except Exception as exc:
                with _log_lock:
                    print(f"  {RED}Error syncing {rel}: {exc}{RESET}")

        threading.Thread(target=do, daemon=True).start()

    def on_created(self, event):
        self._apply(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory:
            self._apply(event.src_path, "modified")

    def on_deleted(self, event):
        self._apply(event.src_path, "deleted")

    def on_moved(self, event):
        self._apply(event.src_path, "deleted")
        self._apply(event.dest_path, "created")


# ── Input helpers ─────────────────────────────────────────────────────────────
def prompt_path(label: str) -> Path:
    while True:
        raw = input(f"Enter path for {label}: ").strip()
        path = Path(os.path.expanduser(raw)).resolve()
        if path.is_dir():
            return path
        print(f"  {RED}Directory not found:{RESET} {path}  — please try again.")


def resolve_dir(raw: str, label: str) -> Path:
    path = Path(os.path.expanduser(raw)).resolve()
    if not path.is_dir():
        print(f"{RED}Error:{RESET} directory not found for {label}: {path}")
        sys.exit(1)
    return path


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sync",
        description="Bidirectional directory sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("dir_a", nargs="?", help="First directory")
    parser.add_argument("dir_b", nargs="?", help="Second directory")
    parser.add_argument(
        "--conflict", "-c",
        choices=["newest", "ask"],
        default="newest",
        metavar="STRATEGY",
        help="How to resolve conflicts on startup: 'newest' (default) or 'ask'",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        default=False,
        help="Sync hidden files and directories (default: ignored)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Sync once and exit instead of watching for changes",
    )
    args = parser.parse_args()

    dir_a = resolve_dir(args.dir_a, "DIR_A") if args.dir_a else prompt_path("directory A")
    dir_b = resolve_dir(args.dir_b, "DIR_B") if args.dir_b else prompt_path("directory B")

    if dir_a == dir_b:
        print(f"{RED}Error:{RESET} Both paths resolve to the same directory.")
        sys.exit(1)

    print(f"\n{BOLD}dirsync{RESET}")
    print(f"  A: {dir_a}")
    print(f"  B: {dir_b}")
    print(f"  Conflict strategy : {args.conflict}")
    print(f"  Hidden files      : {'included' if args.include_hidden else 'ignored'}")

    initial_sync(dir_a, dir_b, args.conflict, args.include_hidden)

    if args.once:
        return

    observer = Observer()
    observer.schedule(SyncHandler(dir_a, dir_b, args.include_hidden), str(dir_a), recursive=True)
    observer.schedule(SyncHandler(dir_b, dir_a, args.include_hidden), str(dir_b), recursive=True)
    observer.start()

    print(f"Watching for changes. Press {BOLD}Ctrl+C{RESET} to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopping…{RESET}")
        observer.stop()
        observer.join()
        print("Sync stopped.")


if __name__ == "__main__":
    main()
