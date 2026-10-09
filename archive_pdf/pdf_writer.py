from __future__ import annotations

import struct
from pathlib import Path


def jpeg_info(path: Path) -> tuple[int, int, int]:
    with path.open("rb") as stream:
        if stream.read(2) != b"\xff\xd8":
            raise ValueError(f"{path.name} não é uma imagem JPEG válida.")
        while True:
            byte = stream.read(1)
            if not byte:
                break
            if byte != b"\xff":
                continue
            marker = stream.read(1)
            while marker == b"\xff":
                marker = stream.read(1)
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) != 2:
                break
            length = struct.unpack(">H", length_bytes)[0]
            if marker and marker[0] in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                data = stream.read(6)
                if len(data) != 6:
                    break
                height, width = struct.unpack(">HH", data[1:5])
                components = data[5]
                return width, height, components
            stream.seek(max(0, length - 2), 1)
    raise ValueError(f"Não foi possível determinar as dimensões de {path.name}.")


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    width, height, _ = jpeg_info(path)
    return width, height


def _page_size(width: int, height: int) -> tuple[float, float]:
    longest = 842.0
    scale = longest / max(width, height)
    return round(width * scale, 3), round(height * scale, 3)


def _pdf_text(value: str) -> bytes:
    """Codifica texto Unicode como uma string hexadecimal UTF-16BE de PDF."""
    return b"<FEFF" + value.encode("utf-16-be").hex().upper().encode("ascii") + b">"


def create_pdf(jpeg_paths: list[Path], output_path: Path, title: str = "Arquivo digital") -> None:
    if not jpeg_paths:
        raise ValueError("É necessária pelo menos uma imagem para criar o PDF.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".part")
    object_count = 2 + len(jpeg_paths) * 3
    offsets = [0] * (object_count + 1)

    def write_object(stream, number: int, body: bytes) -> None:
        offsets[number] = stream.tell()
        stream.write(f"{number} 0 obj\n".encode("ascii"))
        stream.write(body)
        stream.write(b"\nendobj\n")

    with temp_path.open("wb") as pdf:
        pdf.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        write_object(pdf, 1, b"<< /Type /Catalog /Pages 2 0 R >>")
        kids = " ".join(f"{3 + index * 3} 0 R" for index in range(len(jpeg_paths)))
        write_object(pdf, 2, f"<< /Type /Pages /Kids [{kids}] /Count {len(jpeg_paths)} >>".encode("ascii"))

        for index, image_path in enumerate(jpeg_paths):
            page_obj = 3 + index * 3
            image_obj = page_obj + 1
            content_obj = page_obj + 2
            pixel_width, pixel_height, components = jpeg_info(image_path)
            color_space = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}.get(components)
            if color_space is None:
                raise ValueError(f"A imagem {image_path.name} tem um espaço de cor não suportado.")
            page_width, page_height = _page_size(pixel_width, pixel_height)
            resource_name = f"Im{index + 1}"
            page_body = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /XObject << /{resource_name} {image_obj} 0 R >> >> "
                f"/Contents {content_obj} 0 R >>"
            ).encode("ascii")
            write_object(pdf, page_obj, page_body)

            image_size = image_path.stat().st_size
            offsets[image_obj] = pdf.tell()
            pdf.write(f"{image_obj} 0 obj\n".encode("ascii"))
            pdf.write(
                (
                    f"<< /Type /XObject /Subtype /Image /Width {pixel_width} /Height {pixel_height} "
                    f"/ColorSpace {color_space} /BitsPerComponent 8 /Filter /DCTDecode /Length {image_size} >>\nstream\n"
                ).encode("ascii")
            )
            with image_path.open("rb") as image:
                while chunk := image.read(1024 * 1024):
                    pdf.write(chunk)
            pdf.write(b"\nendstream\nendobj\n")

            content = f"q\n{page_width} 0 0 {page_height} 0 0 cm\n/{resource_name} Do\nQ\n".encode("ascii")
            write_object(pdf, content_obj, f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"endstream")

        info_obj = object_count + 1
        offsets.append(pdf.tell())
        pdf.write(f"{info_obj} 0 obj\n<< /Title ".encode("ascii"))
        pdf.write(_pdf_text(title))
        pdf.write(b" /Creator (Arquivo PDF) >>\nendobj\n")
        xref_offset = pdf.tell()
        pdf.write(f"xref\n0 {info_obj + 1}\n".encode("ascii"))
        pdf.write(b"0000000000 65535 f \n")
        for number in range(1, info_obj + 1):
            pdf.write(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
        pdf.write(
            f"trailer\n<< /Size {info_obj + 1} /Root 1 0 R /Info {info_obj} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
                "ascii"
            )
        )
    temp_path.replace(output_path)
