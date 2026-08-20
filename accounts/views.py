from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.utils.http import url_has_allowed_host_and_scheme


from .forms import (
    StudentSignUpForm, TeacherSignUpForm, ProfileUpdateForm,
    ResendVerificationForm,
)
from .models import CustomUser
from .tokens import account_activation_token
from .utils import send_verification_email


def register_landing(request):
    """Let the visitor pick Student or Teacher before showing the signup form."""
    return render(request, 'accounts/register_landing.html')

def is_staff_user(user):
    return user.is_staff



def register_student(request):
    if request.method == 'POST':
        form = StudentSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            send_verification_email(request, user)
            return render(request, 'registration/verify_email_sent.html', {'email': user.email})
    else:
        form = StudentSignUpForm()
    return render(request, 'accounts/register.html', {'form': form, 'role': 'Student'})


@user_passes_test(is_staff_user)
def register_teacher(request):
    if request.method == 'POST':
        form = TeacherSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            send_verification_email(request, user)
            return render(request, 'registration/verify_email_sent.html', {'email': user.email})
    else:
        form = TeacherSignUpForm()
    return render(request, 'accounts/register.html', {'form': form, 'role': 'Teacher'})


def login_view(request):
    next_url = request.POST.get('next') or request.GET.get('next')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                # Validate next_url to avoid open redirect vulnerabilities
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    if request.user.is_staff:
                       messages.success(request, f"Welcome back, {user.username}!")
                       return redirect(next_url)
                    else:
                        messages.error(request, "contact admin to get verified.")
                      
                return redirect('accounts:dashboard')  
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, 'registration/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('accounts:login')


def verify_email(request, uidb64, token):
    """Activate the account if the signed link is valid, then log the user in."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
        login(request, user)
        messages.success(request, "Your email is verified — welcome aboard!")
        return redirect('accounts:dashboard')

    return render(request, 'registration/verify_email_invalid.html')


def resend_verification(request):
    if request.method == 'POST':
        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = CustomUser.objects.filter(email__iexact=email, is_active=False).first()
            if user:
                send_verification_email(request, user)
            # Always show the same message, whether or not the address was found,
            # so this endpoint can't be used to probe which emails are registered.
            messages.success(
                request,
                "If that email is registered and unverified, a new verification link is on its way."
            )
            return redirect('accounts:login')
    else:
        form = ResendVerificationForm()
    return render(request, 'registration/resend_verification.html', {'form': form})


@login_required
def dashboard_redirect(request):
    """Send the logged-in user to the correct dashboard for their role."""
    if request.user.is_teacher:
        return redirect('exams:teacher_dashboard')
    return redirect('exams:student_dashboard')


@login_required
def profile_view(request, username=None):
    if username:
        profile_user = get_object_or_404(CustomUser, username=username)
    else:
        profile_user = request.user
    return render(request, 'accounts/profile.html', {'profile_user': profile_user})


@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('accounts:profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    return render(request, 'accounts/profile_edit.html', {'form': form})