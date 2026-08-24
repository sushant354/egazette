"""Forms for the site: search, and the two account forms.

The search form is a GET form so that a result page is a shareable,
bookmarkable URL. All its fields are optional; an empty form browses the whole
archive newest first.

The account forms are Django's own, restyled: an account here only exists so a
reader can keep bookmarks, so signup asks for a username, an address to reach
them at and a password, and the validation stays Django's.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from gazettes.models import Source
from gazettes.services.search import ORDER_CHOICES, SearchCriteria

DATE_INPUT_FORMATS = ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y']


class SearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Search the archive',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Search gazette text, subjects, ministries…',
            'autocomplete': 'off',
            'spellcheck': 'false',
        }),
    )
    source = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select'}),
    )
    from_date = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    to_date = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    year = forms.IntegerField(
        required=False, min_value=1600, max_value=2200,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    order = forms.ChoiceField(
        required=False,
        choices=[('', 'Relevance')] + ORDER_CHOICES[1:],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only offer sources that actually hold gazettes, so the filter never
        # leads to a guaranteed-empty result page.
        self.fields['source'].choices = [
            (name, title)
            for name, title in Source.objects.filter(gazette_count__gt=0)
            .order_by('title')
            .values_list('name', 'title')
        ]

    def clean(self):
        cleaned = super().clean()
        from_date = cleaned.get('from_date')
        to_date = cleaned.get('to_date')
        if from_date and to_date and from_date > to_date:
            # Swap rather than reject: the reader's intent is obvious and an
            # error page here would be pure friction.
            cleaned['from_date'], cleaned['to_date'] = to_date, from_date
        return cleaned

    def criteria(self):
        """The SearchCriteria this form describes."""
        if not self.is_valid():
            return SearchCriteria()
        data = self.cleaned_data
        return SearchCriteria(
            q=(data.get('q') or '').strip(),
            sources=data.get('source') or [],
            from_date=data.get('from_date'),
            to_date=data.get('to_date'),
            year=data.get('year'),
            order=data.get('order') or '',
        )


class LoginForm(AuthenticationForm):
    """Django's login form, wearing the site's input styling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'username',
            'autofocus': True,
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'autocomplete': 'current-password',
        })


class SignupForm(UserCreationForm):
    """Username, email and the password pair.

    Django's User model leaves email blank-able and unconstrained; here it is
    required and unique, because it is the only way back into an account whose
    password has been forgotten.
    """

    email = forms.EmailField(
        required=True,
        label='Email',
        help_text='Used to reach you about your account, and nothing else.',
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
        self.fields['username'].widget.attrs.update({
            'autocomplete': 'username',
            'autofocus': True,
        })
        self.fields['password1'].widget.attrs['autocomplete'] = 'new-password'
        self.fields['password2'].widget.attrs['autocomplete'] = 'new-password'

    def clean_email(self):
        """One account per address.

        Compared case-insensitively: addresses are not case-sensitive in
        practice, and two accounts differing only in case would make a
        password reset ambiguous.
        """
        email = (self.cleaned_data.get('email') or '').strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'An account with this email address already exists.'
            )
        return email
