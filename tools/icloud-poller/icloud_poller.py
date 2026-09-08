#!/usr/bin/env python3
"""TouchGrass path-backed iCloud Photos poller for Windows.

The poller never edits, moves, pins, unpins, or deletes files in iCloud Photos.
It sends only metadata and relative paths to TouchGrass.
"""

import argparse
import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import urllib.parse


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "TouchGrass" / "iCloudPoller"
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "poller.sqlite3"
LOCK_PATH = APP_DIR / "poller.lock"
PID_PATH = APP_DIR / "poller.pid"
STARTUP_LAUNCHER = Path(os.environ.get("APPDATA", APP_DIR)) / "Microsoft/Windows/Start Menu/Programs/Startup/TouchGrass iCloud Poller.cmd"
SUPPORTED = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".mov", ".mp4"}
DEFAULT_MINIMUM_FREE_GB = 10


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_token(value):
    if os.name != "nt":
        raise RuntimeError("DPAPI token storage requires Windows")
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    source, keepalive = _blob(value.encode("utf-8"))
    output = DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(source), "TouchGrass iCloud Poller", None, None, None, 0, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return base64.b64encode(ctypes.string_at(output.pbData, output.cbData)).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def unprotect_token(value):
    encrypted = base64.b64decode(value)
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    source, keepalive = _blob(encrypted)
    output = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def load_config():
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"Poller is not configured. Run configure first ({CONFIG_PATH}).")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def open_db():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            relative_path TEXT PRIMARY KEY,
            source_key TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime REAL NOT NULL,
            stable_count INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT 'discovered',
            priority INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_retry REAL NOT NULL DEFAULT 0,
            last_seen_scan TEXT,
            error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS files_queue ON files(state, priority DESC, mtime DESC);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    return db


def setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(db, key, value):
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    db.commit()


def source_key(relative_path):
    return hashlib.sha256(relative_path.replace("\\", "/").lower().encode("utf-8")).hexdigest()


def enumerate_media(root):
    for directory, _, names in os.walk(root):
        for name in names:
            path = Path(directory) / name
            if path.suffix.lower() not in SUPPORTED:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            yield path, path.relative_to(root).as_posix(), stat


def reconcile_local(db, root):
    scan_id = datetime.now(timezone.utc).isoformat()
    historical_initialized = setting(db, "baseline_complete", "0") == "1"
    discovered = updated = 0
    for path, relative, stat in enumerate_media(root):
        row = db.execute("SELECT size_bytes,mtime,state FROM files WHERE relative_path=?", (relative,)).fetchone()
        priority = 100 if historical_initialized and row is None else 0
        if row is None:
            db.execute(
                "INSERT INTO files(relative_path,source_key,size_bytes,mtime,stable_count,state,priority,last_seen_scan) VALUES(?,?,?,?,0,'discovered',?,?)",
                (relative, source_key(relative), stat.st_size, stat.st_mtime, priority, scan_id),
            )
            discovered += 1
        elif row[0] != stat.st_size or row[1] != stat.st_mtime:
            db.execute(
                "UPDATE files SET size_bytes=?,mtime=?,stable_count=0,state='discovered',priority=?,attempts=0,error='',last_seen_scan=? WHERE relative_path=?",
                (stat.st_size, stat.st_mtime, max(priority, 50), scan_id, relative),
            )
            updated += 1
        else:
            db.execute("UPDATE files SET stable_count=stable_count+1,last_seen_scan=? WHERE relative_path=?", (scan_id, relative))
    db.execute("UPDATE files SET state='missing' WHERE last_seen_scan IS NULL OR last_seen_scan<>?", (scan_id,))
    set_setting(db, "baseline_complete", "1")
    db.commit()
    return scan_id, discovered, updated


