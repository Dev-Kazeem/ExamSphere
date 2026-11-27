"""Everything that talks to Google Gemini."""
import logging

from . import conf, logic
from .constants import SUBJECT_NAMES

logger = logging.getLogger(__name__)

# 'latest' aliases always exist. For production, pin a specific stable model with GEMINI_MODEL
# (see https://ai.google.dev/gemini-api/docs/models) so behaviour doesn't change under you.
DEFAULT_MODEL = 'gemini-flash-latest'

FALLBACK_MESSAGE = (
    "Your AI Teacher is not available right now. Please try again later. "
    "In the meantime you can still practise with Mock exams and Study topics."
)


class AIUnavailable(Exception):
    """Gemini isn't configured, timed out, or returned something unusable."""


def is_configured():
    return bool(conf.get('GEMINI_API_KEY'))


def chat_model():
    return conf.get('GEMINI_MODEL') or DEFAULT_MODEL


def extraction_model():
    return conf.get('GEMINI_EXTRACTION_MODEL') or chat_model()


def _generate(model, make_contents, *, system=None, temperature=0.3, max_tokens=2048, json_mode=False):
    if not is_configured():
        raise AIUnavailable('GEMINI_API_KEY is not set.')
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=conf.get('GEMINI_API_KEY'),
            http_options=types.HttpOptions(timeout=conf.get_int('GEMINI_TIMEOUT_SECONDS', 25) * 1000),
        )
        config = {'temperature': temperature, 'max_output_tokens': max_tokens}
        if system:
            config['system_instruction'] = system
        if json_mode:
            config['response_mime_type'] = 'application/json'
        response = client.models.generate_content(
            model=model,
            contents=make_contents(types),
            config=types.GenerateContentConfig(**config),
        )
        text = (response.text or '').strip()
    except AIUnavailable:
        raise
    except Exception as exc:                      # network, quota, bad model name, blocked content...
        logger.exception('Gemini request failed (model=%s)', model)
        raise AIUnavailable(str(exc)[:300]) from exc
    if not text:
        raise AIUnavailable('Gemini returned an empty reply.')
    return text


# --------------------------------------------------------------------------
# AI Teacher
# --------------------------------------------------------------------------
def teacher_reply(profile, history, question, channel='web'):
    """
    history: [(role, text)] oldest first, role 'user' or 'assistant'.
    Returns the teacher's reply text.
    """
    user = profile.user
    system = logic.build_teacher_prompt(
        user.first_name or user.username, profile.preferred_language, profile.combination,
        profile.target_school, profile.target_score, channel,
    )

    def contents(types):
        items = []
        for role, text in history:
            if not items and role != 'user':
                continue                              # a conversation must start with the student
            items.append(types.Content(
                role='user' if role == 'user' else 'model',
                parts=[types.Part.from_text(text=text[:1500])],
            ))
        items.append(types.Content(role='user', parts=[types.Part.from_text(text=question[:2000])]))
        return items

    return _generate(chat_model(), contents, system=system, temperature=0.4, max_tokens=2048)


# --------------------------------------------------------------------------
# Question extraction from PDF / DOCX
# --------------------------------------------------------------------------
EXTRACTION_PROMPT = """You extract multiple-choice questions from JAMB (UTME) past-question material.

Return ONLY a JSON array. Each element is an object with exactly these keys:
  "subject": one of {subjects}, or "" if you cannot tell
  "topic": a short syllabus topic such as "Algebra" or "Photosynthesis"
  "question_text": the full question text
  "option_a", "option_b", "option_c", "option_d": the four options, without the letters
  "correct_option": "A", "B", "C" or "D"
  "explanation": one or two sentences saying why that option is right
  "year": the exam year as a number, or null
  "answer_source": "document" if the material states the answer, "ai" if you worked it out yourself
  "needs_figure": true if the question depends on a diagram, graph or table that is not in the material

Rules:
- Extract only what is in the material. Never invent questions.
- Skip anything that does not have four options.
- Keep the original wording. Write maths in plain text, for example x^2, sqrt(3), 3/4.
- If an answer key is given (often at the end), use it. Otherwise work the question out carefully.
- If the material contains no questions, return [].
{hints}"""


def build_extraction_prompt(subject_hint='', year_hint=None):
    hints = []
    if subject_hint:
        hints.append(f'- Every question in this material is {subject_hint}; use that as "subject".')
    if year_hint:
        hints.append(f'- Use {year_hint} as "year" unless the material shows a different year.')
    return EXTRACTION_PROMPT.format(subjects=', '.join(f'"{n}"' for n in SUBJECT_NAMES), hints='\n'.join(hints))


def extract_questions(make_material_parts, subject_hint='', year_hint=None):
    """
    make_material_parts(types) -> list of Gemini parts holding the document chunk.
    Returns a list of raw question dicts.
    """
    prompt = build_extraction_prompt(subject_hint, year_hint)
    text = _generate(
        extraction_model(),
        lambda types: [prompt, *make_material_parts(types)],
        temperature=0.1, max_tokens=8192, json_mode=True,
    )
    try:
        return logic.parse_json_array(text)
    except ValueError as exc:
        raise AIUnavailable(f'Could not read the AI reply: {exc}') from exc
