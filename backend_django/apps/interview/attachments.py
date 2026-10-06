"""Files attached to an AI 助手 message: PDFs become text (scanned PDFs become page images), images go to the model.

Nothing is kept: files are read in memory, images and rendered pages live in a temporary directory for the length of
one generation, and the message only records each file's name and kind.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from .validation import InterviewError, extract_pdf

MAX_FILES = 6
MAX_BYTES = 8 * 1024 * 1024
TEXT_LIMIT = 24000  # characters of PDF text sent with one message, all files together
SCANNED_PAGES = 4  # a PDF without a text layer is rendered page by page (first pages only)
IMAGE_TYPES = {b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg", b"GIF8": ".gif"}


def _image_suffix(data):
    for magic, suffix in IMAGE_TYPES.items():
        if data.startswith(magic):
            return suffix
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ""


def _render_pages(data, folder, stem):
    """Pages of a scanned PDF as PNGs (pdftoppm), so the model can read them like photos."""
    executable = shutil.which("pdftoppm")
    if not executable:
        return []
    source = folder / f"{stem}.pdf"
    source.write_bytes(data)
    try:
        subprocess.run([executable, "-r", "110", "-png", "-f", "1", "-l", str(SCANNED_PAGES), str(source), str(folder / stem)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted(str(path) for path in folder.glob(f"{stem}-*.png"))


class Attachments:
    """Reads the uploads once; use as a context manager so the temporary images are removed afterwards."""

    def __init__(self, files):
        files = list(files or [])
        if len(files) > MAX_FILES:
            raise InterviewError(f"一次最多附 {MAX_FILES} 个文件。")
        self.folder = Path(tempfile.mkdtemp(prefix="iv-assistant-")) if files else None
        self.items, self.texts, self.images = [], [], []
        budget = TEXT_LIMIT
        try:
            for index, upload in enumerate(files):
                name = str(getattr(upload, "name", "") or f"file-{index + 1}")[:120]
                if getattr(upload, "size", 0) > MAX_BYTES:
                    raise InterviewError(f"「{name}」超过 8 MB。")
                data = upload.read(MAX_BYTES + 1)
                if data.startswith(b"%PDF"):
                    text = extract_pdf(data).strip()
                    if len(text) >= 40:
                        clipped = text[:max(0, budget)]
                        budget -= len(clipped)
                        self.texts.append((name, clipped))
                        self.items.append({"name": name, "kind": "pdf", "chars": len(text)})
                    else:  # no text layer: read it as page images
                        pages = _render_pages(data, self.folder, f"pdf{index}")
                        if not pages:
                            raise InterviewError(f"「{name}」没有可读取的文字，也无法转成图片。")
                        self.images += pages
                        self.items.append({"name": name, "kind": "pdf", "pages": len(pages), "scanned": True})
                    continue
                suffix = _image_suffix(data)
                if not suffix:
                    raise InterviewError(f"「{name}」不是 PDF 或图片（支持 PDF / PNG / JPG / WEBP / GIF）。")
                path = self.folder / f"image{index}{suffix}"
                path.write_bytes(data)
                self.images.append(str(path))
                self.items.append({"name": name, "kind": "image"})
        except Exception:
            self.close()
            raise

    def prompt_block(self, images_supported):
        """What the model reads about the files, appended to the latest user message."""
        if not self.items:
            return ""
        lines = ["", "ATTACHMENTS (the user's files for this message):"]
        for item in self.items:
            if item["kind"] == "image":
                lines.append(f"- image「{item['name']}」" + ("（attached as an image）" if images_supported else "（the current AI source cannot see images）"))
            elif item.get("scanned"):
                lines.append(f"- scanned PDF「{item['name']}」, {item['pages']} page image(s)" + ("" if images_supported else "（not readable by the current AI source）"))
        for name, text in self.texts:
            lines.append(f"--- PDF「{name}」text ---\n{text}\n--- end of「{name}」---")
        return "\n".join(lines)

    def close(self):
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
