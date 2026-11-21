"""
Read configuration from Django settings first, then environment variables.

That way the app works as soon as the variables exist in .env / Vercel,
without having to edit settings.py for each one.
"""
import os

from django.conf import settings


def get(name, default=''):
    value = getattr(settings, name, None)
    if value in (None, ''):
        value = os.environ.get(name, default)
    return value


def get_bool(name, default=True):
    value = get(name, None)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def get_int(name, default):
    try:
        return int(get(name, default))
    except (TypeError, ValueError):
        return default
