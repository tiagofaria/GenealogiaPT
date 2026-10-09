from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DigitalPage:
    number: int
    name: str
    original_url: str
    thumbnail_url: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DocumentInfo:
    provider: str
    provider_label: str
    source_url: str
    title: str
    reference: str
    repository: str
    date_label: str
    pages: tuple[DigitalPage, ...]

    def to_dict(self, include_pages: bool = True) -> dict:
        result = asdict(self)
        result["page_count"] = len(self.pages)
        if not include_pages:
            result.pop("pages", None)
        return result


class ViewerAdapter(ABC):
    key = "base"
    label = "Desconhecido"

    @abstractmethod
    def supports(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def inspect(self, url: str) -> DocumentInfo:
        raise NotImplementedError
