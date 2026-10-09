from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from archive_pdf.adapters import AdapterRegistry, UnsupportedViewerError
from archive_pdf.jobs import JobManager, parse_page_selection

ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
REGISTRY = AdapterRegistry()
JOBS = JobManager(ROOT)
INSPECTIONS: dict[str, object] = {}


class AppHandler(BaseHTTPRequestHandler):
    server_version = "ArquivoPDF/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/providers":
            return self.send_json({"providers": REGISTRY.capabilities()})
        if path.startswith("/api/jobs/"):
            return self.handle_job_get(path)
        return self.serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/api/inspect":
                return self.inspect_document(payload)
            if path == "/api/jobs":
                return self.create_job(payload)
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job_id = path.split("/")[3]
                return self.send_json(JOBS.cancel(job_id).to_dict())
            if path.startswith("/api/jobs/") and path.endswith("/resume"):
                job_id = path.split("/")[3]
                return self.send_json(JOBS.resume(job_id).to_dict())
            self.send_error_json(HTTPStatus.NOT_FOUND, "Endereço não encontrado.")
        except (ValueError, UnsupportedViewerError, NotImplementedError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except KeyError as exc:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(exc).strip("'"))
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def inspect_document(self, payload: dict) -> None:
        url = str(payload.get("url") or "").strip()
        document = REGISTRY.inspect(url)
        token = document.source_url
        INSPECTIONS[token] = document
        result = document.to_dict(include_pages=False)
        result["inspection_token"] = token
        self.send_json(result)

    def create_job(self, payload: dict) -> None:
        token = str(payload.get("inspection_token") or "")
        document = INSPECTIONS.get(token)
        if document is None:
            raise ValueError("Analisa novamente o endereço antes de iniciar.")
        pages = parse_page_selection(str(payload.get("pages") or ""), len(document.pages))
        job = JOBS.create(
            document=document,
            pages=pages,
            quality=str(payload.get("quality") or "original"),
            jpeg_quality=int(payload.get("jpeg_quality") or 85),
            output_name=str(payload.get("output_name") or ""),
        )
        self.send_json(job.to_dict(), status=HTTPStatus.ACCEPTED)

    def handle_job_get(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) < 3:
            return self.send_error_json(HTTPStatus.NOT_FOUND, "Trabalho não encontrado.")
        try:
            job = JOBS.get(parts[2])
        except KeyError as exc:
            return self.send_error_json(HTTPStatus.NOT_FOUND, str(exc).strip("'"))
        if len(parts) == 4 and parts[3] == "download":
            if job.status != "complete" or not job.output_path.exists():
                return self.send_error_json(HTTPStatus.CONFLICT, "O PDF ainda não está disponível.")
            return self.send_file(job.output_path, download_name=job.output_path.name)
        self.send_json(job.to_dict())

    def serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else unquote(path.lstrip("/"))
        candidate = (STATIC_ROOT / relative).resolve()
        try:
            candidate.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            return self.send_error_json(HTTPStatus.FORBIDDEN, "Acesso recusado.")
        if not candidate.is_file():
            return self.send_error_json(HTTPStatus.NOT_FOUND, "Ficheiro não encontrado.")
        self.send_file(candidate)

    def send_file(self, path: Path, download_name: str | None = None) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        if download_name:
            ascii_name = download_name.encode("ascii", "ignore").decode("ascii") or "documento.pdf"
            self.send_header("Content-Disposition", f'attachment; filename="{ascii_name}"')
        self.send_header("Cache-Control", "no-store" if download_name else "no-cache")
        self.end_headers()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                self.wfile.write(chunk)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("Pedido inválido.")
        try:
            result = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Pedido inválido.") from exc
        if not isinstance(result, dict):
            raise ValueError("Pedido inválido.")
        return result

    def send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Converte visualizadores de arquivo em PDF.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    address = f"http://{args.host}:{args.port}"
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Arquivo PDF disponível em {address}")
    print("Para terminar, fecha esta janela ou prime Ctrl+C.")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAplicação terminada.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
