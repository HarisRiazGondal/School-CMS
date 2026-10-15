from django import forms


class PrivateAttachmentForm(forms.Form):
    file = forms.FileField()
