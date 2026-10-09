from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

USER_AGENT = "ArquivoPDF/0.1 (+aplicacao local de investigacao genealogica)"


class DownloadCancelled(Exception):
    pass


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("O endereço tem de começar por http:// ou https://.")

    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Não foi possível encontrar o servidor indicado.") from exc

    for address in {item[4][0] for item in addresses}:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Por segurança, só são permitidos servidores públicos.")


def request_bytes(url: str, timeout: int = 45) -> tuple[bytes, str]:
    validate_public_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers.get_content_type()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"O arquivo respondeu com o erro HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Não foi possível contactar o arquivo: {exc.reason}") from exc


def request_json(url: str) -> object:
    payload, _ = request_bytes(url)
    try:
        return json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("O arquivo devolveu uma resposta que não foi possível interpretar.") from exc


def download_with_retries(url: str, target: Path, cancel_event, attempts: int = 4) -> None:
    validate_public_url(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")

    for attempt in range(1, attempts + 1):
        if cancel_event.is_set():
            raise DownloadCancelled
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
            with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
                while True:
                    if cancel_event.is_set():
                        raise DownloadCancelled
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
            partial.replace(target)
            return
        except DownloadCancelled:
            partial.unlink(missing_ok=True)
            raise
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            partial.unlink(missing_ok=True)
            if attempt == attempts:
                raise RuntimeError(f"Falha ao transferir uma imagem após {attempts} tentativas: {exc}") from exc
            time.sleep(2 ** (attempt - 1))
