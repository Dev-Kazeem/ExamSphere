from django import forms


class ContactForm(forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 5}))
    # honeypot — real users never fill this; bots usually do
    website = forms.CharField(required=False, widget=forms.HiddenInput())

    def clean_website(self):
        if self.cleaned_data.get('website'):
            raise forms.ValidationError("Spam detected.")
        return self.cleaned_data['website']