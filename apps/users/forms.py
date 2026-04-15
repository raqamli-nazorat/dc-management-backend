from django import forms
from unfold.widgets import UnfoldAdminSelectMultipleWidget

from .models import User, Role


class UserAdminForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(
        choices=Role.choices,
        widget=UnfoldAdminSelectMultipleWidget(),
        label="Rollari",
        required=True
    )

    class Meta:
        model = User
        fields = '__all__'
