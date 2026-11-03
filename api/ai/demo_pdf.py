"""Gerador mínimo de PDF (texto, Helvetica) usado para manuais demonstrativos e testes."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(pages: list[list[str]]) -> bytes:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(b"")  # /Pages, preenchido ao final
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    page_ids = []
    for lines in pages:
        stream = ["BT", "/F1 11 Tf", "14 TL", "50 790 Td"]
        for line in lines:
            stream.append(f"({_escape(line)}) Tj T*")
        stream.append("ET")
        data = "\n".join(stream).encode("cp1252", errors="replace")
        content = add(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
        page_ids.append(add(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>".encode()
        ))
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(output)


def wrap(text: str, width: int = 88) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines
