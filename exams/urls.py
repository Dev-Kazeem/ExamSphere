from django.urls import path

from . import views

app_name = 'exams'

urlpatterns = [
    # Teacher
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/create/', views.exam_create, name='exam_create'),
    path('teacher/<int:exam_id>/edit/', views.exam_update, name='exam_update'),
    path('teacher/<int:exam_id>/delete/', views.exam_delete, name='exam_delete'),
    path('teacher/<int:exam_id>/toggle-publish/', views.exam_toggle_publish, name='exam_toggle_publish'),
    path('teacher/<int:exam_id>/questions/', views.manage_questions, name='manage_questions'),
    path('teacher/<int:exam_id>/questions/add/', views.question_create, name='question_create'),
    path('teacher/<int:exam_id>/questions/<int:question_id>/edit/', views.question_update, name='question_update'),
    path('teacher/<int:exam_id>/questions/<int:question_id>/delete/', views.question_delete, name='question_delete'),
    path('teacher/<int:exam_id>/results/', views.exam_results, name='exam_results'),
    path('teacher/attempt/<int:attempt_id>/review/', views.attempt_review_teacher, name='attempt_review_teacher'),

    # bulk_upload
    path('teacher/<int:exam_id>/questions/bulk-upload/', views.bulk_upload, name='bulk_upload'),
    path('teacher/<int:exam_id>/questions/bulk-upload/preview/', views.bulk_upload_preview, name='bulk_upload_preview'),
    path('teacher/questions/bulk-upload/sample.csv', views.bulk_upload_sample_csv, name='bulk_upload_sample'),

    # Student
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('student/<int:exam_id>/start/', views.exam_start, name='exam_start'),
    path('student/attempt/<int:attempt_id>/', views.take_exam, name='take_exam'),
    path('student/attempt/<int:attempt_id>/result/', views.result_detail, name='result_detail'),
    path('student/results/', views.my_results, name='my_results'),
]
