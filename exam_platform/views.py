from django.shortcuts import render, redirect

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from .forms import ContactForm


def Home(request):
    return render(request, 'base.html' )


def contact_view(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            send_mail(
                subject=f"[Contact] {form.cleaned_data['subject']}",
                message=f"From: {form.cleaned_data['name']} <{form.cleaned_data['email']}>\n\n{form.cleaned_data['message']}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_FROM_EMAIL],  # your support inbox
                fail_silently=False,
            )
            messages.success(request, "Thanks — we'll get back to you soon.")
            return redirect('contact')
    else:
        form = ContactForm()
    return render(request, 'contact.html', {'form': form})