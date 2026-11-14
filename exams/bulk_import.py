"""
Parsers for bulk-uploading multiple-choice questions from CSV, DOCX or PDF.

Deliberately free of Django imports so it can be unit-tested on its own.
Every parser returns a list of ParsedQuestion; nothing is saved here.
"""
import csv
import io
import re
from dataclasses import dataclass, field

MAX_FILE_SIZE = 4 * 1024 * 1024   # Vercel rejects request bodies over ~4.5 MB
MAX_QUESTIONS = 300
MAX_PDF_PAGES = 60
MAX_CHOICE_LEN = 500              # matches Choice.text max_length
LETTERS = 'ABCDEF'                # matches the 2-6 choices the editor allows

CSV_HEADERS = [
    'question', 'option_a', 'option_b', 'option_c', 'option_d',
    'option_e', 'option_f', 'correct', 'marks', 'explanation',
]

# Postgres refuses NUL characters, and PDFs occasionally produce them.
CONTROL_CHARS = re.compile(r'[\x00-\x08\x0e-\x1f\x7f]')

QUESTION_RE = re.compile(r'^\s*(?:Q(?:uestion)?\s*)?(\d{1,3})\s*[\.\):\-]\s+(.*\S)\s*$', re.I)
OPTION_RE = re.compile(r'^\s*\(?([A-Fa-f])\s*[\.\)]\s+(.*\S)\s*$')
ANSWER_RE = re.compile(r'^\s*(?:correct\s+answer|answer|ans)\s*[:\-]\s*\(?([A-Fa-f])\)?(?![A-Za-z0-9])', re.I)
MARKS_RE = re.compile(r'^\s*(?:marks?|points?)\s*[:\-]\s*(\d{1,3})\b', re.I)
EXPLANATION_RE = re.compile(r'^\s*(?:explanation|reason|rationale)\s*[:\-]\s*(.*)$', re.I)


class ImportFileError(Exception):
    """A file-level problem (wrong type, unreadable, empty) shown to the teacher."""


@dataclass
class ParsedQuestion:
    number: int = 0
    text: str = ''
    options: dict = field(default_factory=dict)   # {'A': 'text', 'B': 'text'}
    answer: str = ''
    marks: int | None = None
    explanation: str = ''
    errors: list = field(default_factory=list)


def clean_text(value):
    value = value.replace('\x0b', '\n').replace('\x0c', '\n')
    return CONTROL_CHARS.sub('', value)


def validate(q):
    errors = []
    if not q.text.strip():
        errors.append("Question text is missing.")
    if len(q.options) < 2:
        errors.append("At least 2 answer options are required.")
    if not q.answer:
        errors.append("No correct answer given.")
    elif q.answer not in q.options:
        errors.append(f"Correct answer '{q.answer}' doesn't match any option.")
    for letter, text in q.options.items():
        if len(text) > MAX_CHOICE_LEN:
            errors.append(f"Option {letter} is longer than {MAX_CHOICE_LEN} characters.")
    if q.marks is not None and q.marks < 1:
        errors.append("Marks must be at least 1.")
    return errors


# --------------------------------------------------------------------------
# Plain-text format (used for DOCX and PDF)
# --------------------------------------------------------------------------
def parse_text(text):
    questions = []
    current = None
    target = None  # where wrapped continuation lines get appended

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if current:
            m = ANSWER_RE.match(line)
            if m:
                current.answer = m.group(1).upper()
                target = None
                continue
            m = MARKS_RE.match(line)
            if m:
                current.marks = int(m.group(1))
                target = None
                continue
            m = EXPLANATION_RE.match(line)
            if m:
                current.explanation = m.group(1).strip()
                target = 'explanation'
                continue

        m = QUESTION_RE.match(line)
        if m:
            current = ParsedQuestion(text=m.group(2).strip())
            questions.append(current)
            target = 'question'
            continue

        m = OPTION_RE.match(line)
        if m and current:
            letter = m.group(1).upper()
            if letter in current.options:
                current.errors.append(f"Option {letter} appears more than once.")
            current.options[letter] = m.group(2).strip()
            target = ('option', letter)
            continue

        # Wrapped line: PDFs and Word break long lines, so glue it onto
        # whatever we were last reading. Text before question 1 is ignored.
        if current is None:
            continue
        if target == 'question':
            current.text += ' ' + line
        elif isinstance(target, tuple):
            current.options[target[1]] += ' ' + line
        elif target == 'explanation':
            current.explanation += ' ' + line

    return questions


