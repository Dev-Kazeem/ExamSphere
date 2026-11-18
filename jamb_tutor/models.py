from django.db import models
from django.conf import settings

class JambProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='jambprofile')
    preferred_language = models.CharField(max_length=20, default="Pidgin")
    target_school = models.CharField(max_length=100, default="UNIJOS")
    target_score = models.IntegerField(default=250)
    combination = models.CharField(max_length=50, default="Science")
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.user.first_name} - {self.target_school}"

class JambQuestion(models.Model):
    subject = models.CharField(max_length=50)
    topic = models.CharField(max_length=100, blank=True)
    question_text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_option = models.CharField(max_length=1, choices=[('A','A'),('B','B'),('C','C'),('D','D')])
    explanation = models.TextField()
    year = models.IntegerField(default=2024)
    def __str__(self): return self.question_text[:60]

class JambMockExam(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject = models.CharField(max_length=50)
    score = models.IntegerField()
    total = models.IntegerField()
    score_400 = models.IntegerField(default=0)
    date_taken = models.DateTimeField(auto_now_add=True)

class JambChat(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    question = models.TextField()
    answer = models.TextField()
    language = models.CharField(max_length=20, default="Pidgin")
    created_at = models.DateTimeField(auto_now_add=True)

class WhatsAppSession(models.Model):
    phone = models.CharField(max_length=20, unique=True)
    language = models.CharField(max_length=20, default="Pidgin")
    name = models.CharField(max_length=100, blank=True)
    current_q_id = models.IntegerField(null=True, blank=True)
    score = models.IntegerField(default=0)
    questions_answered = models.IntegerField(default=0)
    state = models.CharField(max_length=20, default="idle") # idle, drilling, asking
    updated_at = models.DateTimeField(auto_now=True)