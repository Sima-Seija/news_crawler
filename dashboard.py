import json
import os
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "web"
DATA_FILE = ROOT_DIR / "politics_news.json"
STATE_FILE = ROOT_DIR / ".crawl_state.json"
HOST = "127.0.0.1"
PORT = 8000
crawler_process = None
crawler_lock = threading.Lock()


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def current_status():
    articles = load_json(DATA_FILE, [])
    state = load_json(STATE_FILE, {})
    status = {
        "running": crawler_process is not None and crawler_process.poll() is None,
        "article_count": len(articles),
        "source_counts": {},
        "seen_count": len(state.get("seen_urls", [])) if isinstance(state, dict) else 0,
        "last_updated": None,
    }
    for article in articles:
        source = article.get("source", "Unknown")
        status["source_counts"][source] = status["source_counts"].get(source, 0) + 1
    if DATA_FILE.exists():
        status["last_updated"] = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(DATA_FILE.stat().st_mtime)
        )
    return status


def start_crawler():
    global crawler_process
    with crawler_lock:
        if crawler_process is not None and crawler_process.poll() is None:
            return False
        cmd = [sys.executable, str(ROOT_DIR / "politics_news_scraper.py"),
               "--interval-hours", "1.5", "--output", str(DATA_FILE), "--state", str(STATE_FILE)]
        crawler_process = subprocess.Popen(cmd, cwd=str(ROOT_DIR))
        return True


def stop_crawler():
    global crawler_process
    with crawler_lock:
        if crawler_process is None or crawler_process.poll() is not None:
            crawler_process = None
            return False
        crawler_process.terminate()
        try:
            crawler_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            crawler_process.kill()
            crawler_process.wait()
        crawler_process = None
        return True


class DashboardHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urlparse(path)
        if parsed.path.startswith("/api/"):
            return ""
        if parsed.path == "/" or parsed.path == "":
            return str(WEB_DIR / "index.html")
        return str(WEB_DIR / parsed.path.lstrip("/"))

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/articles":
            articles = load_json(DATA_FILE, [])
            self.send_json({"articles": articles})
            return
        if parsed.path == "/api/status":
            self.send_json(current_status())
            return
        if parsed.path == "/api/state":
            state = load_json(STATE_FILE, {})
            self.send_json(state)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/control":
            data = self.read_json()
            action = data.get("action")
            if action == "start":
                ok = start_crawler()
                self.send_json({"started": ok, "status": current_status()})
                return
            if action == "stop":
                ok = stop_crawler()
                self.send_json({"stopped": ok, "status": current_status()})
                return
            self.send_json({"error": "invalid action"}, code=400)
            return
        if parsed.path == "/api/article":
            data = self.read_json()
            articles = load_json(DATA_FILE, [])
            index = data.get("index")
            if index is None or not isinstance(index, int) or index < 0 or index >= len(articles):
                self.send_json({"error": "invalid index"}, code=400)
                return
            article = articles[index]
            article["source"] = data.get("source", article.get("source"))
            article["title"] = data.get("title", article.get("title"))
            article["published_at"] = data.get("published_at", article.get("published_at"))
            article["content"] = data.get("content", article.get("content"))
            article["url"] = data.get("url", article.get("url"))
            save_json(DATA_FILE, articles)
            self.send_json({"saved": True, "article": article})
            return
        self.send_json({"error": "not found"}, code=404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/article":
            data = self.read_json()
            articles = load_json(DATA_FILE, [])
            index = data.get("index")
            if index is None or not isinstance(index, int) or index < 0 or index >= len(articles):
                self.send_json({"error": "invalid index"}, code=400)
                return
            removed = articles.pop(index)
            save_json(DATA_FILE, articles)
            self.send_json({"deleted": True, "removed": removed, "articles": articles})
            return
        self.send_json({"error": "not found"}, code=404)


def run_server():
    os.chdir(str(WEB_DIR))
    server = HTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutdown requested")
    finally:
        stop_crawler()
        server.server_close()


if __name__ == "__main__":
    run_server()
