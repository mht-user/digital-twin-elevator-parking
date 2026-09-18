"""
main.py
=========================================================================
LOP TRUNG GIAN (Backend API) giua Frontend (index.html) va 2 module
nghiep vu that su cua nhom:

  - Simulation Engineer  (SE): run_simulation.py            (cung cap o day)
  - Optimization Engineer(OE): optimization/optimizer.py    (goi qua se_bridge.py)


  Ca /api/simulation va /api/optimization deu di qua CUNG MOT
  SimulationEngineerBridge (optimization/se_bridge.py) - dam bao ca hai
  endpoint luon dung dung mot ban SE, khong the lech nhau. Muon them 1
  chi so nghiep vu moi, phai sua trong run_simulation.py (SE) hoac
  optimizer.py (OE), khong sua/tinh lai trong main.py.
CHAY:
    python3 main.py
    python3 main.py --port 9000 --dataset-dir /duong/dan/khac/Dataset

    (mac dinh: host 0.0.0.0, port 8000, Dataset/ va optimization/ nam
    cung cap voi main.py)

ENDPOINT:
    GET /api/health
    GET /api/simulation?scenario=&include_events=
    GET /api/optimization?scenario=&include_events=&max_moves=&top_k=&include_schedule=
    (chi tiet tham so/response: xem README.md muc 5, hoac goi GET /api/
     de xem danh sach route + mo ta ngan)
=========================================================================
"""

from __future__ import annotations

import argparse
import json
import logging
import socketserver
import sys
import threading
import urllib.parse
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from http.server import SimpleHTTPRequestHandler
from typing import Any, Callable

logger = logging.getLogger("main_api")


# =========================================================================
# 1. CAU HINH DUONG DAN
# =========================================================================

@dataclass(frozen=True)
class Paths:
    """Tap hop duong dan toi cac module SE/OE va Dataset. Co the ghi de
    bang tham so dong lenh (xem parse_args()) de test voi dataset khac."""

    base_dir: Path
    dataset_dir: Path
    optimization_dir: Path
    se_file: Path

    @classmethod
    def defaults(cls, base_dir: Path) -> "Paths":
        return cls(
            base_dir=base_dir,
            dataset_dir=base_dir / "Dataset",
            optimization_dir=base_dir / "optimization",
            se_file=base_dir / "run_simulation.py",
        )

    def check(self) -> None:
        """Kiem tra som cac duong dan bat buoc, bao loi ro rang ngay khi
        khoi dong thay vi de 1 request dau tien tinh co that bai kho hieu."""
        problems = []
        if not self.dataset_dir.is_dir():
            problems.append(f"Khong tim thay thu muc dataset: {self.dataset_dir}")
        if not self.optimization_dir.is_dir():
            problems.append(f"Khong tim thay thu muc optimization: {self.optimization_dir}")
        if not self.se_file.is_file():
            problems.append(f"Khong tim thay SE file: {self.se_file}")
        if problems:
            raise SystemExit(
                "Khong the khoi dong main.py, thieu duong dan:\n  - "
                + "\n  - ".join(problems)
            )


def _import_oe(paths: Paths):
    """Import 2 ham/lop cong khai cua OE tu optimization/. Import o day
    (khong o dau file) de co the chon optimization_dir tuy chinh qua CLI
    truoc khi import."""
    sys.path.insert(0, str(paths.optimization_dir))
    from se_bridge import SimulationEngineerBridge  # type: ignore
    from optimizer import optimize_multi_move  # type: ignore

    return SimulationEngineerBridge, optimize_multi_move


# =========================================================================
# 2. LOI API + TIEN ICH DOC QUERY PARAM (that chat - sai kieu la bao loi
#    ro rang thay vi am tham dung gia tri mac dinh)
# =========================================================================