def extract_text_from_docx(file_obj):
    from docx import Document  # python-docx
    try:
        document = Document(file_obj)
    except Exception as exc:
        raise ImportFileError("Couldn't read this Word file. Make sure it's a valid .docx.") from exc
    return clean_text('\n'.join(p.text for p in document.paragraphs))


def extract_text_from_pdf(file_obj):
    from pypdf import PdfReader
    try:
        reader = PdfReader(file_obj)
        if reader.is_encrypted:
            raise ImportFileError("This PDF is password-protected. Remove the password and try again.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ImportFileError(f"This PDF has more than {MAX_PDF_PAGES} pages. Split it into smaller files.")
        text = '\n'.join((page.extract_text() or '') for page in reader.pages)
    except ImportFileError:
        raise
    except Exception as exc:
        raise ImportFileError("Couldn't read this PDF. It may be corrupted.") from exc
    if not text.strip():
        raise ImportFileError(
            "No text found in this PDF. Scanned or image-only PDFs aren't supported - "
            "upload a text-based PDF, a .docx or a .csv instead."
        )
    return clean_text(text)


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
def _cell(row, fields, key):
    column = fields.get(key)
    if not column:
        return ''
    return clean_text((row.get(column) or '').strip())


def parse_csv(file_obj):
    raw = file_obj.read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')  # older Excel "CSV" exports

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportFileError("The CSV file is empty.")

    fields = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = [c for c in ('question', 'option_a', 'option_b', 'correct') if c not in fields]
    if missing:
        raise ImportFileError(
            "The CSV is missing required column(s): " + ", ".join(missing) +
            ". Download the sample CSV to see the expected layout."
        )

    questions = []
    for row in reader:
        if not any(v.strip() for v in row.values() if isinstance(v, str)):
            continue  # blank line
        if len(questions) >= MAX_QUESTIONS:
            raise ImportFileError(f"Too many questions - the limit is {MAX_QUESTIONS} per upload.")

        q = ParsedQuestion(text=_cell(row, fields, 'question'))
        for letter in LETTERS:
            value = _cell(row, fields, f'option_{letter.lower()}')
            if value:
                q.options[letter] = value

        # "correct" can be a letter (B / option_b) or the exact option text.
        given = _cell(row, fields, 'correct')
        if given:
            candidate = re.sub(r'^option[_\s]*', '', given, flags=re.I).strip(' .()').upper()
            if len(candidate) == 1 and candidate in LETTERS:
                q.answer = candidate
            else:
                q.answer = next(
                    (l for l, t in q.options.items() if t.lower() == given.lower()), given[:30]
                )

        marks = _cell(row, fields, 'marks')
        if marks:
            try:
                q.marks = int(float(marks))
            except ValueError:
                q.errors.append(f"Marks '{marks}' isn't a whole number.")
        q.explanation = _cell(row, fields, 'explanation')
        questions.append(q)

    return questions


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def parse_uploaded_file(uploaded):
    if uploaded.size > MAX_FILE_SIZE:
        raise ImportFileError(f"File is too large - the limit is {MAX_FILE_SIZE // (1024 * 1024)} MB.")

    name = uploaded.name.lower()
    ext = name.rsplit('.', 1)[-1] if '.' in name else ''

    if ext == 'csv':
        questions = parse_csv(uploaded)
    elif ext == 'docx':
        questions = parse_text(extract_text_from_docx(uploaded))
    elif ext == 'pdf':
        questions = parse_text(extract_text_from_pdf(uploaded))
    elif ext == 'doc':
        raise ImportFileError(
            "Old .doc files can't be read. Open it in Word, choose File > Save As > .docx, "
            "and upload that instead."
        )
    else:
        raise ImportFileError("Unsupported file type. Upload a .csv, .docx or .pdf file.")

    if not questions:
        raise ImportFileError("No questions were found. Check the format guide on this page and try again.")
    if len(questions) > MAX_QUESTIONS:
        raise ImportFileError(f"Too many questions - the limit is {MAX_QUESTIONS} per upload.")

    for index, q in enumerate(questions, start=1):
        q.number = index
        q.errors.extend(validate(q))
    return questions