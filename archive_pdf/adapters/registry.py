from __future__ import annotations

from .archeevo import ArcheevoAdapter
from .base import DocumentInfo, ViewerAdapter
from .digitarq import DigitarqAdapter


class UnsupportedViewerError(ValueError):
    pass


class AdapterRegistry:
    def __init__(self, adapters: list[ViewerAdapter] | None = None) -> None:
        self.adapters = adapters or [ArcheevoAdapter(), DigitarqAdapter()]

    def resolve(self, url: str) -> ViewerAdapter:
        for adapter in self.adapters:
            if adapter.supports(url):
                return adapter
        raise UnsupportedViewerError(
            "Ainda não reconhecemos este visualizador. Envia um exemplo para ser criado um novo adaptador."
        )

    def inspect(self, url: str) -> DocumentInfo:
        return self.resolve(url).inspect(url)

    def capabilities(self) -> list[dict]:
        return [
            {"key": "archeevo", "label": "Archeevo", "status": "available"},
            {"key": "digitarq", "label": "Digitarq", "status": "available"},
        ]