class ApiError(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


def _get_str(query: dict, name: str, default: str, allowed: tuple[str, ...]) -> str:
    values = query.get(name)
    if not values:
        return default
    value = values[0].strip()
    if value not in allowed:
        raise ApiError(f"'{name}' phai la mot trong {allowed}, nhan duoc: '{value}'")
    return value


def _get_bool(query: dict, name: str, default: bool) -> bool:
    values = query.get(name)
    if not values:
        return default
    raw = values[0].strip().lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    raise ApiError(f"'{name}' phai la true/false, nhan duoc: '{values[0]}'")


def _get_int(query: dict, name: str, default: int, minimum: int | None = None) -> int:
    values = query.get(name)
    if not values:
        return default
    raw = values[0].strip()
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(f"'{name}' phai la so nguyen, nhan duoc: '{raw}'")
    if minimum is not None and value < minimum:
        raise ApiError(f"'{name}' phai >= {minimum}, nhan duoc: {value}")
    return value


# =========================================================================
# 3. LOP DIEU PHOI (goi dung ham cong khai cua SE/OE, khong tinh gi them)
# =========================================================================

class Backend:
    """Nam giu 1 SimulationEngineerBridge duy nhat + cache ket qua toi uu.

    Ca 2 endpoint /api/simulation va /api/optimization deu di qua cung
    mot `self.bridge`, dam bao chung luon dung chung mot SE.
    """

    def __init__(self, paths: Paths):
        self.paths = paths
        SimulationEngineerBridge, optimize_multi_move = _import_oe(paths)
        self._optimize_multi_move = optimize_multi_move
        self.bridge = SimulationEngineerBridge(paths.se_file)

        # Cache ket qua /api/optimization theo tham so goi. Optimization
        # cham (~10-15s tren dataset that voi max_moves=3) nen KHONG chay
        # lai neu da co cache cho dung tham so. Lock vi server chay da
        # luong (ThreadingTCPServer).
        self._optimize_cache: dict[tuple, dict] = {}
        self._optimize_lock = threading.Lock()

    # --- du lieu dung chung ------------------------------------------------

    def _load_dataset(self) -> dict:
        """Doc lai dataset moi lan goi (dataset nho, doc lai de luon phan
        anh dung file csv hien tai tren dia - khong cache dataset)."""
        return self.bridge.load_dataset(self.paths.dataset_dir)

    # --- /api/simulation -----------------------------------------------

    def simulate(self, scenario: str, include_events: bool) -> dict:
        data = self._load_dataset()
        results = self.bridge.simulate(
            schedule=data["schedule"],
            events=data["events"],
            parking=data["parking"],
            scenario=scenario,
            include_events=include_events,
        )

        # Dem so dong theo status co san trong ket qua SE - thong ke don
        # thuan (giong print_report() cua SE), KHONG phai chi so moi.
        summary = {
            "total_rows": len(results),
            "bottleneck_points": sum(1 for r in results if r["status"] == "BOTTLENECK"),
            "peak_points": sum(1 for r in results if r["status"] == "PEAK"),
            "ok_points": sum(1 for r in results if r["status"] == "OK"),
        }

        return {
            "engine": "run_simulation.py (Simulation Engineer, qua se_bridge.py)",
            "scenario": scenario,
            "include_events": include_events,
            "summary": summary,
            "results": results,
        }

    # --- /api/optimization -----------------------------------------------

    def optimize(
        self,
        scenario: str,
        include_events: bool,
        max_moves: int,
        top_k: int,
        include_schedule: bool,
    ) -> dict:
        cache_key = (scenario, include_events, max_moves, top_k)

        with self._optimize_lock:
            payload = self._optimize_cache.get(cache_key)

        if payload is None:
            logger.info("optimize: dang chay OE cho %s (chua co cache)...", cache_key)
            data = self._load_dataset()
            result = self._optimize_multi_move(
                bridge=self.bridge,
                schedule=data["schedule"],
                rooms=data["rooms"],
                parking=data["parking"],
                events=data["events"],
                scenario=scenario,
                include_events=include_events,
                max_moves=max_moves,
                top_k=top_k,
            )
            payload = {
                "engine": (
                    "optimization/optimizer.py (Optimization Engineer, "
                    "qua se_bridge.py -> run_simulation.py)"
                ),
                "scenario": result.scenario,
                "include_events": result.include_events,
                "max_moves": result.max_moves,
                "moves_applied": len(result.moves),
                "stop_reason": result.stop_reason,
                "total_evaluated_candidates": result.total_evaluated_candidates,
                "total_improving_candidates": result.total_improving_candidates,
                "before": result.baseline_metrics,
                "after": result.final_metrics,
                "moves": result.moves,
                "_optimized_schedule": result.optimized_schedule,
            }
            with self._optimize_lock:
                self._optimize_cache[cache_key] = payload
            logger.info("optimize: xong, da cache cho %s", cache_key)
        else:
            logger.info("optimize: tra tu cache cho %s", cache_key)

        # Cache luon giu ban day du; chi loc truong lich luc tra ve tuy
        # include_schedule cua tung request.
        response = {k: v for k, v in payload.items() if k != "_optimized_schedule"}
        if include_schedule:
            response["optimized_schedule"] = payload["_optimized_schedule"]
        return response


# =========================================================================
# 4. ROUTE  (route table tach rieng khoi HTTP handler, de test/doc de hon)
# =========================================================================

RouteHandler = Callable[[Backend, dict], dict]


def route_health(backend: Backend, query: dict) -> dict:
    return {"status": "ok"}


def route_index(backend: Backend, query: dict) -> dict:
    return {
        "service": "Digital Twin Lite - Backend API trung gian",
        "routes": {
            "/api/health": "Kiem tra server con song.",
            "/api/simulation": (
                "GET scenario=Normal|Worst (mac dinh Normal), "
                "include_events=true|false (mac dinh true). "
                "Goi thang SE, tra nguyen ket qua mo phong."
            ),
            "/api/optimization": (
                "GET scenario=Normal|Worst, include_events=true|false, "
                "max_moves=<int, mac dinh 3>, top_k=<int, mac dinh 10>, "
                "include_schedule=true|false (mac dinh false). "
                "Goi thang OE (qua SE), tra before/after + danh sach move."
            ),
        },
    }


def route_simulation(backend: Backend, query: dict) -> dict:
    scenario = _get_str(query, "scenario", "Normal", ("Normal", "Worst"))
    include_events = _get_bool(query, "include_events", True)
    return backend.simulate(scenario, include_events)


def route_optimization(backend: Backend, query: dict) -> dict:
    scenario = _get_str(query, "scenario", "Normal", ("Normal", "Worst"))
    include_events = _get_bool(query, "include_events", True)
    max_moves = _get_int(query, "max_moves", 3, minimum=1)
    top_k = _get_int(query, "top_k", 10, minimum=1)
    include_schedule = _get_bool(query, "include_schedule", False)
    return backend.optimize(scenario, include_events, max_moves, top_k, include_schedule)


ROUTES: dict[str, RouteHandler] = {
    "/api": route_index,
    "/api/": route_index,
    "/api/health": route_health,
    "/api/simulation": route_simulation,
    "/api/optimization": route_optimization,
}


# =========================================================================
# 5. HTTP HANDLER  (rat mong: parse query -> goi route -> tra JSON)
# =========================================================================

def make_handler(backend: Backend) -> type[SimpleHTTPRequestHandler]:
    """Tao handler class co gan san `backend` (SimpleHTTPRequestHandler
    khong cho truyen tham so qua __init__ mot cach thuan tien, nen dung
    class attribute qua closure nay)."""

    class ApiHandler(SimpleHTTPRequestHandler):
        server_backend = backend

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            logger.info("%s - %s", self.address_string(), fmt % args)

        def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # CORS preflight
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            handler = ROUTES.get(parsed.path)

            if handler is None:
                if parsed.path.startswith("/api"):
                    self._send_json(
                        {"error": f"Khong co route: {parsed.path}"},
                        status=HTTPStatus.NOT_FOUND,
                    )
                    return
                # Khong phai /api/* -> phuc vu file tinh (index.html, ...)
                super().do_GET()
                return

            query = urllib.parse.parse_qs(parsed.query)
            try:
                payload = handler(self.server_backend, query)
                self._send_json(payload)
            except ApiError as exc:
                self._send_json({"error": str(exc)}, status=exc.status)
            except FileNotFoundError as exc:
                # Vi du: Dataset/*.csv thieu file
                self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
            except Exception as exc:  # loi du lieu/SE/OE - tra ro rang, khong treo
                logger.exception("Loi khi xu ly %s", parsed.path)
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    return ApiHandler


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Xu ly nhieu request song song - de /api/simulation (nhanh) khong
    bi chan boi 1 /api/optimization dang chay (~10-15s) o request khac."""

    allow_reuse_address = True
    daemon_threads = True


# =========================================================================
# 6. CLI / ENTRYPOINT
# =========================================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Digital Twin Lite - Backend API trung gian (SE/OE)."
    )
    parser.add_argument("--host", default="0.0.0.0", help="Dia chi bind (mac dinh 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Cong lang nghe (mac dinh 8000)")
    parser.add_argument("--dataset-dir", type=Path, default=base_dir / "Dataset")
    parser.add_argument("--optimization-dir", type=Path, default=base_dir / "optimization")
    parser.add_argument("--se-file", type=Path, default=base_dir / "run_simulation.py")
    parser.add_argument("-v", "--verbose", action="store_true", help="In log muc DEBUG")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    paths = Paths(
        base_dir=Path(__file__).resolve().parent,
        dataset_dir=args.dataset_dir.resolve(),
        optimization_dir=args.optimization_dir.resolve(),
        se_file=args.se_file.resolve(),
    )
    paths.check()

    backend = Backend(paths)
    handler_cls = make_handler(backend)

    with ThreadingTCPServer((args.host, args.port), handler_cls) as httpd:
        logger.info("Backend API dang chay tai http://%s:%s", args.host, args.port)
        logger.info("  Dataset      : %s", paths.dataset_dir)
        logger.info("  Optimization : %s", paths.optimization_dir)
        logger.info("  SE file      : %s", paths.se_file)
        logger.info("Route: GET /api  /api/health  /api/simulation  /api/optimization")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Da dung server.")


if __name__ == "__main__":
    main()
