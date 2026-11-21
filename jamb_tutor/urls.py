from django.urls import path

from . import views, views_admin, views_whatsapp

app_name = 'jamb_tutor'

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('dashboard/', views.dashboard, name='dashboard'),

    path('topics/', views.topics, name='topics'),
    path('topics/<slug:slug>/', views.topic_detail, name='topic_detail'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),

    path('mock/', views.mock_start, name='mock_start'),
    path('mock/history/', views.mock_history, name='mock_history'),
    path('mock/<int:attempt_id>/', views.mock_take, name='mock_take'),
    path('mock/<int:attempt_id>/answer/', views.mock_autosave, name='mock_autosave'),
    path('mock/<int:attempt_id>/result/', views.mock_result, name='mock_result'),
    path('mock/<int:attempt_id>/review/', views.mock_review, name='mock_review'),

    path('teacher/', views.teacher_chat, name='teacher_chat'),
    path('teacher/send/', views.teacher_send, name='teacher_send'),
    path('teacher/history/', views.teacher_history, name='teacher_history'),

    path('subscribe/', views.subscribe, name='subscribe'),
    path('subscribe/<int:plan_id>/pay/', views.subscribe_pay, name='subscribe_pay'),
    path('subscribe/verify/', views.subscribe_verify, name='subscribe_verify'),

    path('whatsapp/webhook/', views_whatsapp.webhook, name='whatsapp_webhook'),

    path('manage/', views_admin.manage_home, name='manage_home'),
    path('manage/csv/', views_admin.csv_upload, name='manage_csv'),
    path('manage/csv/sample/', views_admin.csv_sample, name='manage_csv_sample'),
    path('manage/document/', views_admin.document_upload, name='manage_document'),
    path('manage/import/<int:job_id>/', views_admin.import_job, name='manage_import'),
    path('manage/import/<int:job_id>/process/', views_admin.import_process, name='manage_import_process'),
    path('manage/import/<int:job_id>/save/', views_admin.import_save, name='manage_import_save'),
    path('manage/import/<int:job_id>/csv/', views_admin.import_export_csv, name='manage_import_csv'),
]
