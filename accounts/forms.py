from django import forms

from .models import User


class EmailForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True})
    )

    def clean_email(self):
        return self.cleaned_data["email"].lower()


class RegistrationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "sex"]
        widgets = {
            "sex": forms.RadioSelect,
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
        }
        help_texts = {"sex": "Decides which tournaments you can enter."}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email, last_login__isnull=False).exists():
            raise forms.ValidationError(
                "This address is already registered. Please log in instead."
            )
        return email


class CodeForm(forms.Form):
    code = forms.CharField(
        label="Login code",
        max_length=12,
        widget=forms.TextInput(attrs={
            "inputmode": "numeric", "autocomplete": "one-time-code",
            "autofocus": True, "class": "code-input",
        }),
    )
