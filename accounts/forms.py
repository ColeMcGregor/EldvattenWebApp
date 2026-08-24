from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = (
            "username",
            "display_name",
            "email",
        )
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "autocomplete": "username",
                }
            ),
            "display_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "autocomplete": "name",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "autocomplete": "email",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].required = True

        self.fields["password1"].widget.attrs.update(
            {
                "class": "form-input",
                "autocomplete": "new-password",
            }
        )

        self.fields["password2"].widget.attrs.update(
            {
                "class": "form-input",
                "autocomplete": "new-password",
            }
        )


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "autocomplete": "username",
            }
        )
    )

    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-input",
                "autocomplete": "current-password",
            }
        ),
    )