class ExifToolSession:
    def __init__(self, executable):
        self.executable = executable
        self.process = None
        self.counter = 0

    def __enter__(self):
        self.process = subprocess.Popen(
            [self.executable, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        return self

    def read(self, path):
        self.counter += 1
        marker = str(self.counter)
        args = [
            "-j", "-n", "-api", "QuickTimeUTC=1", "-FileType", "-MIMEType", "-FileModifyDate",
            "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate", "-OffsetTimeOriginal", "-GPSLatitude",
            "-GPSLongitude", "-ImageWidth", "-ImageHeight", "-Orientation", "-Duration", "-Make", "-Model",
            "-ContentIdentifier", str(path), f"-execute{marker}",
        ]
        self.process.stdin.write("\n".join(args) + "\n")
        self.process.stdin.flush()
        lines = []
        ready = f"{{ready{marker}}}"
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("ExifTool stopped unexpectedly")
            if line.strip() == ready:
                break
            lines.append(line)
        parsed = json.loads("".join(lines))
        return parsed[0] if parsed else {}

    def __exit__(self, *_):
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write("-stay_open\nFalse\n")
                self.process.stdin.flush()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()


def parse_exif_datetime(value, offset=""):
    if not value:
        return None, "", ""
    text = str(value).strip()
    local_text = text[:19]
    parsed = None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(local_text, fmt)
            break
        except ValueError:
            pass
    if parsed is None:
        return None, text[:40], str(offset or "")[:10]
    effective_offset = str(offset or "")
    if len(text) > 19 and text[19:20] in {"+", "-"}:
        effective_offset = text[19:25]
    if effective_offset and len(effective_offset) >= 6:
        sign = 1 if effective_offset[0] == "+" else -1
        minutes = sign * (int(effective_offset[1:3]) * 60 + int(effective_offset[4:6]))
        from datetime import timedelta
        parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=minutes)))
    else:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc).isoformat(), local_text, effective_offset[:10]


def record_from_metadata(row, metadata):
    captured, captured_local, offset = parse_exif_datetime(
        metadata.get("DateTimeOriginal") or metadata.get("MediaCreateDate") or metadata.get("CreateDate"),
        metadata.get("OffsetTimeOriginal"),
    )
    relative = row["relative_path"]
    mime = metadata.get("MIMEType") or mimetypes.guess_type(relative)[0] or "application/octet-stream"
    known = {key: metadata.get(key) for key in ("FileType", "CreateDate", "MediaCreateDate") if metadata.get(key) is not None}
    return {
        "source_key": row["source_key"], "relative_path": relative, "mime_type": mime,
        "size_bytes": row["size_bytes"], "file_modified_at": datetime.fromtimestamp(row["mtime"], timezone.utc).isoformat(),
        "captured_at": captured, "captured_local": captured_local, "timezone_offset": offset,
        "latitude": metadata.get("GPSLatitude"), "longitude": metadata.get("GPSLongitude"),
        "width": metadata.get("ImageWidth"), "height": metadata.get("ImageHeight"),
        "orientation": str(metadata.get("Orientation") or ""), "duration_seconds": metadata.get("Duration"),
        "camera_make": str(metadata.get("Make") or ""), "camera_model": str(metadata.get("Model") or ""),
        "live_photo_identifier": str(metadata.get("ContentIdentifier") or ""), "metadata": known,
    }


def request_json(url, username, token, payload, timeout=60):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    auth = base64.b64encode(f"{username}:{token}".encode()).decode()
    request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"{}")


def get_json(url, username, token, timeout=30):
    auth = base64.b64encode(f"{username}:{token}".encode()).decode()
    request = urllib.request.Request(url, method="GET", headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"{}")


def locate_exiftool(config=None, explicit=""):
    """Find and validate ExifTool without requiring users to manage its path."""
    configured = explicit or (config or {}).get("exiftool") or ""
    candidates = [Path(configured)] if configured else []
    on_path = shutil.which("exiftool")
    if on_path:
        candidates.append(Path(on_path))
    user_root = Path(os.environ.get("USERPROFILE", Path.home()))
    downloads = user_root / "Downloads"
    if downloads.is_dir():
        for pattern in (
            "exiftool-*_64/exiftool-*_64/exiftool*.exe",
            "exiftool-*_32/exiftool-*_32/exiftool*.exe",
        ):
            candidates.extend(sorted(downloads.glob(pattern), reverse=True))
    candidates.extend([
        Path(os.environ.get("LOCALAPPDATA", user_root)) / "TouchGrass" / "ExifTool" / "exiftool.exe",
        Path("C:/Program Files/ExifTool/exiftool.exe"),
    ])
    checked = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved in checked or not resolved.is_file():
                continue
            checked.add(resolved)
            result = subprocess.run([str(resolved), "-ver"], capture_output=True, text=True, timeout=20)
            if result.returncode == 0 and result.stdout.strip():
                return str(resolved)
        except (OSError, subprocess.SubprocessError):
            continue
    raise RuntimeError(
        "ExifTool was not found. Download the 64-bit Windows executable from exiftool.org, extract it under Downloads, and retry setup."
    )


