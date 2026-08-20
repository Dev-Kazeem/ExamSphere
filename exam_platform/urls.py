"""exam_platform URL configuration."""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from django.conf import settings
from django.conf.urls.static import static

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('exams/', include('exams.urls')),

    path('payments/', include('payments.urls')),
    path('', views.Home, name="home"),
    path('contact', views.contact_view, name='contact'),
]
 
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    