"""Telefon tarayicisi icin hafif Borsa Analiz web sunucusu."""

from __future__ import annotations

import argparse
import json
import math
import socket
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "mobile_web"


def normalize_symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if symbol.endswith(".IS"):
        symbol = symbol[:-3]
    if not (3 <= len(symbol) <= 6 and symbol.replace("_", "").isalnum()):
        raise ValueError("3-6 karakterli geçerli bir BIST hisse kodu girin.")
    return f"{symbol}.IS"


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "item"):
        return json_safe(value.item())
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def analyze(symbol: str) -> dict:
    normalized = normalize_symbol(symbol)
    from borsa_tarayici import teknik_analiz

    result = teknik_analiz(normalized, "TEK HİSSE")
    if not result:
        raise RuntimeError("Analiz için yeterli veya güncel fiyat verisi alınamadı.")
    return json_safe(result)


class MobileHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def _json(self, data: dict, status=HTTPStatus.OK):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json({"ok": True, "service": "Borsa Analiz Mobil"})
            return
        if path.startswith("/api/"):
            self._json({"ok": False, "error": "Bulunamadı."}, HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/analyze":
            self._json({"ok": False, "error": "Bulunamadı."}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise ValueError("Geçersiz istek.")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            result = analyze(body.get("symbol", ""))
            self._json({"ok": True, "result": result})
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Borsa Analiz mobil web arayüzü")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), MobileHandler)
    print("Borsa Analiz Mobil hazır.")
    print(f"Bilgisayar: http://127.0.0.1:{args.port}")
    print(f"Telefon (aynı Wi-Fi): http://{local_ip()}:{args.port}")
    print("Durdurmak için Ctrl+C kullanın.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu durduruldu.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
