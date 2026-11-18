from django.contrib import admin
from .models import JambQuestion, JambProfile, JambMockExam


admin.site.register(JambQuestion)
admin.site.register(JambProfile)
admin.site.register(JambMockExam)