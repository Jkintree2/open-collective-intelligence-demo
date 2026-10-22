"""Small PDFs built by hand for the offline tests and fixtures: text pages, or pages that are only a picture
(as a scanned document is). Run as a script to write tests/fixtures/pdfs/ again."""

from __future__ import annotations

from pathlib import Path


def _escape(text: str) -> bytes:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", "replace")


def _stream(header: str, data: bytes) -> bytes:
    return f"<< {header} /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"


def make_pdf(pages: list[str], *, title: str | None = None, created: str | None = None,
             modified: str | None = None, pictures: bool = False) -> bytes:
    """One page per entry of `pages` (lines split on newlines). `created` and `modified` are PDF dates
    ("D:20240314120000Z"). With `pictures`, every page is an image and holds no text at all."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    image = add(_stream("/Type /XObject /Subtype /Image /Width 8 /Height 8 /ColorSpace /DeviceGray /BitsPerComponent 8",
                        bytes(range(0, 256, 4)))) if pictures else 0
    tree = add(b"")
    kids = []
    for text in pages:
        if pictures:
            content = b"q 500 0 0 700 50 50 cm /Im1 Do Q"
            resources = f"<< /XObject << /Im1 {image} 0 R >> >>"
        else:
            lines = b" T* ".join(b"(" + _escape(line) + b") Tj" for line in text.split("\n"))
            content = b"BT /F1 11 Tf 14 TL 50 750 Td " + lines + b" ET"
            resources = f"<< /Font << /F1 {font} 0 R >> >>"
        stream = add(_stream("", content))
        kids.append(add(f"<< /Type /Page /Parent {tree} 0 R /MediaBox [0 0 612 792] /Resources {resources} "
                        f"/Contents {stream} 0 R >>".encode()))
    objects[tree - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    catalog = add(f"<< /Type /Catalog /Pages {tree} 0 R >>".encode())
    info_parts = [(b"/Title (" + _escape(title) + b")") if title else b"",
                  f"/CreationDate ({created})".encode() if created else b"",
                  f"/ModDate ({modified})".encode() if modified else b""]
    info = add(b"<< " + b" ".join(p for p in info_parts if p) + b" >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


REPORT = [
    "Coastal Flood Resilience Review 2024\nA report of the Department of Coastal Affairs",
    "Summary of findings\nThe review surveyed forty coastal councils between 2019 and 2023.\n"
    "Councils that combined sea walls with restored salt marsh saw flood damage fall by a third.\n"
    "Sea walls alone did not reduce flood damage over the period.",
]


def write_fixtures(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "flood_report.pdf").write_bytes(make_pdf(REPORT, title="Coastal Flood Resilience Review 2024",
                                                       created="D:20240611093000Z"))
    (folder / "scanned.pdf").write_bytes(make_pdf(["", ""], title="Scanned council minutes", pictures=True))


if __name__ == "__main__":
    write_fixtures(Path(__file__).parent / "fixtures" / "pdfs")
