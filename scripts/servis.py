import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(errors="replace")
sys.stderr.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
LOGS = ROOT / "logs"
STATE_FILE = LOGS / "calisma.json"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
PORT = 8010
HEALTH_URL = f"http://127.0.0.1:{PORT}/api/health"
OPEN_URL = f"http://localhost:{PORT}"
NO_WINDOW = 0x08000000


def health():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return data if data.get("service") == "pulsewatch" else None


def port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def read_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def process_alive(pid):
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True,
        text=True,
        errors="ignore",
    )
    return str(pid) in result.stdout


def stop_process(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def tail(path, lines=20):
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def frontend_is_stale():
    index = DIST / "index.html"
    if not index.exists():
        return True
    built_at = index.stat().st_mtime
    sources = [FRONTEND / "index.html", FRONTEND / "package.json", FRONTEND / "vite.config.js"]
    sources += [path for path in (FRONTEND / "src").rglob("*") if path.is_file()]
    return any(path.stat().st_mtime > built_at for path in sources)


def build_frontend():
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "build.log", "w", encoding="utf-8") as log:
        result = subprocess.run(
            "npm run build", cwd=FRONTEND, shell=True, stdout=log, stderr=subprocess.STDOUT
        )
    return result.returncode


def start(mode):
    state = read_state()
    if state and process_alive(state["api_pid"]):
        if health():
            print(f"PulseWatch zaten calisiyor: {OPEN_URL}")
            return 0
        stop_process(state["api_pid"])
    if port_in_use():
        print(f"{PORT} portu baska bir uygulama tarafindan kullaniliyor. Once onu kapatin.")
        return 1

    if frontend_is_stale():
        print("Arayuz derleniyor, bu bir dakika surebilir...")
        if build_frontend() != 0:
            print(tail(LOGS / "build.log"))
            return 1

    env = os.environ.copy()
    env["FRONTEND_DIST"] = str(DIST)
    env["FRONTEND_URL"] = f"http://localhost:{PORT}"
    env["PUBLIC_URL"] = f"http://localhost:{PORT}"
    env["PYTHONUTF8"] = "1"
    if mode == "demo":
        env["DATABASE_URL"] = "sqlite+aiosqlite:///./data/demo.db"
        env["SEED_DEMO"] = "true"
    else:
        env.pop("DATABASE_URL", None)
        env["SEED_DEMO"] = "false"

    LOGS.mkdir(exist_ok=True)
    log = open(LOGS / "api.log", "a", encoding="utf-8")
    process = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=BACKEND,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=NO_WINDOW,
    )
    STATE_FILE.write_text(json.dumps({"api_pid": process.pid, "mode": mode}), encoding="utf-8")

    for _ in range(120):
        if process.poll() is not None:
            break
        if health():
            print(f"PulseWatch hazir: {OPEN_URL} (veri: {mode})")
            return 0
        time.sleep(0.5)

    print("Sunucu baslatilamadi. Son kayitlar:")
    print(tail(LOGS / "api.log"))
    stop_process(process.pid)
    STATE_FILE.unlink(missing_ok=True)
    return 1


def stop():
    state = read_state()
    if not state:
        print("Calisan PulseWatch bulunamadi.")
        return 0
    if process_alive(state["api_pid"]):
        stop_process(state["api_pid"])
    STATE_FILE.unlink(missing_ok=True)
    print("PulseWatch durduruldu.")
    return 0


def main(args):
    if args[:1] == ["baslat"]:
        return start(args[1] if len(args) > 1 else "normal")
    if args[:1] == ["durdur"]:
        return stop()
    print("Kullanim: servis.py baslat [normal|demo] | durdur")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
