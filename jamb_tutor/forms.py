from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .doc_import import MAX_FILE_SIZE
from .logic import normalize_phone, split_full_name
from .models import JambProfile, Subject

User = get_user_model()


class JambSignupForm(UserCreationForm):
    full_name = forms.CharField(max_length=150, label="Full name")
    phone = forms.CharField(
        max_length=20, label="WhatsApp phone number",
        help_text="Use the number you chat on. Your WhatsApp teacher recognises you by it.",
    )
    email = forms.EmailField(help_text="We'll send a link to verify it.")
    preferred_language = forms.ChoiceField(
        choices=JambProfile.Language.choices, initial=JambProfile.Language.ENGLISH,
        label="Language you want lessons in",
    )
    target_school = forms.CharField(max_length=150, label="Target school", help_text="e.g. University of Ibadan")
    target_score = forms.IntegerField(
        min_value=100, max_value=400, initial=250, label="Target score",
        help_text="JAMB is scored out of 400.",
    )
    combination = forms.ChoiceField(
        choices=JambProfile.Combination.choices, widget=forms.RadioSelect, label="Subject combination",
    )

    field_order = [
        'full_name', 'username', 'phone', 'email', 'password1', 'password2',
        'preferred_language', 'target_school', 'target_score', 'combination',
    ]

    class Meta(UserCreationForm.Meta):
        model = User

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try logging in.")
        return email

    def clean_phone(self):
        raw = self.cleaned_data['phone']
        try:
            digits = normalize_phone(raw)
        except ValueError as exc:
            raise forms.ValidationError(str(exc))
        if JambProfile.objects.filter(phone_e164=digits).exists():
            raise forms.ValidationError("This phone number is already registered.")
        self._phone_raw = raw.strip()
        self._phone_digits = digits
        return digits

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        data = self.cleaned_data
        user.first_name, user.last_name = split_full_name(data['full_name'])
        user.email = data['email']
        user.phone_number = self._phone_raw[:20]
        user.role = User.Role.STUDENT
        user.is_active = False                    # activated by the email link
        user.save()
        JambProfile.objects.create(
            user=user,
            preferred_language=data['preferred_language'],
            target_school=data['target_school'].strip(),
            target_score=data['target_score'],
            combination=data['combination'],
            phone_e164=self._phone_digits,
        )
        return user


class CsvUploadForm(forms.Form):
    file = forms.FileField(
        label="Questions CSV",
        help_text="UTF-8 CSV, up to 4 MB.",
        widget=forms.FileInput(attrs={'accept': '.csv'}),
    )

    def clean_file(self):
        f = self.cleaned_data['file']
        if not f.name.lower().endswith('.csv'):
            raise forms.ValidationError("Upload a .csv file.")
        if f.size > MAX_FILE_SIZE:
            raise forms.ValidationError("File is too large. The limit is 4 MB.")
        return f


class DocumentUploadForm(forms.Form):
    file = forms.FileField(
        label="Past-question document",
        help_text="PDF or Word (.docx), up to 4 MB. Scanned PDFs work too.",
        widget=forms.FileInput(attrs={'accept': '.pdf,.docx,.doc'}),
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(), required=False, empty_label="Let the AI detect it",
        help_text="If the whole file is one subject, choose it. It's more reliable.",
    )
    year = forms.IntegerField(
        required=False, min_value=1978, max_value=2100, label="Exam year",
        help_text="Optional. Applied to every question that doesn't show its own year.",
    )

    def clean_file(self):
        f = self.cleaned_data['file']
        if f.size > MAX_FILE_SIZE:
            raise forms.ValidationError("File is too large. The limit is 4 MB.")
        return f
