from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse

from .base import DigitalPage, DocumentInfo, ViewerAdapter
from ..net import request_json


class DigitarqAdapter(ViewerAdapter):
    key = "digitarq"
    label = "Digitarq"
    _viewer_pattern = re.compile(
        r"/fileViewer/(?P<id>[0-9a-f]{32}|[0-9a-f-]{36})(?:/|$)",
        re.IGNORECASE,
    )
    _page_size = 500

    def supports(self, url: str) -> bool:
        parsed = urlparse(url)
        return bool(self._viewer_pattern.search(parsed.path))

    def inspect(self, url: str) -> DocumentInfo:
        parsed = urlparse(url)
        match = self._viewer_pattern.search(parsed.path)
        if not match:
            raise ValueError("Este endereço não parece ser um visualizador Digitarq válido.")

        document_id = match.group("id")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        metadata = request_json(f"{origin}/api/docs/details/{document_id}")
        if not isinstance(metadata, dict):
            raise RuntimeError("A estrutura de metadados devolvida por este Digitarq não é reconhecida.")

        files = self._fetch_all_files(origin, document_id)
        pages: list[DigitalPage] = []
        for item in files:
            file_id = str(item.get("id") or "").strip()
            file_type = str(item.get("type") or "").upper()
            if not file_id or (file_type and file_type != "IMAGE"):
                continue
            pages.append(
                DigitalPage(
                    number=len(pages) + 1,
                    name=str(item.get("name") or f"pagina-{len(pages) + 1:04d}"),
                    original_url=f"{origin}/api/rdigital/dissemination?{urlencode({'fileId': file_id})}",
                    thumbnail_url=f"{origin}/api/rdigital/thumb?{urlencode({'fileId': file_id})}",
                )
            )

        if not pages:
            raise RuntimeError("O documento não contém imagens públicas para descarregar.")

        title = self._first_value(metadata.get("titles")) or f"Documento {document_id}"
        reference = self._nested_value(metadata.get("referenceCode")) or self._text(metadata.get("value")) or document_id
        repository = self._nested_value(metadata.get("holder")) or self._text(metadata.get("archiveCode")) or parsed.hostname or "Arquivo"
        date_label = self._format_dates(metadata.get("dateInitial"), metadata.get("dateFinal"))
        selected_file = parse_qs(parsed.query).get("selectedFile", [str(files[0].get("id") or "")])[0]
        query = urlencode(
            {
                "isRepresentation": "false",
                "selectedFile": selected_file,
                "fileType": "IMAGE",
            }
        )

        return DocumentInfo(
            provider=self.key,
            provider_label=self.label,
            source_url=f"{origin}/fileViewer/{document_id}?{query}",
            title=title,
            reference=reference,
            repository=repository,
            date_label=date_label,
            pages=tuple(pages),
        )

    def _fetch_all_files(self, origin: str, document_id: str) -> list[dict]:
        files: list[dict] = []
        total: int | None = None
        from_index = 0

        while total is None or from_index < total:
            query = urlencode({"max": self._page_size, "fromIndex": from_index})
            payload = request_json(f"{origin}/api/rdigital/{document_id}?{query}")
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise RuntimeError("A lista de objetos digitais devolvida pelo Digitarq não é reconhecida.")
            batch = [item for item in payload["results"] if isinstance(item, dict)]
            if total is None:
                try:
                    total = max(0, int(payload.get("total", len(batch))))
                except (TypeError, ValueError):
                    total = len(batch)
            files.extend(batch)
            if not batch:
                break
            from_index += len(batch)

        return files

    @staticmethod
    def _text(value: object) -> str:
        return str(value).strip() if value is not None else ""

    @classmethod
    def _nested_value(cls, value: object) -> str:
        return cls._text(value.get("value")) if isinstance(value, dict) else ""

    @classmethod
    def _first_value(cls, value: object) -> str:
        if not isinstance(value, list):
            return ""
        attributed = next(
            (
                item
                for item in value
                if isinstance(item, dict)
                and isinstance(item.get("type"), dict)
                and str(item["type"].get("value") or "").upper() == "ATTRIBUTED"
            ),
            None,
        )
        candidate = attributed or next((item for item in value if isinstance(item, dict)), None)
        return cls._nested_value(candidate)

    @classmethod
    def _format_dates(cls, initial: object, final: object) -> str:
        def year(value: object) -> str:
            text = cls._nested_value(value)
            return text[:4] if len(text) >= 4 and text[:4].isdigit() else ""

        start, end = year(initial), year(final)
        if start and end and start != end:
            return f"{start}–{end}"
        return start or end
