"""
PDF / DOCX past-question import.

A long document would take Gemini longer than a serverless request is allowed to run, so the
file is split into small parts and the admin page processes one part per request, then shows
every extracted question for review before anything is saved.
"""
import io
import math

from django.db import transaction

from . import ai, conf
from .logic import FileProblem, clean_question_row, split_text_chunks
from .models import ImportJob

MAX_FILE_SIZE = 4 * 1024 * 1024        # Vercel rejects request bodies over about 4.5 MB
MAX_PDF_PAGES = 120
MAX_DOC_CHUNKS = 80
DOC_CHUNK_CHARS = 5000


def pages_per_chunk():
    return max(1, conf.get_int('JAMB_PDF_PAGES_PER_CHUNK', 2))


def _docx_text(file_obj):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = Document(file_obj)
    except Exception as exc:
        raise FileProblem("Couldn't read this Word file. Make sure it's a valid .docx.") from exc

    lines = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            lines.append(Paragraph(child, document).text)
        elif tag == 'tbl':
            for row in Table(child, document).rows:
                cells = []
                for cell in row.cells:
                    text = cell.text.strip()
                    if text and (not cells or cells[-1] != text):   # merged cells repeat their text
                        cells.append(text)
                lines.append(' | '.join(cells))
    return '\n'.join(lines)


def create_job(uploaded, user, default_subject=None, default_year=None):
    """Validate the upload and create an ImportJob ready to be processed chunk by chunk."""
    name = uploaded.name
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if uploaded.size > MAX_FILE_SIZE:
        raise FileProblem(f"File is too large. The limit is {MAX_FILE_SIZE // (1024 * 1024)} MB.")

    common = dict(created_by=user, filename=name[:255], default_subject=default_subject, default_year=default_year)

    if ext == 'pdf':
        from pypdf import PdfReader
        blob = uploaded.read()
        try:
            reader = PdfReader(io.BytesIO(blob))
            if reader.is_encrypted:
                raise FileProblem("This PDF is password-protected. Remove the password and try again.")
            pages = len(reader.pages)
        except FileProblem:
            raise
        except Exception as exc:
            raise FileProblem("Couldn't read this PDF. It may be corrupted.") from exc
        if pages == 0:
            raise FileProblem("This PDF has no pages.")
        if pages > MAX_PDF_PAGES:
            raise FileProblem(f"This PDF has {pages} pages. The limit is {MAX_PDF_PAGES}; split it first.")
        return ImportJob.objects.create(
            kind='pdf', source_pdf=blob, total_chunks=math.ceil(pages / pages_per_chunk()), **common
        )

    if ext == 'docx':
        chunks = split_text_chunks(_docx_text(uploaded), DOC_CHUNK_CHARS)
        if not chunks:
            raise FileProblem("No text was found in this document.")
        if len(chunks) > MAX_DOC_CHUNKS:
            raise FileProblem("This document is too long. Split it into smaller files.")
        return ImportJob.objects.create(kind='docx', chunks=chunks, total_chunks=len(chunks), **common)

    if ext == 'doc':
        raise FileProblem(
            "Old .doc files can't be read. Open it in Word, choose File > Save As > .docx, and upload that."
        )
    raise FileProblem("Unsupported file type. Upload a .pdf or .docx file.")


def _pdf_part_bytes(blob, index):
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(blob))
    size = pages_per_chunk()
    writer = PdfWriter()
    for page in reader.pages[index * size:(index + 1) * size]:
        writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _to_draft(raw, job):
    """Turn one raw Gemini item into an editable review row."""
    subject_hint = job.default_subject.name if job.default_subject_id else ''
    row, error = clean_question_row(raw, default_subject=subject_hint, default_year=job.default_year)
    row['answer_source'] = 'ai' if str(raw.get('answer_source', '')).lower() == 'ai' else 'document'
    if raw.get('needs_figure') is True:
        error = '; '.join(filter(None, [error, "Refers to a diagram or table that isn't in the text."]))
        row['needs_figure'] = True
    row['error'] = error
    return row


def process_next_chunk(job_id, skip=False):
    """
    Extract questions from the next part of the document.
    Raises ai.AIUnavailable if Gemini fails (nothing is changed, so the part can be retried).
    """
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().get(pk=job_id)
        if job.status != ImportJob.Status.PROCESSING:
            return job
        index = job.next_chunk
        if index < job.total_chunks:
            if skip:
                job.errors = job.errors + [f"Part {index + 1} of {job.total_chunks} was skipped."]
            else:
                subject_hint = job.default_subject.name if job.default_subject_id else ''
                if job.kind == 'pdf':
                    data = _pdf_part_bytes(bytes(job.source_pdf), index)
                    parts = lambda types: [types.Part.from_bytes(data=data, mime_type='application/pdf')]
                else:
                    text = job.chunks[index]
                    parts = lambda types: ['DOCUMENT TEXT:\n' + text]
                raw_items = ai.extract_questions(parts, subject_hint, job.default_year)
                job.extracted = job.extracted + [_to_draft(item, job) for item in raw_items]
            job.next_chunk = index + 1
        if job.next_chunk >= job.total_chunks:
            job.status = ImportJob.Status.READY
        job.save()
    return job
