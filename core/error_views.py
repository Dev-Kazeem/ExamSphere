import logging

from django.http import HttpResponseBadRequest, HttpResponseServerError, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _wants_json(request):
    accept = request.headers.get('Accept', '')
    return request.path.startswith('/api/') or (
        'application/json' in accept and 'text/html' not in accept
    )


def error_404(request, exception=None):
    if _wants_json(request):
        return JsonResponse({'detail': 'Not found.'}, status=404)
    return render(request, 'errors/404.html', status=404)


def error_403(request, exception=None):
    if _wants_json(request):
        return JsonResponse({'detail': 'You do not have permission to do that.'}, status=403)
    return render(request, 'errors/403.html', status=403)


def csrf_failure(request, reason=''):
    # Log the real reason for you; never show it to the visitor.
    logger.warning("CSRF failure on %s: %s", request.path, reason)
    if _wants_json(request):
        return JsonResponse({'detail': 'CSRF verification failed.'}, status=403)
    return render(request, 'errors/csrf.html', status=403)


def error_400(request, exception=None):
    if _wants_json(request):
        return JsonResponse({'detail': 'Bad request.'}, status=400)
    return HttpResponseBadRequest(render_to_string('errors/400.html'))


def error_500(request):
    # Deliberately rendered without the request/context processors: if the
    # database or a context processor is what broke, using them here would
    # cause a second failure while trying to show the error page.
    if _wants_json(request):
        return JsonResponse({'detail': 'Server error. Please try again later.'}, status=500)
    return HttpResponseServerError(render_to_string('errors/500.html'))