"""The search form.

A GET form so that a result page is a shareable, bookmarkable URL. All fields
are optional; an empty form browses the whole archive newest first.
"""

from django import forms

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
