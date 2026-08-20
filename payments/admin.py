from django.contrib import admin
from .models import Semester, SemesterSubscription

# Register your models here.
admin.site.register(Semester)
admin.site.register(SemesterSubscription)