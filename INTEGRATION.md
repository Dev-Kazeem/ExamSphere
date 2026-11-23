# JAMB Tutor: integration guide

Copy the `jamb_tutor/` folder into your project root (next to `manage.py`). Templates live inside
the app (`jamb_tutor/templates/jamb_tutor/`), so nothing else needs copying.

## 1. Install
```
pip install google-genai pypdf python-docx requests
```
requirements.txt: `google-genai`, `pypdf>=4.0`, `python-docx>=1.1`, `requests` (the rest you already have).

## 2. settings.py
```python
INSTALLED_APPS = [ ..., 'jamb_tutor' ]
```
Everything else is read from environment variables (see section 8), so no other settings edits are needed...        



## 3. exam_platform/urls.py
```python
path('jamb/', include('jamb_tutor.urls')),
```

## 4. accounts/views.py: send JAMB students to their own dashboard
```python
@login_required
def dashboard_redirect(request):
    if hasattr(request.user, 'jamb_profile'):                 # <-- add these two lines
        return redirect('jamb_tutor:dashboard')
    if request.user.is_teacher:
        return redirect('exams:teacher_dashboard')
    return redirect('exams:student_dashboard')
```
This one function covers normal login AND the redirect after email verification.

## 5. templates/base.html: navbar
Change `{% if user.is_teacher %} ... {% else %} ... {% endif %}` to:
```django
{% if user.jamb_profile %}
    <li class="nav-item"><a class="nav-link" href="{% url 'jamb_tutor:dashboard' %}">JAMB Tutor</a></li>
{% elif user.is_teacher %}
    ...your existing teacher links...
{% else %}
    ...your existing student links...
{% endif %}
{% if user.is_staff %}
    <li class="nav-item"><a class="nav-link" href="{% url 'jamb_tutor:manage_home' %}">JAMB question bank</a></li>
{% endif %}
```

## 6. templates/accounts/register_landing.html: the "Sign up as JAMB Student" option
Add next to the Student and Teacher choices:
```django
<a href="{% url 'jamb_tutor:signup' %}" class="btn btn-success w-100">Sign up as a JAMB student</a>
```

## 7. payments/views.py: let the existing Flutterwave webhook confirm JAMB payments
Flutterwave allows ONE webhook URL per account, so JAMB payments (references start with `jt-`) are
routed from your existing handler. In `flutterwave_webhook`, after you parse `payload` and `data`:
```python
data = payload.get("data") or {}
if str(data.get("tx_ref", "")).startswith("jt-"):
    from jamb_tutor.billing import handle_flutterwave_event
    handle_flutterwave_event(data)
    return JsonResponse({"status": "ok"})
```
(Without this the subscribe page still repairs missed payments when the student reloads it.)

## 8. Environment variables (.env locally, Vercel dashboard in production)
```
GEMINI_API_KEY=
GEMINI_MODEL=gemini-flash-latest      # pin a specific stable model for production
SITE_URL=https://yourdomain.com       # used for links inside WhatsApp messages

WHATSAPP_VERIFY_TOKEN=any-long-random-string-you-choose
WHATSAPP_APP_SECRET=                  # Meta app > Settings > Basic > App secret
WHATSAPP_ACCESS_TOKEN=                # permanent system-user token
WHATSAPP_PHONE_NUMBER_ID=

JAMB_REQUIRE_SUBSCRIPTION=True        # False = everything open (handy while testing)
```
Optional: `GEMINI_EXTRACTION_MODEL`, `GEMINI_TIMEOUT_SECONDS` (25), `JAMB_AI_MESSAGES_PER_HOUR` (40),
`JAMB_PDF_PAGES_PER_CHUNK` (2), `WHATSAPP_GRAPH_VERSION` (v24.0).
`FLUTTERWAVE_SECRET_KEY` is the one you already have.

## 9. Migrate
```
python manage.py makemigrations jamb_tutor
python manage.py migrate
```
The nine subjects are created automatically after `migrate`.

## 10. First-time setup in Django admin
1. **JAMB plans:** add at least one (for example "1 month", 30 days, price).
2. Give your own account `is_staff` (superusers already have it) to see the question bank pages.
3. Upload questions: `/jamb/manage/` > CSV or PDF/Word.
4. To give someone free access: JAMB subscriptions > add one with a plan > action "Grant access".

## 11. WhatsApp (Meta Cloud API)
1. developers.facebook.com > create an app > add the WhatsApp product.
2. Webhook callback URL: `https://yourdomain.com/jamb/whatsapp/webhook/`, verify token = `WHATSAPP_VERIFY_TOKEN`.
3. Subscribe the webhook to the **messages** field.
4. Copy the Phone number ID and a permanent access token into the env vars.
5. While the app is in development mode, only numbers you add as test recipients can message the bot.
6. Students must sign up with the same number they use on WhatsApp.

## 12. Vercel notes
* If vercel.json still has `maxLambdaSize: 15mb`, raise it (e.g. 100mb) or remove it: google-genai,
  pypdf, python-docx and Pillow together are larger than that.
* Gemini replies take a few seconds. If your plan's function time limit is very short, raise it
  (document import is already split into small parts for this reason).

## 13. Run the tests
```
python manage.py test jamb_tutor
```
