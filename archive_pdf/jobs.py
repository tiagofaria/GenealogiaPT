from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .adapters.base import DocumentInfo
from .net import DownloadCancelled, download_with_retries
from .pdf_writer import create_pdf


def parse_page_selection(text: str, page_count: int) -> list[int]:
    value = (text or "").strip()
    if not value:
        return list(range(1, page_count + 1))

    selected: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        if re.fullmatch(r"\d+", token):
            selected.add(int(token))
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if not match:
            raise ValueError("Usa intervalos como 1-25,30,42-50.")
        start, end = map(int, match.groups())
        if start > end:
            raise ValueError(f"O intervalo {token} está invertido.")
        selected.update(range(start, end + 1))

    if not selected:
        raise ValueError("Seleciona pelo menos uma página.")
    if min(selected) < 1 or max(selected) > page_count:
        raise ValueError(f"As páginas têm de estar entre 1 e {page_count}.")
    return sorted(selected)


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w\-. ]+", "", value, flags=re.UNICODE).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or "arquivo-digital")[:100]


@dataclass
class Job:
    id: str
    document: DocumentInfo
    selected_pages: list[int]
    quality: str
    jpeg_quality: int
    output_path: Path
    work_path: Path
    status: str = "queued"
    completed: int = 0
    message: str = "Na fila"
    error: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def total(self) -> int:
        return len(self.selected_pages)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "completed": self.completed,
            "total": self.total,
            "percent": round((self.completed / self.total) * 100, 1) if self.total else 0,
            "message": self.message,
            "error": self.error,
            "title": self.document.title,
            "quality": self.quality,
            "output_name": self.output_path.name,
            "download_url": f"/api/jobs/{self.id}/download" if self.status == "complete" else None,
            "can_resume": self.status in {"failed", "cancelled"},
        }


class JobManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.jobs_root = root / ".runtime" / "jobs"
        self.output_root = root / "output" / "pdf"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()
        self.worker_slots = threading.Semaphore(1)

    def create(
        self,
        document: DocumentInfo,
        pages: list[int],
        quality: str,
        jpeg_quality: int,
        output_name: str,
    ) -> Job:
        if quality not in {"original", "thumbnail"}:
            raise ValueError("A qualidade selecionada não é válida.")
        jpeg_quality = max(55, min(95, int(jpeg_quality)))
        job_id = uuid.uuid4().hex[:12]
        filename = safe_filename(output_name or f"{document.reference} - {document.title}") + ".pdf"
        output_path = self._unique_output_path(filename)
        job = Job(
            id=job_id,
            document=document,
            selected_pages=pages,
            quality=quality,
            jpeg_quality=jpeg_quality,
            output_path=output_path,
            work_path=self.jobs_root / job_id,
        )
        with self.lock:
            self.jobs[job_id] = job
        self._persist(job)
        self._start(job)
        return job

    def _unique_output_path(self, filename: str) -> Path:
        candidate = self.output_root / filename
        stem, suffix = candidate.stem, candidate.suffix
        number = 2
        with self.lock:
            reserved = {job.output_path for job in self.jobs.values()}
            while candidate.exists() or candidate in reserved:
                candidate = self.output_root / f"{stem} ({number}){suffix}"
                number += 1
        return candidate

    def get(self, job_id: str) -> Job:
        with self.lock:
            job = self.jobs.get(job_id)
        if not job:
            raise KeyError("Trabalho não encontrado.")
        return job

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status in {"queued", "downloading", "creating_pdf"}:
            job.cancel_event.set()
            job.message = "A cancelar…"
        return job

    def resume(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status not in {"failed", "cancelled"}:
            raise ValueError("Este trabalho não pode ser retomado neste momento.")
        job.cancel_event = threading.Event()
        job.status = "queued"
        job.error = ""
        job.message = "A retomar"
        self._persist(job)
        self._start(job)
        return job

    def _start(self, job: Job) -> None:
        threading.Thread(target=self._run, args=(job,), daemon=True, name=f"arquivo-pdf-{job.id}").start()

    def _run(self, job: Job) -> None:
        try:
            with self.worker_slots:
                if job.cancel_event.is_set():
                    raise DownloadCancelled
                job.status = "downloading"
                job.message = "A preparar as imagens"
                jpeg_dir = job.work_path / "jpeg"
                source_dir = job.work_path / "source"
                jpeg_dir.mkdir(parents=True, exist_ok=True)
                source_dir.mkdir(parents=True, exist_ok=True)
                magick = shutil.which("magick")
                if not magick:
                    raise RuntimeError("O ImageMagick não está instalado ou não foi encontrado no PATH.")

                pdf_images: list[Path] = []
                job.completed = 0
                for sequence, page_number in enumerate(job.selected_pages, start=1):
                    if job.cancel_event.is_set():
                        raise DownloadCancelled
                    page = job.document.pages[page_number - 1]
                    jpeg_path = jpeg_dir / f"{sequence:05d}.jpg"
                    pdf_images.append(jpeg_path)
                    if jpeg_path.exists() and jpeg_path.stat().st_size > 0:
                        job.completed = sequence
                        continue

                    job.message = f"A descarregar a página {sequence} de {job.total}"
                    source_path = source_dir / f"{sequence:05d}.img"
                    source_url = page.original_url if job.quality == "original" else page.thumbnail_url
                    download_with_retries(source_url, source_path, job.cancel_event)
                    self._convert_image(magick, source_path, jpeg_path, job.jpeg_quality)
                    source_path.unlink(missing_ok=True)
                    job.completed = sequence
                    self._persist(job)
                    time.sleep(0.12)

                if job.cancel_event.is_set():
                    raise DownloadCancelled
                job.status = "creating_pdf"
                job.message = "A criar o PDF"
                self._persist(job)
                create_pdf(pdf_images, job.output_path, title=job.document.title)
                job.status = "complete"
                job.message = "PDF concluído"
                self._persist(job)
        except DownloadCancelled:
            job.status = "cancelled"
            job.message = "Transferência interrompida. Pode ser retomada."
            self._persist(job)
        except Exception as exc:
            job.status = "failed"
            job.message = "Não foi possível concluir"
            job.error = str(exc)
            self._persist(job)

    @staticmethod
    def _convert_image(magick: str, source: Path, target: Path, quality: int) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".part.jpg")
        command = [
            magick,
            str(source) + "[0]",
            "-auto-orient",
            "-alpha",
            "remove",
            "-colorspace",
            "sRGB",
            "-strip",
            "-quality",
            str(quality),
            str(partial),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0 or not partial.exists():
            detail = (result.stderr or result.stdout or "erro desconhecido").strip()
            raise RuntimeError(f"Não foi possível converter uma imagem: {detail[:400]}")
        partial.replace(target)

    def _persist(self, job: Job) -> None:
        job.work_path.mkdir(parents=True, exist_ok=True)
        state_path = job.work_path / "state.json"
        state_path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
