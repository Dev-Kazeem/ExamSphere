"""
WhatsApp bot (Meta WhatsApp Cloud API).

Every message in both directions is saved as a ChatMessage with channel='whatsapp', so the
conversation also shows up in the in-app Ask AI Teacher chat.
"""
import logging
import random

import requests
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from . import ai, billing, chat, conf, logic
from .constants import MOCK_MIN_QUESTIONS, WHATSAPP_MOCK_QUESTIONS
from .models import ChatMessage, JambProfile, MockAnswer, MockAttempt, Question, Subject

logger = logging.getLogger(__name__)
State = JambProfile.WaState
Attempt = MockAttempt


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------
def send_text(to, body):
    token = conf.get('WHATSAPP_ACCESS_TOKEN')
    phone_id = conf.get('WHATSAPP_PHONE_NUMBER_ID')
    if not (token and phone_id):
        logger.warning('WhatsApp is not configured (WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID).')
        return False
    version = conf.get('WHATSAPP_GRAPH_VERSION', 'v24.0')
    url = f'https://graph.facebook.com/{version}/{phone_id}/messages'
    ok = True
    for part in logic.split_message(body):
        try:
            response = requests.post(
                url,
                json={'messaging_product': 'whatsapp', 'to': to, 'type': 'text',
                      'text': {'body': part, 'preview_url': False}},
                headers={'Authorization': f'Bearer {token}'},
                timeout=10,
            )
            if response.status_code >= 300:
                logger.warning('WhatsApp send failed (%s): %s', response.status_code, response.text[:300])
                ok = False
        except requests.RequestException:
            logger.exception('WhatsApp send failed')
            ok = False
    return ok


def _reply(profile, wa_id, inbound, text, kind=ChatMessage.Kind.BOT):
    ChatMessage.objects.create(
        user=profile.user, role=ChatMessage.Role.ASSISTANT, content=text,
        channel=ChatMessage.Channel.WHATSAPP, kind=kind,
    )
    send_text(wa_id, text)
    if inbound is not None:
        ChatMessage.objects.filter(pk=inbound.pk).update(reply_sent=True)


