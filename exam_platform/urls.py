"""exam_platform URL configuration."""
from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static
from core import error_views

from . import views


urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Application url  
    path('accounts/', include('accounts.urls')),
    path('exams/', include('exams.urls')),
    path('payments/', include('payments.urls')),

    # Main pages
    path('', views.Home, name="home"),
    path('contact', views.contact_view, name='contact'),

]


# Custom error handlers
handler400 = 'core.error_views.error_400'
handler403 = 'core.error_views.error_403'
handler404 = 'core.error_views.error_404'
handler500 = 'core.error_views.error_500'

# Development-only media and error testing routes 
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    urlpatterns += [
            path('_errors/404/', error_views.error_404),
            path('_errors/403/', error_views.error_403),
            path('_errors/400/', error_views.error_400),
            path('_errors/500/', error_views.error_500),
            path('_errors/csrf/', error_views.csrf_failure),
        ]