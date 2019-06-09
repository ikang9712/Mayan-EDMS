from __future__ import unicode_literals

import os

from django import forms
from django.conf import settings
from django.contrib.admin.utils import label_for_field
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models
from django.utils.module_loading import import_string
from django.utils.translation import ugettext_lazy as _

from mayan.apps.acls.models import AccessControlList

from .models import UserLocaleProfile
from .utils import introspect_attribute, resolve_attribute
from .widgets import DisableableSelectWidget, PlainWidget, TextAreaDiv


class ChoiceForm(forms.Form):
    """
    Form to be used in side by side templates used to add or remove
    items from a many to many field
    """
    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', [])
        label = kwargs.pop('label', _('Selection'))
        help_text = kwargs.pop('help_text', None)
        disabled_choices = kwargs.pop('disabled_choices', ())
        super(ChoiceForm, self).__init__(*args, **kwargs)
        self.fields['selection'].choices = choices
        self.fields['selection'].label = label
        self.fields['selection'].help_text = help_text
        self.fields['selection'].widget.disabled_choices = disabled_choices
        self.fields['selection'].widget.attrs.update(
            {
                'class': 'full-height', 'data-height-difference': '450'
            }
        )

    selection = forms.MultipleChoiceField(
        required=False, widget=DisableableSelectWidget()
    )


class FormOptions(object):
    def __init__(self, form, kwargs, options=None):
        """
        Option definitions will be iterated. The option value will be
        determined in the following order: as passed via keyword
        arguments during form intialization, as form get_... method or
        finally as static Meta options. This is to allow a form with
        Meta options or method to be overrided at initialization
        and increase the usability of a single class.
        """
        for name, default_value in self.option_definitions.items():
            try:
                # Check for a runtime value via kwargs
                value = kwargs.pop(name)
            except KeyError:
                try:
                    # Check if there is a get_... method
                    value = getattr(self, 'get_{}'.format(name))()
                except AttributeError:
                    try:
                        # Check the meta class options
                        value = getattr(options, name)
                    except AttributeError:
                        value = default_value

            setattr(self, name, value)


class DetailFormOption(FormOptions):
    # Dictionary list of option names and default values
    option_definitions = {'extra_fields': []}


class DetailForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.opts = DetailFormOption(
            form=self, kwargs=kwargs, options=getattr(self, 'Meta', None)
        )
        super(DetailForm, self).__init__(*args, **kwargs)

        for extra_field in self.opts.extra_fields:
            obj = extra_field.get('object', self.instance)
            field = extra_field['field']

            result = resolve_attribute(
                attribute=field, obj=obj
            )

            label = extra_field.get('label', None)

            # If label is not specified try to get it from the object itself
            if not label:
                attribute_name, obj = introspect_attribute(
                    attribute_name=field, obj=obj
                )

                if not obj:
                    label = _('None')
                else:
                    try:
                        label = getattr(
                            getattr(obj, attribute_name), 'short_description'
                        )
                    except AttributeError:
                        label = label_for_field(
                            name=attribute_name, model=obj
                        )

            help_text = extra_field.get('help_text', None)
            # If help_text is not specified try to get it from the object itself
            if not help_text:
                if obj:
                    try:
                        field_object = obj._meta.get_field(field_name=field)
                    except FieldDoesNotExist:
                        field_object = field

                    help_text = getattr(
                        field_object, 'help_text', None
                    )

            # TODO: Add others result types <=> Field types
            if isinstance(result, models.query.QuerySet):
                self.fields[field] = forms.ModelMultipleChoiceField(
                    queryset=result, label=label
                )
            else:
                self.fields[field] = forms.CharField(
                    initial=resolve_attribute(
                        obj=obj,
                        attribute=field
                    ), label=label, help_text=help_text,
                    widget=extra_field.get('widget', PlainWidget)
                )

        for field_name, field in self.fields.items():
            self.fields[field_name].widget.attrs.update(
                {'readonly': 'readonly'}
            )


