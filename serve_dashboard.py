"""
serve_dashboard.py
=========================================================================
Backend nhe phuc vu index.html. 2 endpoint:

  GET /api/dashboard?scenario=Normal|Worst&include_events=true|false
      -> heatmap + KPI + parking_view CUA LICH HIEN TAI (nhanh, <1s).

  GET /api/optimize?scenario=Normal|Worst&include_events=true|false&max_moves=3
      -> goi optimizer THAT (optimize_multi_move trong optimize/), tra ve
      before/after that (khong bia so). CHAM lan dau (~10s tren dataset
      that voi max_moves=3, da do gio thuc te) nen KET QUA DUOC CACHE
      trong bo nho theo (scenario, include_events, max_moves) - goi lai
      cung tham so se tra ngay tu cache, khong chay lai optimizer.
      Neu optimize/ chua ton tai, tra {"available": false, "reason": ...}
      thay vi crash hoac bia du lieu.

Chay: python3 serve_dashboard.py  (dat cung cap voi run_simulation.py,
dashboard_data.py, index.html, va thu muc optimize/)
=========================================================================
"""

from __future__ import annotations

import json
import socketserver
import urllib.parse
from http.server import SimpleHTTPRequestHandler

from dashboard_data import build_dashboard_payload, build_optimization_payload

PORT = 8080

# Cache ket qua /api/optimize trong bo nho tien trinh - khoa la
# (scenario, include_events, max_moves). Mat khi restart server (chap
# nhan duoc, day la backend demo nhe, khong phai production service).
_optimize_cache: dict = {}


def _bool_param(query: dict, name: str, default: bool) -> bool:
    raw = query.get(name, [str(default).lower()])[0].strip().lower()
    return raw not in ("false", "0", "no")


class DashboardHandler(SimpleHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/dashboard":
            scenario = query.get("scenario", ["Normal"])[0]
            if scenario not in ("Normal", "Worst"):
                scenario = "Normal"
            include_events = _bool_param(query, "include_events", True)

            try:
                payload = build_dashboard_payload(
                    scenario=scenario, include_events=include_events
                )
                self._send_json(payload)
            except Exception as exc:  # dataset loi, ... - tra loi ro rang thay vi treo
                self._send_json({"error": str(exc)}, status=500)
            return

        if parsed.path == "/api/optimize":
            scenario = query.get("scenario", ["Normal"])[0]
            if scenario not in ("Normal", "Worst"):
                scenario = "Normal"
            include_events = _bool_param(query, "include_events", True)
            try:
                max_moves = int(query.get("max_moves", ["3"])[0])
            except ValueError:
                max_moves = 3

            cache_key = (scenario, include_events, max_moves)
            if cache_key not in _optimize_cache:
                print(
                    f"[optimize] dang chay optimize_multi_move cho {cache_key} "
                    "(lan dau se mat vai chuc giay)..."
                )
                try:
                    _optimize_cache[cache_key] = build_optimization_payload(
                        scenario=scenario,
                        include_events=include_events,
                        max_moves=max_moves,
                    )
                except Exception as exc:
                    self._send_json({"available": False, "reason": str(exc)}, status=500)
                    return
                print(f"[optimize] xong, da cache {cache_key}")
            else:
                print(f"[optimize] tra tu cache cho {cache_key}")

            self._send_json(_optimize_cache[cache_key])
            return

        super().do_GET()


class ReusableTCPServer(socketserver.TCPServer):
    # Cho phep restart server ngay khong bi "Address already in use"
    # (loi da gap thuc te khi test - port giu o trang thai TIME_WAIT).
    allow_reuse_address = True


if __name__ == "__main__":
    with ReusableTCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"Server dashboard dang chay tai: http://localhost:{PORT}")
        print("Mo trinh duyet truy cap duong dan tren de xem Dashboard.")
        print("Luu y: /api/optimize lan goi dau cho moi to hop tham so se mat")
        print("khoang 10-15s (chay optimizer that) - cac lan sau tra tu cache.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDa dung server.")
