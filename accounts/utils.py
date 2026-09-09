from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import account_activation_token


def send_verification_email(request, user):
    """Build a signed activation link and email it to the user."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_activation_token.make_token(user)

    if request is not None:
        domain = get_current_site(request).domain
        protocol = 'https' if request.is_secure() else 'http'
    else:
        domain = getattr(settings, 'DEFAULT_DOMAIN', 'localhost:8000')
        protocol = 'https' if getattr(settings, 'DEFAULT_HTTPS', False) else 'http'

    verify_path = reverse('accounts:verify_email', kwargs={'uidb64': uid, 'token': token})
    verify_url = f"{protocol}://{domain}{verify_path}"

    subject = "Verify your ExamSphere account"
    message = render_to_string('accounts/email/verification_email.txt', {
        'user': user,
        'verify_url': verify_url,
    })
    send_mail(
        subject,
        message,
        getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@examsphere.local'),
        [user.email],
        fail_silently=False,
    )
    return verify_url