def process_queue(db, config, limit=10):
    root = Path(config["root"])
    rows = db.execute(
        "SELECT * FROM files WHERE state IN ('discovered','error') AND stable_count>=1 AND next_retry<=? ORDER BY priority DESC,mtime DESC LIMIT ?",
        (time.time(), limit),
    ).fetchall()
    if not rows:
        return 0
    token = unprotect_token(config["token_dpapi"])
    records, processed_rows = [], []
    with ExifToolSession(locate_exiftool(config)) as exiftool:
        for row in rows:
            path = root / Path(row["relative_path"])
            try:
                metadata = exiftool.read(path)
                records.append(record_from_metadata(row, metadata))
                processed_rows.append(row)
            except Exception as exc:
                attempts = row["attempts"] + 1
                delay = min(86400, 30 * (2 ** min(attempts, 10)))
                db.execute("UPDATE files SET state='error',attempts=?,next_retry=?,error=? WHERE relative_path=?", (attempts, time.time() + delay, str(exc)[:1000], row["relative_path"]))
    if records:
        try:
            response = request_json(config["ingest_url"], config["username"], token, {"assets": records})
            by_key = {item.get("source_key"): item for item in response.get("results", [])}
            for row in processed_rows:
                result = by_key.get(row["source_key"], {})
                if result.get("status") == "error":
                    db.execute("UPDATE files SET state='error',error=? WHERE relative_path=?", (result.get("detail", "Server rejected metadata")[:1000], row["relative_path"]))
                else:
                    db.execute("UPDATE files SET state='ready',priority=0,attempts=0,error='' WHERE relative_path=?", (row["relative_path"],))
        except Exception as exc:
            for row in processed_rows:
                db.execute("UPDATE files SET state='error',next_retry=?,error=? WHERE relative_path=?", (time.time() + 60, str(exc)[:1000], row["relative_path"]))
    db.commit()
    return len(rows)


def send_reconcile(db, config, scan_id, discovered=0, updated=0):
    keys = [row[0] for row in db.execute("SELECT source_key FROM files WHERE state<>'missing'")]
    backlog = db.execute("SELECT COUNT(*) FROM files WHERE state IN ('discovered','error')").fetchone()[0]
    errors = db.execute("SELECT COUNT(*) FROM files WHERE state='error'").fetchone()[0]
    token = unprotect_token(config["token_dpapi"])
    return request_json(config["reconcile_url"], config["username"], token, {
        "seen_source_keys": keys, "started_at": scan_id, "discovered_count": discovered,
        "updated_count": updated, "backlog_count": backlog, "error_count": errors,
    })


def hydration_capacity(root, config):
    free_gb = shutil.disk_usage(root).free / (1024 ** 3)
    minimum_gb = max(1.0, float(config.get("minimum_free_gb", DEFAULT_MINIMUM_FREE_GB)))
    return free_gb >= minimum_gb, free_gb, minimum_gb


