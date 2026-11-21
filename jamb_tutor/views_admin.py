import csv
import logging

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import ai, doc_import
from .constants import CSV_COLUMNS, SUBJECT_NAMES
from .decorators import jamb_admin_required
from .forms import CsvUploadForm, DocumentUploadForm
from .importers import save_rows
from .logic import FileProblem, clean_question_row, parse_question_csv
from .models import ImportJob, Question, Subject

logger = logging.getLogger(__name__)
FIELDS = ('subject', 'topic', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d',
          'correct_option', 'explanation', 'year')


@jamb_admin_required
def manage_home(request):
    per_subject = Subject.objects.annotate(q_count=Count('questions'))
    return render(request, 'jamb_tutor/manage/home.html', {
        'total': Question.objects.count(),
        'per_subject': per_subject,
        'jobs': ImportJob.objects.defer('source_pdf', 'chunks', 'extracted')[:8],
        'ai_ready': ai.is_configured(),
    })


# ==========================================================================
# CSV
# ==========================================================================
@jamb_admin_required
def csv_upload(request):
    form = CsvUploadForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == 'POST' and form.is_valid():
        try:
            rows, problems = parse_question_csv(form.cleaned_data['file'].read())
        except FileProblem as exc:
            form.add_error('file', str(exc))
        else:
            saved = save_rows(rows, request.user)
            result = {
                'added': saved['added'],
                'duplicates': saved['duplicates'],
                'invalid': len(problems),
                'problems': problems[:50],
                'more_problems': max(0, len(problems) - 50),
            }
    return render(request, 'jamb_tutor/manage/csv_upload.html', {
        'form': form, 'result': result, 'columns': CSV_COLUMNS,
    })


@jamb_admin_required
def csv_sample(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="jamb_questions_template.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(CSV_COLUMNS)
    writer.writerow(['Maths', 'Algebra', 'If 2x + 3 = 11, what is the value of x?', '2', '4', '6', '8', 'B',
                     '2x = 11 - 3 = 8, so x = 4.', 2019])
    writer.writerow(['Biology', 'Cell Biology', 'Which organelle is the site of aerobic respiration?',
                     'Ribosome', 'Nucleus', 'Mitochondrion', 'Golgi body', 'C',
                     'Mitochondria release energy from glucose using oxygen.', ''])
    return response


# ==========================================================================
# PDF / DOCX through Gemini
# ==========================================================================
@jamb_admin_required
def document_upload(request):
    form = DocumentUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        if not ai.is_configured():
            form.add_error('file', "Gemini isn't configured. Set GEMINI_API_KEY first.")
        else:
            try:
                job = doc_import.create_job(
                    form.cleaned_data['file'], request.user,
                    default_subject=form.cleaned_data['subject'],
                    default_year=form.cleaned_data['year'],
                )
            except FileProblem as exc:
                form.add_error('file', str(exc))
            else:
                return redirect('jamb_tutor:manage_import', job_id=job.pk)
    return render(request, 'jamb_tutor/manage/doc_upload.html', {'form': form, 'ai_ready': ai.is_configured()})


def _drafts_from_job(job):
    drafts = []
    for row in job.extracted:
        draft = dict(row)
        draft['include'] = not row.get('error')
        drafts.append(draft)
    return drafts


def _drafts_from_post(post):
    try:
        total = max(0, min(int(post.get('total', 0)), 1000))
    except ValueError:
        total = 0
    drafts = []
    for i in range(total):
        raw = {key: post.get(f'{key}_{i}', '') for key in FIELDS}
        row, error = clean_question_row(raw)
        row['answer_source'] = post.get(f'answer_source_{i}', 'document')
        row['error'] = error
        row['include'] = post.get(f'include_{i}') == 'on'
        drafts.append(row)
    return drafts


@jamb_admin_required
def import_job(request, job_id):
    job = get_object_or_404(ImportJob.objects.defer('source_pdf', 'chunks'), pk=job_id)
    context = {'job': job, 'subject_names': SUBJECT_NAMES}
    if job.status == ImportJob.Status.READY:
        drafts = _drafts_from_job(job)
        context.update(
            drafts=drafts,
            flagged=sum(1 for d in drafts if d.get('error')),
            ai_guessed=sum(1 for d in drafts if d.get('answer_source') == 'ai'),
        )
    return render(request, 'jamb_tutor/manage/import_job.html', context)


@require_POST
@jamb_admin_required
def import_process(request, job_id):
    """Extract the next part of the document. The page calls this repeatedly until it is done."""
    skip = request.POST.get('skip') == '1'
    try:
        job = doc_import.process_next_chunk(job_id, skip=skip)
    except ImportJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found.'}, status=404)
    except ai.AIUnavailable as exc:
        return JsonResponse({'error': str(exc)}, status=502)
    except Exception as exc:
        logger.exception('Document import failed on job %s', job_id)
        return JsonResponse({'error': f'Unexpected error: {exc}'}, status=500)
    return JsonResponse({
        'done': job.next_chunk,
        'total': job.total_chunks,
        'finished': job.status != ImportJob.Status.PROCESSING,
        'found': len(job.extracted),
    })


@require_POST
@jamb_admin_required
def import_save(request, job_id):
    job = get_object_or_404(ImportJob, pk=job_id)
    if job.status != ImportJob.Status.READY:
        return redirect('jamb_tutor:manage_import', job_id=job.pk)

    drafts = _drafts_from_post(request.POST)
    chosen = [d for d in drafts if d['include']]
    bad = [d for d in chosen if d['error']]
    if bad:
        messages.error(request, f"{len(bad)} ticked question(s) still have problems. Fix or untick them, then save again.")
        return render(request, 'jamb_tutor/manage/import_job.html', {
            'job': job, 'subject_names': SUBJECT_NAMES, 'drafts': drafts,
            'flagged': sum(1 for d in drafts if d['error']),
            'ai_guessed': sum(1 for d in drafts if d.get('answer_source') == 'ai'),
        })
    if not chosen:
        messages.error(request, "Tick at least one question to save.")
        return redirect('jamb_tutor:manage_import', job_id=job.pk)

    saved = save_rows(chosen, request.user)
    job.status = ImportJob.Status.SAVED
    job.result = {'added': saved['added'], 'duplicates': saved['duplicates'], 'unticked': len(drafts) - len(chosen)}
    job.extracted = []
    job.source_pdf = None
    job.chunks = []
    job.save()
    messages.success(request, f"Added {saved['added']} question(s). Skipped {saved['duplicates']} duplicate(s).")
    return redirect('jamb_tutor:manage_import', job_id=job.pk)


@jamb_admin_required
def import_export_csv(request, job_id):
    """Download the extracted questions in the same layout as the CSV upload."""
    job = get_object_or_404(ImportJob, pk=job_id)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="extracted_{job.pk}.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(CSV_COLUMNS)
    for row in job.extracted:
        writer.writerow([row.get(column, '') for column in CSV_COLUMNS])
    return response
