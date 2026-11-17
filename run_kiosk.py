"""
run_kiosk.py — Unified Terminal Runner for VidyaSahayak Kiosk
Streams Backend, Frontend, and Public Mobile Tunnel (ngrok) directly into this terminal window.
Press Ctrl+C to cleanly stop all services.
"""

import os
import sys
import shutil
import subprocess
import threading
import signal
import time
import re
import json

# Configure UTF-8 for console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ANSI color codes for clear log distinction
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"

project_root = os.path.abspath(os.path.dirname(__file__))
backend_dir = os.path.join(project_root, "backend")
frontend_dir = os.path.join(project_root, "frontend")
tunnel_file = os.path.join(frontend_dir, "public", "tunnel.json")

processes = []
active_tunnel_url = None

def find_ngrok_bin():
    """Locate the ngrok executable on this system."""
    which_path = shutil.which("ngrok")
    if which_path:
        return which_path

    # Fallback winget / local AppData locations on Windows
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe", "ngrok.exe"),
        os.path.join(local_app_data, "ngrok", "ngrok.exe"),
        r"C:\Program Files\ngrok\ngrok.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def write_tunnel_file(url):
    """Write active public tunnel URL to frontend/public/tunnel.json."""
    global active_tunnel_url
    active_tunnel_url = url
    os.environ["NGROK_TUNNEL_URL"] = url
    try:
        os.makedirs(os.path.dirname(tunnel_file), exist_ok=True)
        with open(tunnel_file, "w", encoding="utf-8") as f:
            json.dump({"publicUrl": url, "updatedAt": time.time()}, f, indent=2)
    except Exception as e:
        print(f"{YELLOW}[TUNNEL] Could not write tunnel.json: {e}{RESET}", flush=True)

def remove_tunnel_file():
    """Clean up tunnel.json so stale links are never served."""
    try:
        if os.path.exists(tunnel_file):
            os.remove(tunnel_file)
    except Exception:
        pass

def stream_logs(pipe, prefix, color):
    """Read lines from a process pipe and print with colored prefix in real-time."""
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            clean_line = line.rstrip()
            if clean_line:
                print(f"{color}{BOLD}[{prefix}]{RESET} {clean_line}", flush=True)
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass

def stream_tunnel_logs(pipe):
    """Monitor ngrok output, extract the live public HTTPS URL, and stream status."""
    url_found = False
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            clean_line = line.rstrip()
            if not clean_line:
                continue

            # Look for the public tunnel URL
            match = re.search(r"url=(https://[^\s]+)", clean_line) or re.search(r'"url":\s*"(https://[^"]+)"', clean_line)
            if match and not url_found:
                url_found = True
                pub_url = match.group(1).rstrip("/")
                write_tunnel_file(pub_url)
                print("\n" + "=" * 70, flush=True)
                print(f"{MAGENTA}{BOLD}   🌐 MOBILE NAVIGATION TUNNEL ACTIVE{RESET}", flush=True)
                print(f"   {MAGENTA}{BOLD}📱 Phones on ANY network (4G/5G/WiFi) can scan QR codes!{RESET}", flush=True)
                print(f"   {BOLD}Public URL:{RESET} {MAGENTA}{BOLD}{pub_url}{RESET}", flush=True)
                print("=" * 70 + "\n", flush=True)
            elif "started tunnel" in clean_line or "client session established" in clean_line or "lvl=error" in clean_line:
                print(f"{MAGENTA}{BOLD}[TUNNEL]{RESET} {clean_line}", flush=True)
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass

def cleanup(sig=None, frame=None):
    """Gracefully terminate backend, frontend, and tunnel processes."""
    print(f"\n{YELLOW}{BOLD}[KIOSK] Shutting down all services...{RESET}", flush=True)
    remove_tunnel_file()
    for p in processes:
        if p.poll() is None:
            try:
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
    print(f"{GREEN}{BOLD}[KIOSK] All services stopped cleanly.{RESET}", flush=True)
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    remove_tunnel_file()

    print("=" * 70, flush=True)
    print(f"{CYAN}{BOLD}   VidyaSahayak Kiosk — Live Unified Terminal Stream{RESET}", flush=True)
    print("=" * 70, flush=True)
    print(f"  {CYAN}Backend:{RESET}   http://localhost:8000 (FastAPI Docs: /docs)")
    print(f"  {GREEN}Frontend:{RESET}  http://localhost:3000 (Orb Kiosk UI)")

    ngrok_bin = find_ngrok_bin()
    if ngrok_bin:
        print(f"  {MAGENTA}Tunnel:{RESET}    ngrok public HTTPS bridge (starting...)")
    else:
        print(f"  {YELLOW}Tunnel:{RESET}    ngrok not found. Navigation will use LAN IP fallback.")

    print(f"  {YELLOW}Press Ctrl+C at any time to stop all services.{RESET}")
    print("=" * 70 + "\n", flush=True)

    # 1. Start Public Mobile Tunnel (ngrok) if available
    if ngrok_bin:
        tunnel_cmd = [ngrok_bin, "http", "3000", "--log=stdout"]
        tunnel_proc = subprocess.Popen(
            tunnel_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
        processes.append(tunnel_proc)
        t_tunnel = threading.Thread(target=stream_tunnel_logs, args=(tunnel_proc.stdout,), daemon=True)
        t_tunnel.start()

    # 2. Start Backend (uvicorn)
    backend_env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    backend_cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", "8000",
        "--reload",
        "--reload-dir", backend_dir,
        "--reload-dir", os.path.join(project_root, "config"),
        "--reload-dir", os.path.join(project_root, "agents"),
    ]
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=backend_dir,
        env=backend_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )
    processes.append(backend_proc)

    # 3. Start Frontend (npm run dev)
    npm_bin = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_cmd = [npm_bin, "run", "dev"]
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1
    )
    processes.append(frontend_proc)

    # 4. Stream backend and frontend logs
    t_backend = threading.Thread(target=stream_logs, args=(backend_proc.stdout, "BACKEND", CYAN), daemon=True)
    t_frontend = threading.Thread(target=stream_logs, args=(frontend_proc.stdout, "FRONTEND", GREEN), daemon=True)

    t_backend.start()
    t_frontend.start()

    # Keep main alive and monitor health
    try:
        while True:
            if backend_proc.poll() is not None:
                print(f"{RED}[KIOSK] Backend exited with code {backend_proc.poll()}{RESET}", flush=True)
                break
            if frontend_proc.poll() is not None:
                print(f"{RED}[KIOSK] Frontend exited with code {frontend_proc.poll()}{RESET}", flush=True)
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()

if __name__ == "__main__":
    main()