def run_cycle(db, config, batch=10):
    root = Path(config["root"])
    if not root.is_dir():
        raise RuntimeError(f"iCloud Photos folder is unavailable: {root}")
    token = unprotect_token(config["token_dpapi"])
    try:
        control = get_json(config["ingest_url"], config["username"], token)
        set_setting(db, "last_server_error", "")
        retry_request = str(control.get("retry_requested_at") or "")
        if retry_request and retry_request != setting(db, "last_retry_request", ""):
            db.execute("UPDATE files SET state='discovered',attempts=0,next_retry=0,error='' WHERE state='error'")
            db.commit()
            set_setting(db, "last_retry_request", retry_request)
    except Exception as exc:
        set_setting(db, "last_server_error", str(exc))
    scan_id, discovered, updated = reconcile_local(db, root)
    has_capacity, free_gb, minimum_gb = hydration_capacity(root, config)
    set_setting(db, "disk_free_gb", f"{free_gb:.2f}")
    set_setting(db, "minimum_free_gb", f"{minimum_gb:.2f}")
    set_setting(db, "disk_guard_active", "0" if has_capacity else "1")
    processed = process_queue(db, config, batch) if has_capacity else 0
    try:
        send_reconcile(db, config, scan_id, discovered, updated)
        set_setting(db, "last_server_error", "")
    except Exception as exc:
        set_setting(db, "last_server_error", str(exc))
    set_setting(db, "last_scan", datetime.now(timezone.utc).isoformat())
    return {"discovered": discovered, "updated": updated, "processed": processed, "disk_guard_active": not has_capacity}


def rotate_credential():
    config = load_config()
    ingest_url = config["ingest_url"]
    if not ingest_url.endswith("/assets/"):
        raise RuntimeError("Cannot derive the credential-rotation endpoint from the ingestion URL")
    rotate_url = ingest_url[:-len("assets/")] + "rotate-token/"
    current_token = unprotect_token(config["token_dpapi"])
    response = request_json(rotate_url, config["username"], current_token, {})
    replacement = str(response.get("token") or "")
    if len(replacement) < 32:
        raise RuntimeError("TouchGrass did not return a replacement poller credential")
    config["token_dpapi"] = protect_token(replacement)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Rotated the one-time setup token into a DPAPI-only poller credential.")


def configure(args):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise RuntimeError(f"Folder does not exist: {root}")
    exiftool = locate_exiftool(explicit=args.exiftool or "")
    config = {
        "root": str(root), "ingest_url": args.url, "reconcile_url": args.reconcile_url,
        "username": args.username, "token_dpapi": protect_token(args.token), "exiftool": exiftool,
        "interval_seconds": args.interval, "minimum_free_gb": DEFAULT_MINIMUM_FREE_GB,
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Configured {root}. ExifTool {exiftool}. Token encrypted with Windows DPAPI at {CONFIG_PATH}.")


def validate_endpoint(value):
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"Invalid TouchGrass endpoint: {value}")
    return value.rstrip("/") + "/"


def set_endpoints(args):
    config = load_config()
    config["ingest_url"] = validate_endpoint(args.url)
    config["reconcile_url"] = validate_endpoint(args.reconcile_url)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Updated TouchGrass poller endpoints; the encrypted credential was preserved.")


