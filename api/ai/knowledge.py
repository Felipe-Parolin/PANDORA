"""Indexação de manuais (PDF) em trechos pesquisáveis."""
import logging
import re

from django.db import transaction

from .models import ManualChunk, ManualIndex

logger = logging.getLogger(__name__)

MAX_PAGES = 300
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
INDEXABLE_CATEGORIES = ("MANUAL", "DOCUMENT")


def is_indexable(media) -> bool:
    return bool(media.file and media.category in INDEXABLE_CATEGORIES and media.file.name.lower().endswith(".pdf"))


def split_text(text: str, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP) -> list[str]:
    """Divide em trechos respeitando, quando possível, fim de frase."""
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf_pages(file_obj) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(file_obj)
    pages = []
    for page in list(reader.pages)[:MAX_PAGES]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # página corrompida não deve derrubar a indexação inteira
            pages.append("")
    return pages


def index_media(media) -> ManualIndex:
    """(Re)indexa um PDF; é idempotente e registra o resultado em ``ManualIndex``."""
    status, error, pages, chunks = ManualIndex.Status.INDEXED, "", [], []
    try:
        media.file.open("rb")
        try:
            pages = extract_pdf_pages(media.file)
        finally:
            media.file.close()
        for number, text in enumerate(pages, start=1):
            chunks.extend((number, piece) for piece in split_text(text))
        if not chunks:
            status = ManualIndex.Status.NO_TEXT
    except Exception as exc:  # PDF protegido, arquivo ausente etc.
        logger.warning("Falha ao indexar mídia %s: %s", media.pk, type(exc).__name__)
        status, error = ManualIndex.Status.ERROR, "Não foi possível ler o PDF."
        chunks = []
    with transaction.atomic():
        ManualChunk.objects.filter(media=media).delete()
        ManualChunk.objects.bulk_create(
            [ManualChunk(media=media, position=i, page=page, text=text) for i, (page, text) in enumerate(chunks)]
        )
        index, _ = ManualIndex.objects.update_or_create(
            media=media, defaults={"status": status, "page_count": len(pages), "chunk_count": len(chunks), "error": error}
        )
    return index
