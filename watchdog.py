#!/usr/bin/env python3
"""
Ryuu K Discord Bot Watchdog + Webhook Server

Runs alongside bot.py on the Windows machine.
- Auto-restarts the bot if it dies (watchdog loop, every 60s)
- Exposes a small HTTP API on port 8734 for remote control
- Protected by a secret token

Endpoints:
  GET  /status        -> {"online": true/false, "pid": int|null, "uptime": str}
  POST /restart       -> kills old bot, starts new one
  POST /stop          -> kills bot, does NOT restart (watchdog will restart within 60s unless --no-watchdog)
  GET  /health        -> "ok" (simple liveness check)

Usage:
  python watchdog.py
  python watchdog.py --no-watchdog   (webhook only, no auto-restart)
  python watchdog.py --port 8734

Environment variables (or create .env):
  WATCHDOG_TOKEN   - secret token for webhook auth (required for remote access)
  BOT_DIR          - path to the discord-rag-bot folder
  BOT_SCRIPT       - bot.py (default)
  WATCHDOG_PORT    - 8734 (default)
  WATCHDOG_INTERVAL - 60 seconds (default)
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import signal
import threading
import http.server
import socketserver
from pathlib import Path

# Try dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- Config ---

BOT_DIR = os.getenv("BOT_DIR", r"C:\Users\EliteBook\OneDrive\Ryuu\GPT docs\Ryuu_RAG\discord-rag-bot")
BOT_SCRIPT = os.getenv("BOT_SCRIPT", "bot.py")
LOCK_FILE = os.path.join(BOT_DIR, "ryuu_discord_bot.lock")
OUT_LOG = os.path.join(BOT_DIR, "ryuu_discord_bot.out.log")
ERR_LOG = os.path.join(BOT_DIR, "ryuu_discord_bot.err.log")
WATCHDOG_PORT = int(os.getenv("WATCHDOG_PORT", "8734"))
WATCHDOG_INTERVAL = int(os.getenv("WATCHDOG_INTERVAL", "60"))
WATCHDOG_TOKEN = os.getenv("WATCHDOG_TOKEN", "")
NO_WATCHDOG = False

bot_process = None
bot_start_time = None
watchdog_running = True
lock = threading.Lock()


def get_pid_from_lock():
    """Read the PID from the lock file, or None."""
    try:
        with open(LOCK_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def is_bot_alive():
    """Check if the bot process is actually running."""
    global bot_process
    # If we have a direct subprocess handle, check it
    if bot_process is not None:
        return bot_process.poll() is None
    # Otherwise check the lock file PID
    pid = get_pid_from_lock()
    if pid is None:
        return False
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def kill_bot():
    """Kill the bot process."""
    global bot_process
    if bot_process is not None and bot_process.poll() is None:
        try:
            bot_process.terminate()
            time.sleep(3)
            if bot_process.poll() is None:
                bot_process.kill()
        except Exception:
            pass
        bot_process = None

    # Also kill any stray python bot.py processes by PID from lock
    pid = get_pid_from_lock()
    if pid:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

    # Clear lock file
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


def start_bot():
    """Start the bot as a subprocess."""
    global bot_process, bot_start_time

    # Clear stale lock
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass

    # Clear old logs
    for log_file in [OUT_LOG, ERR_LOG]:
        try:
            os.remove(log_file)
        except FileNotFoundError:
            pass

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    bot_path = os.path.join(BOT_DIR, BOT_SCRIPT)
    if not os.path.exists(bot_path):
        print(f"[watchdog] ERROR: Bot script not found at {bot_path}")
        return False

    try:
        out_fh = open(OUT_LOG, "a")
        err_fh = open(ERR_LOG, "a")
        bot_process = subprocess.Popen(
            [sys.executable, "-u", BOT_SCRIPT],
            cwd=BOT_DIR,
            stdout=out_fh,
            stderr=err_fh,
            env=env,
        )
        bot_start_time = time.time()
        print(f"[watchdog] Started bot.py (PID {bot_process.pid})")
        return True
    except Exception as e:
        print(f"[watchdog] Failed to start bot: {e}")
        return False


def restart_bot():
    """Kill and restart the bot."""
    with lock:
        print("[watchdog] Restarting bot...")
        kill_bot()
        time.sleep(2)
        return start_bot()


def watchdog_loop():
    """Background loop that restarts the bot if it dies."""
    while watchdog_running and not NO_WATCHDOG:
        time.sleep(WATCHDOG_INTERVAL)
        if not is_bot_alive():
            print("[watchdog] Bot appears offline. Auto-restarting...")
            restart_bot()


# --- HTTP Server ---

class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default access logs
        pass

    def _send_json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_token(self):
        """Check Authorization header against WATCHDOG_TOKEN."""
        if not WATCHDOG_TOKEN:
            return True  # No token configured, allow all
        auth = self.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        if token == WATCHDOG_TOKEN:
            return True
        return False

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return

        if self.path == "/status":
            alive = is_bot_alive()
            pid = bot_process.pid if bot_process else get_pid_from_lock()
            uptime = None
            if alive and bot_start_time:
                uptime = int(time.time() - bot_start_time)
            self._send_json(200, {
                "online": alive,
                "pid": pid,
                "uptime_seconds": uptime,
            })
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if not self._check_token():
            self._send_json(401, {"error": "unauthorized"})
            return

        if self.path == "/restart":
            success = restart_bot()
            self._send_json(200 if success else 500, {
                "restarted": success,
                "pid": bot_process.pid if bot_process else None,
            })
            return

        if self.path == "/stop":
            kill_bot()
            self._send_json(200, {"stopped": True})
            return

        self._send_json(404, {"error": "not found"})


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global NO_WATCHDOG

    parser = argparse.ArgumentParser(description="Ryuu K bot watchdog + webhook server")
    parser.add_argument("--no-watchdog", action="store_true", help="Disable auto-restart loop")
    parser.add_argument("--port", type=int, default=WATCHDOG_PORT, help="HTTP server port")
    parser.add_argument("--no-start", action="store_true", help="Don't start the bot on launch")
    args = parser.parse_args()

    NO_WATCHDOG = args.no_watchdog

    print(f"[watchdog] Bot dir: {BOT_DIR}")
    print(f"[watchdog] Bot script: {BOT_SCRIPT}")
    print(f"[watchdog] HTTP port: {args.port}")
    print(f"[watchdog] Auto-restart: {not NO_WATCHDOG}")
    print(f"[watchdog] Token set: {bool(WATCHDOG_TOKEN)}")

    # Start the bot immediately
    if not args.no_start:
        start_bot()

    # Start watchdog thread
    if not NO_WATCHDOG:
        t = threading.Thread(target=watchdog_loop, daemon=True)
        t.start()
        print(f"[watchdog] Watchdog loop running (interval: {WATCHDOG_INTERVAL}s)")

    # Start HTTP server
    server = ThreadedHTTPServer(("0.0.0.0", args.port), WebhookHandler)
    print(f"[watchdog] Webhook server listening on :{args.port}")
    print(f"[watchdog]   GET  /status   - check bot status")
    print(f"[watchdog]   POST /restart  - restart the bot")
    print(f"[watchdog]   POST /stop     - stop the bot")
    print(f"[watchdog]   GET  /health  - liveness check")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[watchdog] Shutting down...")
        watchdog_running = False
        kill_bot()
        server.shutdown()


if __name__ == "__main__":
    main()