def install_task(args):
    python = Path(sys.executable).resolve()
    script = Path(__file__).resolve()
    task_command = f'"{python}" "{script}" run'
    installed_with = "Task Scheduler"
    try:
        subprocess.run(
            ["schtasks", "/Create", "/TN", "TouchGrass iCloud Poller", "/SC", "ONLOGON", "/TR", task_command, "/RL", "LIMITED", "/F"],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        # ONLOGON task creation is denied by policy on some non-admin Windows
        # accounts. The signed-in user's Startup folder provides equivalent
        # persistence without elevation or a UAC prompt.
        pythonw = python.with_name("pythonw.exe")
        executable = pythonw if pythonw.is_file() else python
        STARTUP_LAUNCHER.parent.mkdir(parents=True, exist_ok=True)
        STARTUP_LAUNCHER.write_text(
            f'@echo off\r\nstart "" /min "{executable}" "{script}" run\r\n', encoding="utf-8"
        )
        installed_with = "the Windows Startup folder"
    start_background_worker()
    print(f"Installed with {installed_with} and started the poller in the signed-in iCloud for Windows session.")


def start_background_worker():
    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.is_file() else python
    flags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        flags |= getattr(subprocess, name, 0)
    process = subprocess.Popen(
        [str(executable), str(Path(__file__).resolve()), "run"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=flags,
    )
    return process.pid


def acquire_instance_lock():
    """Return an open Windows lock handle, or None when a worker is running."""
    import msvcrt

    APP_DIR.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def run_forever(db, config):
    lock_handle = acquire_instance_lock()
    if lock_handle is None:
        print("TouchGrass iCloud Poller is already running.")
        return
    PID_PATH.write_text(str(os.getpid()), encoding="ascii")
    try:
        while True:
            if setting(db, "paused", "0") != "1":
                try:
                    result = run_cycle(db, config)
                    print(f"{datetime.now().isoformat()} {result}", flush=True)
                except Exception as exc:
                    print(f"{datetime.now().isoformat()} poller error: {exc}", file=sys.stderr, flush=True)
            time.sleep(max(15, int(config.get("interval_seconds", 30))))
    finally:
        PID_PATH.unlink(missing_ok=True)
        lock_handle.close()


def add_connection_arguments(command):
    command.add_argument("--root", required=True)
    command.add_argument("--url", required=True)
    command.add_argument("--reconcile-url", required=True)
    command.add_argument("--username", required=True)
    command.add_argument("--token", required=True)
    command.add_argument("--exiftool")
    command.add_argument("--interval", type=int, default=30)


def status(db):
    counts = dict(db.execute("SELECT state,COUNT(*) FROM files GROUP BY state").fetchall())
    print(json.dumps({
        "database": str(DB_PATH), "last_scan": setting(db, "last_scan"), "counts": counts,
        "paused": setting(db, "paused", "0") == "1", "last_server_error": setting(db, "last_server_error", ""),
        "disk_guard_active": setting(db, "disk_guard_active", "0") == "1",
        "disk_free_gb": float(setting(db, "disk_free_gb", "0") or 0),
        "minimum_free_gb": float(setting(db, "minimum_free_gb", str(DEFAULT_MINIMUM_FREE_GB)) or DEFAULT_MINIMUM_FREE_GB),
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description="TouchGrass iCloud Photos poller")
    sub = parser.add_subparsers(dest="command", required=True)
    cfg = sub.add_parser("configure")
    add_connection_arguments(cfg)
    setup = sub.add_parser("setup")
    add_connection_arguments(setup)
    endpoints = sub.add_parser("set-endpoints")
    endpoints.add_argument("--url", required=True)
    endpoints.add_argument("--reconcile-url", required=True)
    sub.add_parser("install"); sub.add_parser("uninstall"); sub.add_parser("run"); sub.add_parser("pause"); sub.add_parser("resume")
    sub.add_parser("rotate-token")
    sub.add_parser("status"); sub.add_parser("scan-now"); sub.add_parser("retry-errors")
    args = parser.parse_args()
    if args.command == "configure":
        return configure(args)
    if args.command == "setup":
        configure(args)
        db = open_db()
        config = load_config()
        result = run_cycle(db, config, batch=1)
        rotate_credential()
        install_task(args)
        print(json.dumps({"connected": True, **result}, indent=2))
        return
    if args.command == "set-endpoints":
        return set_endpoints(args)
    if args.command == "rotate-token":
        return rotate_credential()
    db = open_db()
    if args.command == "install": return install_task(args)
    if args.command == "uninstall":
        subprocess.run(["schtasks", "/Delete", "/TN", "TouchGrass iCloud Poller", "/F"], check=False)
        STARTUP_LAUNCHER.unlink(missing_ok=True)
        if PID_PATH.exists():
            subprocess.run(["taskkill", "/PID", PID_PATH.read_text(encoding="ascii").strip(), "/T", "/F"], check=False)
        return
    if args.command == "pause": set_setting(db, "paused", "1"); return
    if args.command == "resume": set_setting(db, "paused", "0"); return
    if args.command == "retry-errors":
        db.execute("UPDATE files SET state='discovered',attempts=0,next_retry=0,error='' WHERE state='error'"); db.commit(); return
    if args.command == "status": return status(db)
    config = load_config()
    if args.command == "scan-now":
        print(json.dumps(run_cycle(db, config, batch=25), indent=2)); return
    return run_forever(db, config)


if __name__ == "__main__":
    main()
