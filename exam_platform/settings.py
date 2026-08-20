"""
Django settings for exam_platform project.

Online Multiple-Choice Exam Platform
Two user roles: Student and Teacher.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------
# SECURITY
# -----------------------------------------------------------------------
# In production, set this via an environment variable and NEVER commit
# a real secret key to version control.
SECRET_KEY = os.environ.get('SECRET_KEY')

DEBUG = os.environ.get('DEBUG')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS').split(',')

# -----------------------------------------------------------------------
# APPLICATION DEFINITION
# -----------------------------------------------------------------------
INSTALLED_APPS = [
     'jazzmin',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Third-party
    'crispy_forms',
    'crispy_bootstrap5',
   

    # Local apps
    'accounts',
    'exams',
    'payments',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'exam_platform.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'exam_platform.wsgi.application'
ASGI_APPLICATION = 'exam_platform.asgi.application'

# -----------------------------------------------------------------------
# DATABASE
# -----------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# -----------------------------------------------------------------------
# PASSWORD VALIDATION
# -----------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# -----------------------------------------------------------------------
# CUSTOM USER MODEL
# -----------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.CustomUser'

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'accounts:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

# -----------------------------------------------------------------------
# INTERNATIONALIZATION
# -----------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# -----------------------------------------------------------------------
# STATIC & MEDIA FILES
# -----------------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -----------------------------------------------------------------------
# CRISPY FORMS
# -----------------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# -----------------------------------------------------------------------
# SESSION / SECURITY HARDENING (sane defaults; tune for production)
# -----------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours

# When DEBUG is False, force extra hardening (enable these behind HTTPS)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# -----------------------------------------------------------------------
# MESSAGES
# -----------------------------------------------------------------------
from django.contrib.messages import constants as messages_constants  # noqa: E402
MESSAGE_TAGS = {
    messages_constants.DEBUG: 'secondary',
    messages_constants.INFO: 'info',
    messages_constants.SUCCESS: 'success',
    messages_constants.WARNING: 'warning',
    messages_constants.ERROR: 'danger',
}


# -------------------------------------------------------------------------
# EMAIL SERVICES
# -------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '10'))  # seconds — don't hang forever if the provider is down

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@yourdomain.com')
SERVER_EMAIL = os.environ.get('DJANGO_SERVER_EMAIL', DEFAULT_FROM_EMAIL)  # for Django's internal error emails

CONTACT_RECIPIENT_EMAIL = os.environ.get('CONTACT_RECIPIENT_EMAIL', DEFAULT_FROM_EMAIL)

# So Django emails you (ADMINS) when a 500 error happens in production
ADMINS = [tuple(pair.split(':')) for pair in os.environ.get('ADMINS', '').split(',') if ':' in pair]


# ----------------------------------------------------------------
# FLUTTER WAVE CONFIGURATION
# ----------------------------------------------------------------
FLUTTERWAVE_PUBLIC_KEY = os.environ.get('FLUTTERWAVE_PUBLIC_KEY', '')
FLUTTERWAVE_SECRET_KEY = os.environ.get('FLUTTERWAVE_SECRET_KEY', '')
FLUTTERWAVE_WEBHOOK_SECRET = os.environ.get('FLUTTERWAVE_WEBHOOK_SECRET', '')


#------------------------------------------------------------------
# CUSTOMIZING DJANGO ADMIN PANEL USING JAZZMIN
#------------------------------------------------------------------
JAZZMIN_SETTINGS = {
    "site_title": "ExamSphere |Admin",
    "site_header": "ExamSphere",
    "site_brand": "ExamSphere",
    "welcome_sign": "Welcome to ExamSphere Administration",

    "custom_css": "css/admin-custom.css",
    "show_sidebar": True,
    "navigation_expanded": True,

    "icons": {
        "students.Student": "fas fa-user-graduate",
        "exams.Exam": "fas fa-file-alt",
        "exams.Question": "fas fa-question-circle",
        "exams.Result": "fas fa-chart-bar",
        "auth.User": "fas fa-user",
        "auth.Group": "fas fa-users",
    },


    "topmenu_links": [
        {
            "name": "Home",
            "url": "home",
            "permissions": ["auth.view_user"],
            "icon": "fas fa-home",
        },

        {
            "name": "My Dashboard",
            "url": "accounts:dashboard",
            "icon": "fas fa-tachometer-alt",
        },
    ],
}

JAZZMIN_UI_TWEAKS = {
    "sidebar": "sidebar-dark-primary",
}