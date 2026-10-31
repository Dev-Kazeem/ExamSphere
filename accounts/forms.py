from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import CustomUser


class StudentSignUpForm(UserCreationForm):
    LEVEL_CHOICES = [
        ('100', '100 Level'),
        ('200', '200 Level'),
        ('300', '300 Level'),
        ('400', '400 Level'),
        ('500', '500 Level'),
    ]
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True, max_length=150)
    last_name = forms.CharField(required=True, max_length=150)
    roll_number = forms.CharField(required=False, max_length=50, label="Matric Number")
    grade_level = forms.ChoiceField(required=False, label="Level", choices=LEVEL_CHOICES)

    class Meta:
        model = CustomUser
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'roll_number', 'grade_level', 'password1', 'password2',
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = CustomUser.Role.STUDENT
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.roll_number = self.cleaned_data.get('roll_number', '')
        user.grade_level = self.cleaned_data.get('grade_level', '')
        user.is_active = False  # activated once the email link is clicked
        if commit:
            user.save()
        return user


class TeacherSignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True, max_length=150)
    last_name = forms.CharField(required=True, max_length=150)
    department = forms.CharField(required=False, max_length=100, label="Department / Subject Area")

    class Meta:
        model = CustomUser
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'department', 'password1', 'password2',
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = CustomUser.Role.TEACHER
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.department = self.cleaned_data.get('department', '')
        user.is_active = False  # activated once the email link is clicked
        if commit:
            user.save()
        return user


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'email', 'phone_number', 'bio',
            'profile_picture', 'department', 'roll_number', 'grade_level',
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3}),
            'profile_picture': forms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hide teacher/student-only fields based on the instance's role.
        if self.instance and self.instance.pk:
            if self.instance.is_student:
                self.fields.pop('department', None)
            elif self.instance.is_teacher:
                self.fields.pop('roll_number', None)
                self.fields.pop('grade_level', None)


class EmailAwareAuthenticationForm(AuthenticationForm):
    """
    Same as Django's login form, but gives a specific, actionable message
    when the account exists and the password is correct but the email
    hasn't been verified yet (i.e. is_active=False).
    """

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise forms.ValidationError(
                "Please verify your email address before logging in. "
                "Check your inbox for the verification link, or use the "
                "'Resend verification email' link below.",
                code='inactive',
            )


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(label="Your email address")
