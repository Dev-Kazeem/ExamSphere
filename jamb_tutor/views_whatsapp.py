import hmac
import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from . import conf, logic, whatsapp

logger = logging.getLogger(__name__)


@csrf_exempt
def webhook(request):
    """Meta calls this URL: GET once to verify it, then POST for every incoming message."""
    if request.method == 'GET':
        expected = conf.get('WHATSAPP_VERIFY_TOKEN')
        token = request.GET.get('hub.verify_token', '')
        if expected and request.GET.get('hub.mode') == 'subscribe' and hmac.compare_digest(token, expected):
            return HttpResponse(request.GET.get('hub.challenge', ''), content_type='text/plain')
        return HttpResponse(status=403)

    if request.method != 'POST':
        return HttpResponse(status=405)

    raw = request.body
    if not logic.verify_signature(raw, request.headers.get('X-Hub-Signature-256', ''), conf.get('WHATSAPP_APP_SECRET')):
        return HttpResponse(status=401)

    try:
        payload = json.loads(raw)
    except ValueError:
        return HttpResponse(status=400)

    for message in logic.extract_messages(payload):
        try:
            whatsapp.handle_incoming(message)
        except Exception:                       # never return an error: Meta would retry for days
            logger.exception('Failed to handle WhatsApp message %s', message.get('id'))
    return HttpResponse('ok')