def _subscribe_text():
    return (
        "Mock exams and your AI Teacher need an active subscription.\n"
        f"Subscribe here: {chat.site_url(reverse('jamb_tutor:subscribe'))}\n\n"
        "Then come back and type MOCK."
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def handle_incoming(msg):
    wa_id, text, message_id = msg['from'], msg['text'], msg['id']

    profile = JambProfile.objects.select_related('user').filter(phone_e164=wa_id).first()
    if profile is None:
        send_text(wa_id, (
            "Hello! I couldn't find a JAMB Tutor account for this WhatsApp number.\n"
            f"Sign up here with this number: {chat.site_url(reverse('jamb_tutor:signup'))}"
        ))
        return
    if not profile.user.is_active:
        send_text(wa_id, "Please verify your email first. Open the link we sent to your inbox, then message me again.")
        return

    defaults = dict(
        user=profile.user, role=ChatMessage.Role.USER, content=text or '[unsupported message]',
        channel=ChatMessage.Channel.WHATSAPP, kind=ChatMessage.Kind.BOT,
    )
    if message_id:
        inbound, created = ChatMessage.objects.get_or_create(wa_message_id=message_id, defaults=defaults)
        if not created and inbound.reply_sent:
            return                                    # Meta re-delivered a message we already answered
    else:
        inbound = ChatMessage.objects.create(**defaults)

    if msg['type'] not in ('text', 'button') or not text:
        return _reply(profile, wa_id, inbound, "I can only read text messages for now. Please type your question.")

    command, argument = logic.parse_command(text)

    # ---- in the middle of a mock ----
    if profile.wa_state == State.IN_MOCK:
        if command == 'stop':
            return _stop_mock(profile, wa_id, inbound)
        letter = logic.parse_answer_letter(text)
        if letter:
            return _answer_mock(profile, wa_id, inbound, letter)
        return _reply(profile, wa_id, inbound, "Reply with A, B, C or D to answer, or type STOP to quit the mock.")

    # ---- menu commands ----
    if command == 'start':
        _set_state(profile, State.IDLE)
        return _reply(profile, wa_id, inbound, logic.welcome_text(profile.user.first_name or profile.user.username,
                                                                    profile.preferred_language))
    if command == 'subscribe':
        return _reply(profile, wa_id, inbound, _subscribe_text())
    if command == 'stop':
        _set_state(profile, State.IDLE)
        return _reply(profile, wa_id, inbound, "Okay. Type MOCK to practise, or ask me any question.")

    # ---- choosing a subject for a mock ----
    if profile.wa_state == State.AWAITING_SUBJECT and command != 'mock':
        subject_name = logic.resolve_subject_choice(text)
        if subject_name:
            return _start_mock(profile, wa_id, inbound, subject_name)
        if len(text) <= 20:
            return _reply(profile, wa_id, inbound,
                          "I didn't get that. Reply with a number from the list, or type STOP.\n\n" + logic.subject_menu())
        _set_state(profile, State.IDLE)               # a real question: leave the menu and answer it

    if command == 'mock':
        if not billing.user_has_access(profile.user):
            return _reply(profile, wa_id, inbound, _subscribe_text())
        subject_name = logic.resolve_subject_choice(argument) if argument else None
        if subject_name:
            return _start_mock(profile, wa_id, inbound, subject_name)
        _set_state(profile, State.AWAITING_SUBJECT)
        return _reply(profile, wa_id, inbound, "Which subject? Reply with a number:\n\n" + logic.subject_menu())

    return _ask_teacher(profile, wa_id, inbound, text)


def _set_state(profile, state, attempt=None):
    profile.wa_state = state
    profile.wa_attempt = attempt
    profile.save(update_fields=['wa_state', 'wa_attempt'])


# --------------------------------------------------------------------------
# AI Teacher
# --------------------------------------------------------------------------
def _ask_teacher(profile, wa_id, inbound, text):
    user = profile.user
    if not billing.user_has_access(user):
        return _reply(profile, wa_id, inbound, _subscribe_text())
    if not ai.is_configured():
        return _reply(profile, wa_id, inbound, ai.FALLBACK_MESSAGE)
    if chat.rate_limited(user):
        return _reply(profile, wa_id, inbound,
                      "You've asked a lot of questions this hour. Take a short break and try again soon.")
    history = chat.recent_history(user)
    try:
        answer = ai.teacher_reply(profile, history, text, channel='whatsapp')
    except ai.AIUnavailable:
        return _reply(profile, wa_id, inbound, "I couldn't answer just now. Please send your question again in a minute.")
    ChatMessage.objects.filter(pk=inbound.pk).update(kind=ChatMessage.Kind.AI)
    profile.record_activity()
    _reply(profile, wa_id, inbound, answer, kind=ChatMessage.Kind.AI)


# --------------------------------------------------------------------------
# Mock exam over WhatsApp
# --------------------------------------------------------------------------
def _question_message(attempt, answer):
    q = answer.question
    return logic.format_whatsapp_question(
        answer.position + 1, attempt.total_questions, attempt.subject.name,
        {'text': q.question_text, 'a': q.option_a, 'b': q.option_b, 'c': q.option_c, 'd': q.option_d},
    )


def _start_mock(profile, wa_id, inbound, subject_name):
    if not billing.user_has_access(profile.user):
        return _reply(profile, wa_id, inbound, _subscribe_text())
    subject = Subject.objects.filter(name=subject_name).first()
    ids = list(Question.objects.filter(subject=subject).values_list('id', flat=True)) if subject else []
    if len(ids) < MOCK_MIN_QUESTIONS:
        _set_state(profile, State.IDLE)
        return _reply(profile, wa_id, inbound,
                      f"There aren't enough {subject_name} questions yet. Try another subject: type MOCK.")

    Attempt.objects.filter(
        user=profile.user, source=Attempt.Source.WHATSAPP, status=Attempt.Status.IN_PROGRESS
    ).update(status=Attempt.Status.ABANDONED)

    chosen = random.sample(ids, min(WHATSAPP_MOCK_QUESTIONS, len(ids)))
    with transaction.atomic():
        attempt = Attempt.objects.create(
            user=profile.user, subject=subject, source=Attempt.Source.WHATSAPP,
            total_questions=len(chosen), duration_seconds=0,
        )
        MockAnswer.objects.bulk_create(
            [MockAnswer(attempt=attempt, question_id=qid, position=i) for i, qid in enumerate(chosen)]
        )
    _set_state(profile, State.IN_MOCK, attempt)
    first = attempt.answers.select_related('question').get(position=0)
    _reply(profile, wa_id, inbound,
           f"Starting a {len(chosen)}-question {subject.full_name} mock. Good luck!\n\n" + _question_message(attempt, first))


def _answer_mock(profile, wa_id, inbound, letter):
    attempt = profile.wa_attempt
    if attempt is None or attempt.status != Attempt.Status.IN_PROGRESS:
        _set_state(profile, State.IDLE)
        return _reply(profile, wa_id, inbound, "There's no mock running. Type MOCK to start one.")

    answer = attempt.answers.select_related('question').filter(position=attempt.wa_index).first()
    if answer is None:
        return _finish_mock(profile, wa_id, inbound, attempt, '')

    question = answer.question
    answer.selected_option = letter
    answer.is_correct = letter == question.correct_option
    answer.answered_at = timezone.now()
    answer.save(update_fields=['selected_option', 'is_correct', 'answered_at'])

    if answer.is_correct:
        feedback = "Correct!"
    else:
        feedback = f"Not quite. The correct answer is {question.correct_option}."
    if question.explanation:
        feedback += f"\n{question.explanation}"

    attempt.wa_index += 1
    attempt.save(update_fields=['wa_index'])
    if attempt.wa_index >= attempt.total_questions:
        return _finish_mock(profile, wa_id, inbound, attempt, feedback)

    nxt = attempt.answers.select_related('question').get(position=attempt.wa_index)
    _reply(profile, wa_id, inbound, feedback + "\n\n" + _question_message(attempt, nxt))


def _finish_mock(profile, wa_id, inbound, attempt, feedback):
    attempt.finalize(Attempt.Status.COMPLETED)
    _set_state(profile, State.IDLE)
    profile.record_activity()
    projected = attempt.projected_score
    verdict = "You are on track for your target." if attempt.passed_for(profile.target_score) \
        else "You are below your target score, so keep practising."
    summary = (
        f"Mock finished!\nScore: {attempt.score}/{attempt.total_questions} ({attempt.percentage}%)\n"
        f"That is about {projected}/400 in JAMB terms. Your target is {profile.target_score}.\n{verdict}\n\n"
        "Type MOCK to try another subject, or ask me any question."
    )
    _reply(profile, wa_id, inbound, (feedback + "\n\n" if feedback else '') + summary)


def _stop_mock(profile, wa_id, inbound):
    attempt = profile.wa_attempt
    if attempt is not None:
        Attempt.objects.filter(pk=attempt.pk, status=Attempt.Status.IN_PROGRESS).update(
            status=Attempt.Status.ABANDONED, submitted_at=timezone.now()
        )
    _set_state(profile, State.IDLE)
    _reply(profile, wa_id, inbound, "Mock stopped. Type MOCK to start another, or ask me any question.")