class DynamicFormMixin(object):
    def __init__(self, *args, **kwargs):
        self.schema = kwargs.pop('schema')
        super(DynamicFormMixin, self).__init__(*args, **kwargs)

        widgets = self.schema.get('widgets', {})
        field_order = self.schema.get(
            'field_order', self.schema['fields'].keys()
        )

        for field_name in field_order:
            field_data = self.schema['fields'][field_name]
            field_class = import_string(field_data['class'])
            kwargs = {
                'label': field_data['label'],
                'required': field_data.get('required', True),
                'initial': field_data.get('default', None),
                'help_text': field_data.get('help_text'),
            }
            if widgets and field_name in widgets:
                widget = widgets[field_name]
                kwargs['widget'] = import_string(
                    widget['class']
                )(**widget.get('kwargs', {}))

            kwargs.update(field_data.get('kwargs', {}))
            self.fields[field_name] = field_class(**kwargs)


    @property
    def media(self):
        return forms.Media(**self.schema.get('media', {}))


class DynamicForm(DynamicFormMixin, forms.Form):
    pass


class DynamicModelForm(DynamicFormMixin, forms.ModelForm):
    pass


class FileDisplayForm(forms.Form):
    DIRECTORY = None
    FILENAME = None

    text = forms.CharField(
        label='',
        widget=TextAreaDiv(
            attrs={'class': 'full-height scrollable', 'data-height-difference': 270}
        )
    )

    def __init__(self, *args, **kwargs):
        super(FileDisplayForm, self).__init__(*args, **kwargs)
        if self.DIRECTORY or self.FILENAME:
            file_path = os.path.join(
                settings.BASE_DIR, os.sep.join(self.DIRECTORY), self.FILENAME
            )
            with open(file_path) as file_object:
                self.fields['text'].initial = file_object.read()


class FilteredSelectionFormOptions(FormOptions):
    # Dictionary list of option names and default values
    option_definitions = {
        'allow_multiple': False,
        'field_name': None,
        'help_text': None,
        'label': None,
        'model': None,
        'permission': None,
        'queryset': None,
        'required': True,
        'user': None,
        'widget_class': None,
        'widget_attributes': {'size': '10'},
    }


class FilteredSelectionForm(forms.Form):
    """
    Form to select the from a list of choice filtered by access. Can be
    configure to allow single or multiple selection.
    """
    def __init__(self, *args, **kwargs):
        opts = FilteredSelectionFormOptions(
            form=self, kwargs=kwargs, options=getattr(self, 'Meta', None)
        )

        if opts.queryset is None:
            if not opts.model:
                raise ImproperlyConfigured(
                    '{} requires a queryset or a model to be specified as '
                    'a meta option or passed during initialization.'.format(
                        self.__class__.__name__
                    )
                )

            queryset = opts.model.objects.all()
        else:
            queryset = opts.queryset

        if opts.allow_multiple:
            extra_kwargs = {}
            field_class = forms.ModelMultipleChoiceField
            widget_class = forms.widgets.SelectMultiple
        else:
            extra_kwargs = {'empty_label': None}
            field_class = forms.ModelChoiceField
            widget_class = forms.widgets.Select

        if opts.widget_class:
            widget_class = opts.widget_class

        if opts.permission:
            queryset = AccessControlList.objects.restrict_queryset(
                permission=opts.permission, queryset=queryset,
                user=opts.user
            )

        super(FilteredSelectionForm, self).__init__(*args, **kwargs)

        self.fields[opts.field_name] = field_class(
            help_text=opts.help_text, label=opts.label,
            queryset=queryset, required=opts.required,
            widget=widget_class(attrs=opts.widget_attributes),
            **extra_kwargs
        )


class LicenseForm(FileDisplayForm):
    DIRECTORY = ()
    FILENAME = 'LICENSE'


class LocaleProfileForm(forms.ModelForm):
    class Meta:
        fields = ('language', 'timezone')
        model = UserLocaleProfile
        widgets = {
            'language': forms.Select(
                attrs={
                    'class': 'select2'
                }
            ),
            'timezone': forms.Select(
                attrs={
                    'class': 'select2'
                }
            )
        }


class LocaleProfileForm_view(DetailForm):
    class Meta:
        fields = ('language', 'timezone')
        model = UserLocaleProfile
