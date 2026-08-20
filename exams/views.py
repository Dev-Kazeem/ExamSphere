from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import ExamForm, QuestionForm, ChoiceFormSet
from .models import Exam, Question, ExamAttempt, StudentAnswer
from .permissions import teacher_required, student_required


# =========================================================================
# TEACHER VIEWS
# =========================================================================

@teacher_required
def teacher_dashboard(request):
    exams = (
        Exam.objects.filter(teacher=request.user)
        .annotate(num_questions=Count('questions', distinct=True), num_attempts=Count('attempts', distinct=True))
    )
    return render(request, 'exams/teacher_dashboard.html', {'exams': exams})


@teacher_required
def exam_create(request):
    if request.method == 'POST':
        form = ExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.teacher = request.user
            exam.save()
            messages.success(request, "Exam created. Now add some questions!")
            return redirect('exams:manage_questions', exam_id=exam.id)
    else:
        form = ExamForm()
    return render(request, 'exams/exam_form.html', {'form': form, 'title': 'Create Exam'})


@teacher_required
def exam_update(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    if request.method == 'POST':
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            messages.success(request, "Exam updated.")
            return redirect('exams:teacher_dashboard')
    else:
        form = ExamForm(instance=exam)
    return render(request, 'exams/exam_form.html', {'form': form, 'title': 'Edit Exam', 'exam': exam})


@teacher_required
def exam_delete(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    if request.method == 'POST':
        exam.delete()
        messages.success(request, "Exam deleted.")
        return redirect('exams:teacher_dashboard')
    return render(request, 'exams/exam_confirm_delete.html', {'exam': exam})


@teacher_required
def exam_toggle_publish(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    if request.method == 'POST':
        if not exam.is_published and exam.question_count == 0:
            messages.error(request, "Add at least one question before publishing.")
        else:
            exam.is_published = not exam.is_published
            exam.save(update_fields=['is_published'])
            messages.success(request, f"Exam is now {'published' if exam.is_published else 'unpublished'}.")
    return redirect('exams:teacher_dashboard')


@teacher_required
def manage_questions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    questions = exam.questions.all()
    return render(request, 'exams/manage_questions.html', {'exam': exam, 'questions': questions})


@teacher_required
def question_create(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        question = Question(exam=exam)
        formset = ChoiceFormSet(request.POST, instance=question)
        if form.is_valid():
            # Bind formset to an in-memory (unsaved) question first for validation,
            # then save both atomically once everything is valid.
            question = form.save(commit=False)
            question.exam = exam
            formset = ChoiceFormSet(request.POST, instance=question)
            if formset.is_valid():
                with transaction.atomic():
                    question.save()
                    formset.instance = question
                    formset.save()
                messages.success(request, "Question added.")
                return redirect('exams:manage_questions', exam_id=exam.id)
    else:
        form = QuestionForm(initial={'order': exam.question_count + 1})
        formset = ChoiceFormSet()
    return render(request, 'exams/question_form.html', {
        'form': form, 'formset': formset, 'exam': exam, 'title': 'Add Question',
    })


@teacher_required
def question_update(request, exam_id, question_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    question = get_object_or_404(Question, id=question_id, exam=exam)
    if request.method == 'POST':
        form = QuestionForm(request.POST, instance=question)
        formset = ChoiceFormSet(request.POST, instance=question)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, "Question updated.")
            return redirect('exams:manage_questions', exam_id=exam.id)
    else:
        form = QuestionForm(instance=question)
        formset = ChoiceFormSet(instance=question)
    return render(request, 'exams/question_form.html', {
        'form': form, 'formset': formset, 'exam': exam, 'title': 'Edit Question',
    })


@teacher_required
def question_delete(request, exam_id, question_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    question = get_object_or_404(Question, id=question_id, exam=exam)
    if request.method == 'POST':
        question.delete()
        messages.success(request, "Question deleted.")
        return redirect('exams:manage_questions', exam_id=exam.id)
    return render(request, 'exams/question_confirm_delete.html', {'question': question, 'exam': exam})


@teacher_required
def exam_results(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, teacher=request.user)
    attempts = exam.attempts.select_related('student').exclude(status=ExamAttempt.Status.IN_PROGRESS)
    return render(request, 'exams/exam_results.html', {'exam': exam, 'attempts': attempts})


@teacher_required
def attempt_review_teacher(request, attempt_id):
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related('exam', 'student'), id=attempt_id, exam__teacher=request.user
    )
    answers = attempt.answers.select_related('question', 'selected_choice').order_by('question__order')
    return render(request, 'exams/attempt_review.html', {'attempt': attempt, 'answers': answers, 'is_teacher_view': True})


# =========================================================================
# STUDENT VIEWS
# =========================================================================
@student_required
def student_dashboard(request):
    now = timezone.now()
    available_exams = Exam.objects.filter(
        is_published=True, start_time__lte=now, end_time__gte=now   # <-- restore this
    ).annotate(num_questions=Count('questions', distinct=True)).filter(num_questions__gt=0)

    upcoming_exams = Exam.objects.filter(is_published=True, start_time__gt=now)

    my_attempts = ExamAttempt.objects.filter(student=request.user).select_related('exam')

    attempts_by_exam = {}
    for attempt in my_attempts:
        attempts_by_exam.setdefault(attempt.exam_id, []).append(attempt)

    exam_status = []
    for exam in available_exams:
        used = len(attempts_by_exam.get(exam.id, []))
        exam_status.append({
            'exam': exam,
            'attempts_used': used,
            'can_attempt': used < exam.max_attempts,
        })

    recent_results = my_attempts.exclude(status=ExamAttempt.Status.IN_PROGRESS)[:5]

    return render(request, 'exams/student_dashboard.html', {
        'exam_status': exam_status,
        'upcoming_exams': upcoming_exams,
        'recent_results': recent_results,
    })


@student_required
def exam_start(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id, is_published=True)

    if not exam.can_be_attempted_by(request.user):
        messages.error(request, "This exam isn't currently available to you (closed, not yet open, or no attempts left).")
        return redirect('exams:student_dashboard')

    # Resume an in-progress attempt if one already exists and hasn't expired.
    in_progress = ExamAttempt.objects.filter(
        student=request.user, exam=exam, status=ExamAttempt.Status.IN_PROGRESS
    ).first()
    if in_progress:
        if in_progress.is_time_expired:
            in_progress.grade()
            return redirect('exams:result_detail', attempt_id=in_progress.id)
        return redirect('exams:take_exam', attempt_id=in_progress.id)

    attempt_number = exam.attempts_used_by(request.user) + 1
    attempt = ExamAttempt.objects.create(student=request.user, exam=exam, attempt_number=attempt_number)
    return redirect('exams:take_exam', attempt_id=attempt.id)

@student_required
def take_exam(request, attempt_id):
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, student=request.user)

    if attempt.status != ExamAttempt.Status.IN_PROGRESS:
        return redirect('exams:result_detail', attempt_id=attempt.id)
    
    if attempt.is_time_expired:
        attempt.grade()
        messages.warning(request, "Time was up, so your exam was automatically submitted.")
        return redirect('exams:result_detail', attempt_id=attempt.id)

    questions = list(attempt.exam.questions.prefetch_related('choices').order_by('order', 'id'))

    if request.method == 'POST':
        with transaction.atomic():
            for question in questions:
                choice_id = request.POST.get(f'question_{question.id}')
                selected_choice = None
                if choice_id:
                    selected_choice = question.choices.filter(id=choice_id).first()
                StudentAnswer.objects.update_or_create(
                    attempt=attempt, question=question,
                    defaults={'selected_choice': selected_choice},
                )
            attempt.grade()
        messages.success(request, "Exam submitted!")
        return redirect('exams:result_detail', attempt_id=attempt.id)

    # Pre-fill any previously saved answers (e.g. if the page was reloaded).
    existing_answers = {
        a.question_id: a.selected_choice_id for a in attempt.answers.all()
    }

    return render(request, 'exams/take_exam.html', {
        'attempt': attempt,
        'exam': attempt.exam,
        'questions': questions,
        'existing_answers': existing_answers,
        'seconds_remaining': attempt.seconds_remaining,
    })


@student_required
def result_detail(request, attempt_id):
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related('exam'), id=attempt_id, student=request.user
    )
    if attempt.status == ExamAttempt.Status.IN_PROGRESS:
        return redirect('exams:take_exam', attempt_id=attempt.id)

    answers = attempt.answers.select_related('question', 'selected_choice').prefetch_related(
        'question__choices'
    ).order_by('question__order')
    return render(request, 'exams/attempt_review.html', {
        'attempt': attempt, 'answers': answers, 'is_teacher_view': False,
    })


@student_required
def my_results(request):
    attempts = ExamAttempt.objects.filter(
        student=request.user
    ).exclude(status=ExamAttempt.Status.IN_PROGRESS).select_related('exam')
    return render(request, 'exams/my_results.html', {'attempts': attempts})
