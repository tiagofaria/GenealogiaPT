from __future__ import annotations

from urllib.parse import urlparse

from .base import DocumentInfo, ViewerAdapter


class DigitarqAdapter(ViewerAdapter):
    """Ponto de extensão para uma próxima versão.

    A deteção já existe para a interface explicar corretamente que o endereço é
    conhecido, sem fingir que consegue extrair imagens antes de o adaptador estar
    implementado e testado em diferentes instalações Digitarq.
    """

    key = "digitarq"
    label = "Digitarq"

    def supports(self, url: str) -> bool:
        parsed = urlparse(url)
        haystack = f"{parsed.hostname or ''}{parsed.path}".lower()
        return "digitarq" in haystack or "/details?" in url.lower()

    def inspect(self, url: str) -> DocumentInfo:
        raise NotImplementedError(
            "Este endereço parece ser Digitarq. O adaptador está preparado na arquitetura, "
            "mas ainda precisa de ser implementado e testado com um exemplo real."
        )
