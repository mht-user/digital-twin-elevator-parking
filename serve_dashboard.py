"""
serve_dashboard.py
Chạy backend nhẹ phục vụ giao diện Dashboard.
Sử dụng dữ liệu trực tiếp từ pipeline dashboard_data.py của nhóm.
Hỗ trợ kịch bản (Normal/Worst), luồng xe (checkin/checkout), và tính năng bật/tắt sự kiện (include_events).
"""
from http.server import SimpleHTTPRequestHandler
import json
import socketserver
import urllib.parse
from dashboard_data import build_dashboard_payload

PORT = 8080

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/dashboard"):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            scenario = query.get("scenario", ["Normal"])[0]
            if scenario not in ("Normal", "Worst"):
                scenario = "Normal"

            direction = query.get("direction", ["checkin"])[0]

            include_events_str = query.get("include_events", ["true"])[0].lower()
            include_events = include_events_str not in ("false", "0", "no")

            payload = build_dashboard_payload(scenario=scenario, include_events=include_events)
            payload["direction"] = direction

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        else:
            super().do_GET()

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"Server dashboard đang chạy tại: http://localhost:{PORT}")
        print("Mở trình duyệt truy cập đường dẫn trên để xem Dashboard.")
        httpd.serve_forever()
