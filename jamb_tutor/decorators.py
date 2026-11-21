from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from . import billing


def _login_redirect(request):
    return redirect(f"{reverse('accounts:login')}?{urlencode({'next': request.get_full_path()})}")


def jamb_student_required(view):
    """Logged-in user who signed up as a JAMB student."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _login_redirect(request)
        if not hasattr(request.user, 'jamb_profile'):
            messages.info(request, "That page is for JAMB students.")
            return redirect('accounts:dashboard')
        return view(request, *args, **kwargs)
    return wrapper


def subscription_required(view):
    """JAMB student with an active subscription (mock exams and AI Teacher)."""
    @wraps(view)
    @jamb_student_required
    def wrapper(request, *args, **kwargs):
        if not billing.user_has_access(request.user):
            messages.warning(request, "Subscribe to unlock mock exams and your AI Teacher.")
            return redirect('jamb_tutor:subscribe')
        return view(request, *args, **kwargs)
    return wrapper


def jamb_admin_required(view):
    """Staff only. Teachers sign themselves up, so they don't get access to the shared question bank."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return _login_redirect(request)
        if not (user.is_active and (user.is_staff or user.is_superuser)):
            messages.error(request, "Only site admins can manage the JAMB question bank.")
            return redirect('accounts:dashboard')
        return view(request, *args, **kwargs)
    return wrapper
