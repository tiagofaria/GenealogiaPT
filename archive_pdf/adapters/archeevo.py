from __future__ import annotations

import re
from urllib.parse import quote, urlparse

from .base import DigitalPage, DocumentInfo, ViewerAdapter
from ..net import request_json


class ArcheevoAdapter(ViewerAdapter):
    key = "archeevo"
    label = "Archeevo"
    _description_pattern = re.compile(r"/viewer/descriptions/(?P<id>\d+)(?:/|$)", re.IGNORECASE)

    def supports(self, url: str) -> bool:
        return bool(self._description_pattern.search(urlparse(url).path))

    def inspect(self, url: str) -> DocumentInfo:
        parsed = urlparse(url)
        match = self._description_pattern.search(parsed.path)
        if not match:
            raise ValueError("Este endereço não parece ser um visualizador Archeevo válido.")

        description_id = match.group("id")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        metadata = request_json(f"{origin}/api/descriptions/{description_id}")
        digital_objects = request_json(f"{origin}/api/descriptions/{description_id}/digitalobjects")

        if not isinstance(metadata, dict) or not isinstance(digital_objects, list):
            raise RuntimeError("A estrutura devolvida por este Archeevo não é reconhecida.")

        files: list[dict] = []
        for representation in digital_objects:
            if isinstance(representation, dict) and isinstance(representation.get("Files"), list):
                files.extend(item for item in representation["Files"] if isinstance(item, dict))

        pages: list[DigitalPage] = []
        for index, item in enumerate(files, start=1):
            original_id = item.get("DisseminationURL") or item.get("OriginalURL")
            thumbnail_id = item.get("ThumbnailURL") or original_id
            if not original_id:
                continue
            pages.append(
                DigitalPage(
                    number=index,
                    name=str(item.get("Name") or f"pagina-{index:04d}"),
                    original_url=self._storage_url(origin, str(original_id)),
                    thumbnail_url=self._storage_url(origin, str(thumbnail_id)),
                )
            )

        if not pages:
            raise RuntimeError("O documento não contém imagens públicas para descarregar.")

        title = self._text(metadata.get("UnitTitle")) or f"Documento {description_id}"
        reference = self._text(metadata.get("CompleteUnitId")) or str(description_id)
        repository = self._text(metadata.get("Repository")) or parsed.hostname or "Arquivo"
        date_label = self._format_dates(metadata.get("UnitDateInitial"), metadata.get("UnitDateFinal"))
        canonical_url = f"{origin}/viewer/descriptions/{description_id}"

        return DocumentInfo(
            provider=self.key,
            provider_label=self.label,
            source_url=canonical_url,
            title=title,
            reference=reference,
            repository=repository,
            date_label=date_label,
            pages=tuple(pages),
        )

    @staticmethod
    def _storage_url(origin: str, object_id: str) -> str:
        return f"{origin}/api/storage/storageobject?objectId={quote(object_id, safe='')}"

    @staticmethod
    def _text(value: object) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _format_dates(initial: object, final: object) -> str:
        def year(value: object) -> str:
            text = str(value or "")
            return text[:4] if len(text) >= 4 and text[:4].isdigit() else ""

        start, end = year(initial), year(final)
        if start and end and start != end:
            return f"{start}–{end}"
        return start or end
