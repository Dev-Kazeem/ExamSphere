"""Save cleaned question rows, skipping duplicates. Used by CSV upload and document review."""
from django.db import transaction

from .logic import question_hash
from .models import Question, Subject, Topic


def save_rows(rows, created_by=None):
    """
    rows: dicts from logic.clean_question_row (subject already canonical).
    Returns {'added': n, 'duplicates': n}. A question counts as a duplicate when the same
    subject already has a question with the same text (ignoring case, spacing and punctuation).
    """
    subjects = {s.name: s for s in Subject.objects.all()}

    prepared, seen, duplicates = [], set(), 0
    for row in rows:
        subject = subjects.get(row['subject'])
        if subject is None:
            continue
        key = (subject.pk, question_hash(subject.pk, row['question_text']))
        if key in seen:
            duplicates += 1                      # repeated inside the same upload
            continue
        seen.add(key)
        prepared.append((subject, key[1], row))

    existing = set()
    if prepared:
        existing = set(
            Question.objects.filter(text_hash__in=[h for _, h, _ in prepared])
            .values_list('subject_id', 'text_hash')
        )

    topics = {}
    for topic in Topic.objects.filter(subject__in={s for s, _, _ in prepared}):
        topics[(topic.subject_id, topic.name.lower())] = topic

    to_create = []
    with transaction.atomic():
        for subject, text_hash, row in prepared:
            if (subject.pk, text_hash) in existing:
                duplicates += 1
                continue
            name = row['topic'] or 'General'
            topic = topics.get((subject.pk, name.lower()))
            if topic is None:
                topic = Topic.objects.create(subject=subject, name=name)
                topics[(subject.pk, name.lower())] = topic
            to_create.append(Question(
                subject=subject, topic=topic,
                question_text=row['question_text'],
                option_a=row['option_a'], option_b=row['option_b'],
                option_c=row['option_c'], option_d=row['option_d'],
                correct_option=row['correct_option'],
                explanation=row['explanation'],
                year=int(row['year']) if row.get('year') else None,
                text_hash=text_hash, created_by=created_by,
            ))
        Question.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)

    return {'added': len(to_create), 'duplicates': duplicates}
