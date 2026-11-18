# urls.py
from django.urls import path
from . import views
urlpatterns = [
    path('signup/', views.jamb_signup, name='jamb_signup'),
    path('dashboard/', views.jamb_dashboard, name='jamb_dashboard'),
    path('mock/', views.jamb_mock, name='jamb_mock'),
    path('ask/', views.jamb_ask, name='jamb_ask'),
    path('verify/<uidb64>/<token>/', views.jamb_verify_email, name='jamb_verify_email'),
]
