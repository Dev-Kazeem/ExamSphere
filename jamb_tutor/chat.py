"""Chat helpers shared by the web chat and the WhatsApp bot."""
from datetime import timedelta

from django.utils import timezone

from . import conf
from .models import ChatMessage


def site_url(path=''):
    base = (conf.get('SITE_URL') or '').rstrip('/')
    return f'{base}{path}'


def recent_history(user, limit=8):
    """Last `limit` AI-teacher messages (web and WhatsApp), oldest first."""
    rows = list(
        ChatMessage.objects.filter(user=user, kind=ChatMessage.Kind.AI)
        .order_by('-id').values_list('role', 'content')[:limit]
    )
    return rows[::-1]


def rate_limited(user):
    """Caps AI questions per hour so one student can't run up the Gemini bill."""
    limit = conf.get_int('JAMB_AI_MESSAGES_PER_HOUR', 40)
    since = timezone.now() - timedelta(hours=1)
    asked = ChatMessage.objects.filter(
        user=user, role=ChatMessage.Role.USER, kind=ChatMessage.Kind.AI, created_at__gte=since
    ).count()
    return asked >= limit
