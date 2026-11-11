"""Deterministic file decoding: bytes -> page-wise plain text.

Nothing here interprets content; uploaded text is treated purely as data and is
never executed, evaluated or used as instructions.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

from ..config import SurveyConfig
from ..models import CurriculumDocument

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/plain",
    ".csv": "text/csv",
}

RECOVERY = {
    "unsupported": "Supported formats are PDF, Word (.docx), plain text (.txt) and CSV. "
                   "You can also paste the module text, or add modules by hand on the review screen.",
    "too_large": "Try uploading only the pages that describe your modules, or paste the relevant text instead.",
    "empty": "No readable text was found. Paste the module descriptions instead, or add modules by hand.",
    "image_only": "This PDF appears to be scanned images, so there is no text to read. Scanned documents (OCR) "
                  "are not supported in this version and nothing has been extracted. Paste the text, upload a "
                  "text-based PDF or Word file, or add your modules by hand.",
    "error": "The file could not be read. It may be corrupted or password-protected. Paste the text instead, "
             "or add modules by hand.",
}


@dataclass
class DecodedText:
    document: CurriculumDocument
    pages: list[str] = field(default_factory=list)   # raw text; kept in memory only
    csv_rows: list[dict[str, str]] | None = None

    @property
    def ok(self) -> bool:
        return self.document.parse_status == "ok"

    @property
    def full_text(self) -> str:
        return "\n".join(self.pages)


def _doc(filename: str, data: bytes, media_type: str, status: str, message: str = "", **kw) -> CurriculumDocument:
    return CurriculumDocument(
        original_filename=Path(filename).name[:200],
        sha256=hashlib.sha256(data).hexdigest(),
        media_type=media_type,
        parse_status=status,
        message=message,
        **kw,
    )


def decode_text(text: str, name: str = "pasted text") -> DecodedText:
    data = text.encode("utf-8", errors="replace")
    if not text.strip():
        return DecodedText(_doc(name, data, "text/plain", "empty", RECOVERY["empty"]))
    pages = text.replace("\r\n", "\n").replace("\r", "\n").split("\f")
    return DecodedText(_doc(name, data, "text/plain", "ok", n_pages=len(pages), n_chars=len(text)), pages)


def decode_upload(filename: str, data: bytes, cfg: SurveyConfig) -> DecodedText:
    """Decode an uploaded file. Never raises: failures are reported in `document.parse_status`."""
    limits = cfg.uploads
    ext = Path(filename).suffix.lower()
    media = MEDIA_TYPES.get(ext, "application/octet-stream")
    if ext not in limits["accepted_extensions"]:
        return DecodedText(_doc(filename, data, media, "unsupported",
                                f"'{ext or 'unknown'}' files are not supported. " + RECOVERY["unsupported"]))
    if len(data) > limits["max_file_mb"] * 1024 * 1024:
        return DecodedText(_doc(filename, data, media, "too_large",
                                f"The file is larger than {limits['max_file_mb']} MB. " + RECOVERY["too_large"]))
    if not data:
        return DecodedText(_doc(filename, data, media, "empty", RECOVERY["empty"]))
    try:
        if ext == ".pdf":
            pages = _pdf_pages(data, limits["max_pages"])
        elif ext == ".docx":
            pages = _docx_pages(data)
        elif ext == ".csv":
            text = _decode_bytes(data)
            rows = list(csv.DictReader(io.StringIO(text)))
            doc = _doc(filename, data, media, "ok" if rows else "empty",
                       "" if rows else RECOVERY["empty"], n_pages=1, n_chars=len(text))
            return DecodedText(doc, [text], csv_rows=rows)
        else:
            pages = _decode_bytes(data).replace("\r\n", "\n").replace("\r", "\n").split("\f")
    except Exception as exc:  # corrupted / encrypted / not really that format
        return DecodedText(_doc(filename, data, media, "error", f"{RECOVERY['error']} ({type(exc).__name__})"))

    n_chars = sum(len(p.strip()) for p in pages)
    if ext == ".pdf" and pages and n_chars < limits["min_chars_per_page"] * len(pages):
        return DecodedText(_doc(filename, data, media, "image_only", RECOVERY["image_only"],
                                n_pages=len(pages), n_chars=n_chars))
    if n_chars == 0:
        return DecodedText(_doc(filename, data, media, "empty", RECOVERY["empty"], n_pages=len(pages)))
    if n_chars > limits["max_chars"]:
        return DecodedText(_doc(filename, data, media, "too_large",
                                "The document contains more text than this version processes. " + RECOVERY["too_large"],
                                n_pages=len(pages), n_chars=n_chars))
    return DecodedText(_doc(filename, data, media, "ok", n_pages=len(pages), n_chars=n_chars), pages)


def _decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _pdf_pages(data: bytes, max_pages: int) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("encrypted PDF")
    pages = []
    for i, page in enumerate(reader.pages):
        if i >= max_pages:
            break
        pages.append(page.extract_text() or "")
    return pages


def _docx_pages(data: bytes) -> list[str]:
    """Word has no reliable page breaks, so the whole document is one 'page'.

    Headings and list paragraphs are preserved as plain-text cues ("- " bullets),
    two-column table rows become "label: value" lines.
    """
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                lines.append("")
                continue
            style = (block.style.name or "").lower() if block.style is not None else ""
            if "list" in style or "bullet" in style:
                indent = "    " if any(ch in style for ch in ("2", "3")) else ""
                lines.append(f"{indent}- {text}")
            else:
                lines.append(text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = []
                for c in row.cells:
                    t = c.text.strip()
                    if t and (not cells or cells[-1] != t):   # merged cells repeat
                        cells.append(t)
                if len(cells) == 2 and "\n" not in cells[0]:
                    head, body = cells
                    body_lines = body.split("\n")
                    if len(body_lines) > 1:
                        lines.append(f"{head}:")
                        lines.extend(body_lines)
                    else:
                        lines.append(f"{head}: {body}")
                elif cells:
                    lines.append(" ".join(c.replace("\n", " ") for c in cells))
            lines.append("")
    return ["\n".join(lines)]
