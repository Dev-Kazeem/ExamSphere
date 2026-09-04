from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet

from .models import Exam, Question, Choice


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = [
            'title', 'description', 'subject', 'duration_minutes',
            'start_time', 'end_time', 'pass_percentage', 'semester','max_attempts',
            'shuffle_questions', 'is_published',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['start_time'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['end_time'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_time')
        end = cleaned_data.get('end_time')
        if start and end and end <= start:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned_data


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['text', 'marks', 'order', 'explanation']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 2}),
            'explanation': forms.Textarea(attrs={'rows': 2}),
        }


class BaseChoiceFormSet(BaseInlineFormSet):
    """Ensures a question has at least 2 filled options and exactly one correct answer."""

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        filled_forms = [
            f for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get('DELETE', False) and f.cleaned_data.get('text')
        ]
        if len(filled_forms) < 2:
            raise forms.ValidationError("Each question needs at least 2 answer choices.")

        correct_count = sum(1 for f in filled_forms if f.cleaned_data.get('is_correct'))
        if correct_count == 0:
            raise forms.ValidationError("Mark exactly one choice as the correct answer.")
        if correct_count > 1:
            raise forms.ValidationError("Only one choice can be marked correct.")


ChoiceFormSet = inlineformset_factory(
    Question,
    Choice,
    formset=BaseChoiceFormSet,
    fields=['text', 'is_correct'],
    extra=4,
    max_num=6,
    can_delete=True,
)
