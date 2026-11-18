from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import JambProfile, JambQuestion, JambMockExam, JambChat
from .decorators import jamb_only
from .ai_helper import ask_jamb_ai
import random

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site

User = get_user_model()

@login_required
def home_router(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('university_dashboard')
    if hasattr(request.user, 'jambprofile'):
        return redirect('jamb_dashboard')
    return redirect('university_dashboard')



def jamb_signup(request):
    if request.user.is_authenticated:
        return redirect('account:dashboard')
    
    if request.method == 'POST':
        name = request.POST.get('name','').strip()
        phone = request.POST.get('phone','').strip()
        email = request.POST.get('email','').strip().lower()
        password = request.POST.get('password','')
        language = request.POST.get('language','Pidgin')
        target_school = request.POST.get('target_school') or request.POST.get('target_school_custom') or 'UNIJOS'
        target_score = request.POST.get('target_score', 250)
        combination = request.POST.get('combination','Science')

        if not name or not phone or not email or not password:
            messages.error(request, "Fill name, phone, email and password")
            return render(request, 'jamb_tutor/signup.html')
        
        if User.objects.filter(username=phone).exists():
            messages.error(request, "This phone don register. Login.")
            return redirect('login')
        if User.objects.filter(email=email).exists():
            messages.error(request, "This email don register. Use another email or login.")
            return render(request, 'jamb_tutor/signup.html')

        # Create user but INACTIVE until email verified - same as your other signup
        user = User.objects.create_user(username=phone, email=email, password=password, first_name=name, is_active=False)
        JambProfile.objects.create(user=user, preferred_language=language, target_school=target_school, target_score=int(target_score), combination=combination, phone=phone)

        # Send verification email
        current_site = get_current_site(request)
        subject = 'Verify your JAMB Tutor account'
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        verify_link = f"http://{current_site.domain}/jamb/verify/{uid}/{token}/"
        # For live site, use https automatically - Django handles it via request
        # If you use Vercel, replace above with f"https://{current_site.domain}/jamb/verify/{uid}/{token}/"
        
        message = render_to_string('jamb_tutor/verify_email.html', {
            'user': user,
            'verify_link': verify_link,
        })
        send_mail(subject, message, None, [email], fail_silently=False)

        messages.success(request, f"We sent verification link to {email}. Check inbox / spam and click it.")
        return render(request, 'jamb_tutor/check_email.html', {'email': email})
    
    return render(request, 'jamb_tutor/signup.html')

def jamb_verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except:
        user = None
    
    if user and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        messages.success(request, f"Welcome {user.first_name}! Email verified. 🎉")
        return redirect('account:dashboard')  # Will auto go to jamb_dashboard
    else:
        messages.error(request, "Link don expire or invalid. Signup again.")
        return redirect('jamb_signup')

@jamb_only
def jamb_dashboard(request):
    profile = request.user.jambprofile
    exams = JambMockExam.objects.filter(user=request.user).order_by('-date_taken')[:5]
    last_score = exams[0].score_400 if exams else 0
    return render(request, 'jamb_tutor/dashboard.html', {'profile': profile, 'exams': exams, 'last_score': last_score})

@jamb_only
def jamb_mock(request):
    if request.method == 'POST':
        score=0; total=0
        for key, val in request.POST.items():
            if key.startswith('q_'):
                total+=1
                qid = key.replace('q_','')
                try:
                    q = JambQuestion.objects.get(id=qid)
                    if val == q.correct_option: score+=1
                except: pass
        score_400 = int((score/total*400) if total else 0)
        JambMockExam.objects.create(user=request.user, subject="Mixed", score=score, total=total, score_400=score_400)
        return render(request, 'jamb_tutor/result.html', {'score':score,'total':total,'score_400':score_400,'profile':request.user.jambprofile})
    questions = list(JambQuestion.objects.all().order_by('?')[:10])
    return render(request, 'jamb_tutor/mock.html', {'questions': questions})

@jamb_only
def jamb_ask(request):
    answer=None; question=None
    if request.method=='POST':
        question=request.POST.get('question')
        profile=request.user.jambprofile
        answer=ask_jamb_ai(question, language=profile.preferred_language, student_name=request.user.first_name)
        JambChat.objects.create(user=request.user, question=question, answer=answer, language=profile.preferred_language)
    return render(request, 'jamb_tutor/ask.html', {'answer':answer,'question':question})