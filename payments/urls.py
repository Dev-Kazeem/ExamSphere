from django.urls import path
from . import views

app_name = 'payments'
urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),
    path('semester/<int:semester_id>/pay/', views.initiate_payment, name='initiate'),
    path('verify/', views.verify_payment, name='verify'),
    path('webhook/', views.flutterwave_webhook, name='webhook'),
]