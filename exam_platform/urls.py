"""exam_platform URL configuration."""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from django.conf import settings
from django.conf.urls.static import static

from . import views


from django.http import JsonResponse
import os


def debug_static(request):
    path = os.path.join(
        settings.STATIC_ROOT,
        "images",
        "logo.png"
    )

    return JsonResponse({
        "STATIC_ROOT": str(settings.STATIC_ROOT),
        "logo_exists": os.path.exists(path),
        "logo_path": path,
    })    


urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('exams/', include('exams.urls')),

    path('payments/', include('payments.urls')),
    path('', views.Home, name="home"),
    path('contact', views.contact_view, name='contact'),

    path("debug-static/", debug_static),
]
 
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT
    )