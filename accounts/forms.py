
from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import Group

from .models import AccountStatus, User
from .services import get_allowed_account_statuses


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


class AccountSettingsForm(forms.ModelForm):
    class Meta:
        model = User

        fields = (
            "display_name",
        )

        widgets = {
            "display_name": forms.TextInput(
                attrs={
                    "class": "form-input",
                    "autocomplete": "name",
                }
            ),
        }


class UserPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["old_password"].widget.attrs.update(
            {
                "class": "form-input",
                "autocomplete": "current-password",
            }
        )

        self.fields["new_password1"].widget.attrs.update(
            {
                "class": "form-input",
                "autocomplete": "new-password",
            }
        )

        self.fields["new_password2"].widget.attrs.update(
            {
                "class": "form-input",
                "autocomplete": "new-password",
            }
        )


class AccountStatusForm(forms.ModelForm):
    class Meta:
        model = User

        fields = (
            "account_status",
        )

        widgets = {
            "account_status": forms.Select(
                attrs={
                    "class": "form-input",
                }
            ),
        }

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)

        allowed_statuses = get_allowed_account_statuses(
            actor=actor,
            account=self.instance,
        )

        self.fields["account_status"].choices = [
            (status, AccountStatus(status).label)
            for status in allowed_statuses
        ]


class AccountActivationForm(forms.ModelForm):
    class Meta:
        model = User

        fields = (
            "is_active",
        )

        widgets = {
            "is_active": forms.CheckboxInput(),
        }


class AccountGroupForm(forms.Form):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-input",
                "size": "8",
            }
        ),
    )

    def __init__(
        self,
        *args,
        instance=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.fields["groups"].queryset = (
            Group.objects.order_by("name")
        )

        if instance is not None:
            self.initial["groups"] = list(
                instance.groups.values_list(
                    "pk",
                    flat=True,
                )
            )
