from pathlib import Path
from textwrap import wrap
from typing import Iterable, List


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 72
TOP_MARGIN = 730
LINE_HEIGHT = 14
MAX_CHARS = 92


def escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def lines_from_paragraphs(paragraphs: Iterable[str]) -> List[str]:
    lines: List[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            lines.append("")
            continue
        lines.extend(wrap(paragraph, width=MAX_CHARS))
        lines.append("")
    return lines


def write_simple_pdf(path: Path, title: str, paragraphs: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [title, ""] + lines_from_paragraphs(paragraphs)
    pages = [lines[index : index + 46] for index in range(0, len(lines), 46)]

    objects = []
    page_refs = []
    for page_index, page_lines in enumerate(pages, start=1):
        commands = ["BT", "/F1 11 Tf", f"{LEFT_MARGIN} {TOP_MARGIN} Td"]
        for line_index, line in enumerate(page_lines):
            if line_index:
                commands.append(f"0 -{LINE_HEIGHT} Td")
            font_size = 14 if page_index == 1 and line_index == 0 else 11
            commands.append(f"/F1 {font_size} Tf")
            commands.append(f"({escape_pdf_text(line)}) Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        content_number = len(objects) + 1
        page_number = len(objects) + 2
        objects.append(
            f"{content_number} 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream\nendobj\n"
        )
        objects.append(
            f"{page_number} 0 obj\n"
            f"<< /Type /Page /Parent 999 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Contents {content_number} 0 R /Resources << /Font << /F1 998 0 R >> >> >>\n"
            "endobj\n".encode("latin-1")
        )
        page_refs.append(f"{page_number} 0 R")

    font_object = b"998 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    pages_object = (
        f"999 0 obj\n<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>\nendobj\n"
    ).encode("latin-1")
    catalog_object = b"1000 0 obj\n<< /Type /Catalog /Pages 999 0 R >>\nendobj\n"
    all_objects = objects + [font_object, pages_object, catalog_object]

    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for obj in all_objects:
        offsets.append(len(output))
        output.extend(obj)

    xref_offset = len(output)
    max_object_number = 1000
    offset_map = {index + 1: offset for index, offset in enumerate(offsets[:-3])}
    offset_map[998] = offsets[-3]
    offset_map[999] = offsets[-2]
    offset_map[1000] = offsets[-1]

    output.extend(f"xref\n0 {max_object_number + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for object_number in range(1, max_object_number + 1):
        offset = offset_map.get(object_number, 0)
        status = "n" if offset else "f"
        generation = "00000" if offset else "65535"
        output.extend(f"{offset:010d} {generation} {status} \n".encode("latin-1"))
    output.extend(
        f"trailer\n<< /Size {max_object_number + 1} /Root 1000 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    )
    path.write_bytes(bytes(output))
