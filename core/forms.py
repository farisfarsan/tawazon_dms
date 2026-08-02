from django import forms
from .models import Client, ClientContact


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'client_type', 'country', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Bank Muscat'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'contact@company.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+968 XXXXXXXX'}),
            'client_type': forms.Select(attrs={'class': 'form-input'}),
            'country': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Oman'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
        }


class ClientContactForm(forms.ModelForm):
    class Meta:
        model = ClientContact
        fields = ['client', 'name', 'contact_type', 'email', 'phone', 'enabled']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Full name'}),
            'contact_type': forms.Select(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'email@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '+968 XXXXXXXX'}),
            'enabled': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }