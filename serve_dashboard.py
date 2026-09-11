"""
serve_dashboard.py
Chạy backend nhẹ phục vụ giao diện Dashboard.
Sử dụng dữ liệu trực tiếp từ pipeline dashboard_data.py của nhóm.
"""
from http.server import SimpleHTTPRequestHandler
import json
import socketserver
from dashboard_data import build_dashboard_payload

PORT = 8080

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/dashboard"):
            scenario = "Normal"
            direction = "checkin"
            if "scenario=Worst" in self.path:
                scenario = "Worst"
            if "direction=checkout" in self.path:
                direction = "checkout"
            
            payload = build_dashboard_payload(scenario=scenario, direction=direction)
            
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
