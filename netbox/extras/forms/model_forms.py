import json

from django import forms
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from core.forms.mixins import SyncedDataMixin
from core.models import ContentType
from dcim.models import DeviceRole, DeviceType, Location, Platform, Region, Site, SiteGroup
from extras.choices import *
from extras.models import *
from extras.utils import FeatureQuery
from netbox.config import get_config, PARAMS
from netbox.forms import NetBoxModelForm
from tenancy.models import Tenant, TenantGroup
from utilities.forms import BootstrapMixin, add_blank_choice, get_field_value
from utilities.forms.fields import (
    CommentField, ContentTypeChoiceField, ContentTypeMultipleChoiceField, DynamicModelChoiceField,
    DynamicModelMultipleChoiceField, JSONField, SlugField,
)
from utilities.forms.widgets import ChoicesWidget, HTMXSelect
from virtualization.models import Cluster, ClusterGroup, ClusterType


__all__ = (
    'BookmarkForm',
    'ConfigContextForm',
    'ConfigRevisionForm',
    'ConfigTemplateForm',
    'CustomFieldChoiceSetForm',
    'CustomFieldForm',
    'CustomLinkForm',
    'EventRuleForm',
    'ExportTemplateForm',
    'ImageAttachmentForm',
    'JournalEntryForm',
    'SavedFilterForm',
    'TagForm',
    'WebhookForm',
)


class CustomFieldForm(BootstrapMixin, forms.ModelForm):
    content_types = ContentTypeMultipleChoiceField(
        label=_('Content types'),
        queryset=ContentType.objects.all(),
        limit_choices_to=FeatureQuery('custom_fields'),
    )
    object_type = ContentTypeChoiceField(
        label=_('Object type'),
        queryset=ContentType.objects.public(),
        required=False,
        help_text=_("Type of the related object (for object/multi-object fields only)")
    )
    choice_set = DynamicModelChoiceField(
        queryset=CustomFieldChoiceSet.objects.all(),
        required=False
    )

    fieldsets = (
        (_('Custom Field'), (
            'content_types', 'name', 'label', 'group_name', 'type', 'object_type', 'required', 'description',
        )),
        (_('Behavior'), ('search_weight', 'filter_logic', 'ui_visibility', 'weight', 'is_cloneable')),
        (_('Values'), ('default', 'choice_set')),
        (_('Validation'), ('validation_minimum', 'validation_maximum', 'validation_regex')),
    )

    class Meta:
        model = CustomField
        fields = '__all__'
        help_texts = {
            'type': _(
                "The type of data stored in this field. For object/multi-object fields, select the related object "
                "type below."
            ),
            'description': _("This will be displayed as help text for the form field. Markdown is supported.")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Disable changing the type of a CustomField as it almost universally causes errors if custom field data
        # is already present.
        if self.instance.pk:
            self.fields['type'].disabled = True


class CustomFieldChoiceSetForm(BootstrapMixin, forms.ModelForm):
    extra_choices = forms.CharField(
        widget=ChoicesWidget(),
        required=False,
        help_text=mark_safe(_(
            'Enter one choice per line. An optional label may be specified for each choice by appending it with a '
            'comma. Example:'
        ) + ' <code>choice1,First Choice</code>')
    )

    class Meta:
        model = CustomFieldChoiceSet
        fields = ('name', 'description', 'base_choices', 'extra_choices', 'order_alphabetically')

    def clean_extra_choices(self):
        data = []
        for line in self.cleaned_data['extra_choices'].splitlines():
            try:
                value, label = line.split(',', maxsplit=1)
            except ValueError:
                value, label = line, line
            data.append((value, label))
        return data


class CustomLinkForm(BootstrapMixin, forms.ModelForm):
    content_types = ContentTypeMultipleChoiceField(
        label=_('Content types'),
        queryset=ContentType.objects.all(),
        limit_choices_to=FeatureQuery('custom_links')
    )

    fieldsets = (
        (_('Custom Link'), ('name', 'content_types', 'weight', 'group_name', 'button_class', 'enabled', 'new_window')),
        (_('Templates'), ('link_text', 'link_url')),
    )

    class Meta:
        model = CustomLink
        fields = '__all__'
        widgets = {
            'link_text': forms.Textarea(attrs={'class': 'font-monospace'}),
            'link_url': forms.Textarea(attrs={'class': 'font-monospace'}),
        }
        help_texts = {
            'link_text': _(
                "Jinja2 template code for the link text. Reference the object as <code>{{ object }}</code>. Links "
                "which render as empty text will not be displayed."
            ),
            'link_url': _("Jinja2 template code for the link URL. Reference the object as <code>{{ object }}</code>."),
        }


class ExportTemplateForm(BootstrapMixin, SyncedDataMixin, forms.ModelForm):
    content_types = ContentTypeMultipleChoiceField(
        label=_('Content types'),
        queryset=ContentType.objects.all(),
        limit_choices_to=FeatureQuery('export_templates')
    )
    template_code = forms.CharField(
        label=_('Template code'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'font-monospace'})
    )

    fieldsets = (
        (_('Export Template'), ('name', 'content_types', 'description', 'template_code')),
        (_('Data Source'), ('data_source', 'data_file', 'auto_sync_enabled')),
        (_('Rendering'), ('mime_type', 'file_extension', 'as_attachment')),
    )

    class Meta:
        model = ExportTemplate
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Disable data field when a DataFile has been set
        if self.instance.data_file:
            self.fields['template_code'].widget.attrs['readonly'] = True
            self.fields['template_code'].help_text = _(
                'Template content is populated from the remote source selected below.'
            )

    def clean(self):
        super().clean()

        if not self.cleaned_data.get('template_code') and not self.cleaned_data.get('data_file'):
            raise forms.ValidationError(_("Must specify either local content or a data file"))

        return self.cleaned_data


class SavedFilterForm(BootstrapMixin, forms.ModelForm):
    slug = SlugField()
    content_types = ContentTypeMultipleChoiceField(
        label=_('Content types'),
        queryset=ContentType.objects.all()
    )
    parameters = JSONField()

    fieldsets = (
        (_('Saved Filter'), ('name', 'slug', 'content_types', 'description', 'weight', 'enabled', 'shared')),
        (_('Parameters'), ('parameters',)),
    )

    class Meta:
        model = SavedFilter
        exclude = ('user',)

    def __init__(self, *args, initial=None, **kwargs):

        # Convert any parameters delivered via initial data to JSON data
        if initial and 'parameters' in initial:
            if type(initial['parameters']) is str:
                initial['parameters'] = json.loads(initial['parameters'])

        super().__init__(*args, initial=initial, **kwargs)


class BookmarkForm(BootstrapMixin, forms.ModelForm):
    object_type = ContentTypeChoiceField(
        label=_('Object type'),
        queryset=ContentType.objects.all(),
        limit_choices_to=FeatureQuery('bookmarks').get_query()
    )

    class Meta:
        model = Bookmark
        fields = ('object_type', 'object_id')


class WebhookForm(NetBoxModelForm):

    fieldsets = (
        (_('Webhook'), ('name', 'tags',)),
        (_('HTTP Request'), (
            'payload_url', 'http_method', 'http_content_type', 'additional_headers', 'body_template', 'secret',
        )),
        (_('SSL'), ('ssl_verification', 'ca_file_path')),
    )

    class Meta:
        model = Webhook
        fields = '__all__'
        widgets = {
            'additional_headers': forms.Textarea(attrs={'class': 'font-monospace'}),
            'body_template': forms.Textarea(attrs={'class': 'font-monospace'}),
        }


class EventRuleForm(NetBoxModelForm):
    content_types = ContentTypeMultipleChoiceField(
        label=_('Content types'),
        queryset=ContentType.objects.all(),
        limit_choices_to=FeatureQuery('webhooks')
    )
    action_choice = forms.ChoiceField(
        label=_('Action choice'),
        choices=[]
    )

    fieldsets = (
        (_('EventRule'), ('name', 'content_types', 'enabled', 'tags')),
        (_('Events'), ('type_create', 'type_update', 'type_delete', 'type_job_start', 'type_job_end')),
        (_('Conditions'), ('conditions',)),
        (_('Action'), ('action_type', 'action_choice', 'parameters', 'action_object_type', 'action_object_id', 'action_object_identifier')),
    )

    class Meta:
        model = EventRule
        fields = '__all__'
        labels = {
            'type_create': _('Creations'),
            'type_update': _('Updates'),
            'type_delete': _('Deletions'),
            'type_job_start': _('Job executions'),
            'type_job_end': _('Job terminations'),
        }
        widgets = {
            'conditions': forms.Textarea(attrs={'class': 'font-monospace'}),
            'action_type': HTMXSelect(),
            'action_object_type': forms.HiddenInput,
            'action_object_id': forms.HiddenInput,
            'action_object_identifier': forms.HiddenInput,
        }

    def get_script_choices(self):
        choices = []
        idx = 0
        for module in ScriptModule.objects.all():
            scripts = []
            for script_name in module.scripts.keys():
                name = f"{str(module.pk)}:{script_name.lower()}"
                scripts.append((name, script_name))

            if scripts:
                choices.append((str(module), scripts))

        self.fields['action_choice'].choices = choices
        self.fields['action_choice'].initial = get_field_value(self, 'action_object_identifier')

    def get_webhook_choices(self):
        initial = None
        if self.fields['action_object_type'] and get_field_value(self, 'action_object_id'):
            initial = Webhook.objects.get(pk=get_field_value(self, 'action_object_id'))
        self.fields['action_choice'] = DynamicModelChoiceField(
            label=_('Webhook'),
            queryset=Webhook.objects.all(),
            required=True,
            initial=initial
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['action_object_type'].required = False
        self.fields['action_object_id'].required = False

        # Determine the action type
        action_type = get_field_value(self, 'action_type')

        if action_type == EventRuleActionChoices.WEBHOOK:
            self.get_webhook_choices()
        elif action_type == EventRuleActionChoices.SCRIPT:
            self.get_script_choices()

    def clean(self):
        super().clean()

        action_choice = self.cleaned_data.get('action_choice')
        if self.cleaned_data.get('action_type') == EventRuleActionChoices.WEBHOOK:
            self.cleaned_data['action_object_type'] = ContentType.objects.get_for_model(action_choice)
            self.cleaned_data['action_object_id'] = action_choice.id
            self.cleaned_data['action_object_identifier'] = ''
        elif self.cleaned_data.get('action_type') == EventRuleActionChoices.SCRIPT:
            script = ScriptModule.objects.get(pk=action_choice.split(":")[0])
            self.cleaned_data['action_object_type'] = ContentType.objects.get_for_model(script)
            self.cleaned_data['action_object_id'] = script.id
            self.cleaned_data['action_object_identifier'] = action_choice

        return self.cleaned_data


class TagForm(BootstrapMixin, forms.ModelForm):
    slug = SlugField()
    object_types = ContentTypeMultipleChoiceField(
        label=_('Object types'),
        queryset=ContentType.objects.all(),
        limit_choices_to=FeatureQuery('tags'),
        required=False
    )

    fieldsets = (
        ('Tag', ('name', 'slug', 'color', 'description', 'object_types')),
    )

    class Meta:
        model = Tag
        fields = [
            'name', 'slug', 'color', 'description', 'object_types',
        ]


class ConfigContextForm(BootstrapMixin, SyncedDataMixin, forms.ModelForm):
    regions = DynamicModelMultipleChoiceField(
        label=_('Regions'),
        queryset=Region.objects.all(),
        required=False
    )
    site_groups = DynamicModelMultipleChoiceField(
        label=_('Site groups'),
        queryset=SiteGroup.objects.all(),
        required=False
    )
    sites = DynamicModelMultipleChoiceField(
        label=_('Sites'),
        queryset=Site.objects.all(),
        required=False
    )
    locations = DynamicModelMultipleChoiceField(
        label=_('Locations'),
        queryset=Location.objects.all(),
        required=False
    )
    device_types = DynamicModelMultipleChoiceField(
        label=_('Device types'),
        queryset=DeviceType.objects.all(),
        required=False
    )
    roles = DynamicModelMultipleChoiceField(
        label=_('Roles'),
        queryset=DeviceRole.objects.all(),
        required=False
    )
    platforms = DynamicModelMultipleChoiceField(
        label=_('Platforms'),
        queryset=Platform.objects.all(),
        required=False
    )
    cluster_types = DynamicModelMultipleChoiceField(
        label=_('Cluster types'),
        queryset=ClusterType.objects.all(),
        required=False
    )
    cluster_groups = DynamicModelMultipleChoiceField(
        label=_('Cluster groups'),
        queryset=ClusterGroup.objects.all(),
        required=False
    )
    clusters = DynamicModelMultipleChoiceField(
        label=_('Clusters'),
        queryset=Cluster.objects.all(),
        required=False
    )
    tenant_groups = DynamicModelMultipleChoiceField(
        label=_('Tenant groups'),
        queryset=TenantGroup.objects.all(),
        required=False
    )
    tenants = DynamicModelMultipleChoiceField(
        label=_('Tenants'),
        queryset=Tenant.objects.all(),
        required=False
    )
    tags = DynamicModelMultipleChoiceField(
        label=_('Tags'),
        queryset=Tag.objects.all(),
        required=False
    )
    data = JSONField(
        label=_('Data'),
        required=False
    )

    fieldsets = (
        (_('Config Context'), ('name', 'weight', 'description', 'data', 'is_active')),
        (_('Data Source'), ('data_source', 'data_file', 'auto_sync_enabled')),
        (_('Assignment'), (
            'regions', 'site_groups', 'sites', 'locations', 'device_types', 'roles', 'platforms', 'cluster_types',
            'cluster_groups', 'clusters', 'tenant_groups', 'tenants', 'tags',
        )),
    )

    class Meta:
        model = ConfigContext
        fields = (
            'name', 'weight', 'description', 'data', 'is_active', 'regions', 'site_groups', 'sites', 'locations',
            'roles', 'device_types', 'platforms', 'cluster_types', 'cluster_groups', 'clusters', 'tenant_groups',
            'tenants', 'tags', 'data_source', 'data_file', 'auto_sync_enabled',
        )

    def __init__(self, *args, initial=None, **kwargs):

        # Convert data delivered via initial data to JSON data
        if initial and 'data' in initial:
            if type(initial['data']) is str:
                initial['data'] = json.loads(initial['data'])

        super().__init__(*args, initial=initial, **kwargs)

        # Disable data field when a DataFile has been set
        if self.instance.data_file:
            self.fields['data'].widget.attrs['readonly'] = True
            self.fields['data'].help_text = _('Data is populated from the remote source selected below.')

    def clean(self):
        super().clean()

        if not self.cleaned_data.get('data') and not self.cleaned_data.get('data_file'):
            raise forms.ValidationError(_("Must specify either local data or a data file"))

        return self.cleaned_data


class ConfigTemplateForm(BootstrapMixin, SyncedDataMixin, forms.ModelForm):
    tags = DynamicModelMultipleChoiceField(
        label=_('Tags'),
        queryset=Tag.objects.all(),
        required=False
    )
    template_code = forms.CharField(
        label=_('Template code'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'font-monospace'})
    )

    fieldsets = (
        (_('Config Template'), ('name', 'description', 'environment_params', 'tags')),
        (_('Content'), ('template_code',)),
        (_('Data Source'), ('data_source', 'data_file', 'auto_sync_enabled')),
    )

    class Meta:
        model = ConfigTemplate
        fields = '__all__'
        widgets = {
            'environment_params': forms.Textarea(attrs={'rows': 5})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Disable content field when a DataFile has been set
        if self.instance.data_file:
            self.fields['template_code'].widget.attrs['readonly'] = True
            self.fields['template_code'].help_text = _(
                'Template content is populated from the remote source selected below.'
            )

    def clean(self):
        super().clean()

        if not self.cleaned_data.get('template_code') and not self.cleaned_data.get('data_file'):
            raise forms.ValidationError(_("Must specify either local content or a data file"))

        return self.cleaned_data


class ImageAttachmentForm(BootstrapMixin, forms.ModelForm):

    class Meta:
        model = ImageAttachment
        fields = [
            'name', 'image',
        ]


class JournalEntryForm(NetBoxModelForm):
    kind = forms.ChoiceField(
        label=_('Kind'),
        choices=add_blank_choice(JournalEntryKindChoices),
        required=False
    )
    comments = CommentField()

    class Meta:
        model = JournalEntry
        fields = ['assigned_object_type', 'assigned_object_id', 'kind', 'tags', 'comments']
        widgets = {
            'assigned_object_type': forms.HiddenInput,
            'assigned_object_id': forms.HiddenInput,
        }


EMPTY_VALUES = ('', None, [], ())


class ConfigFormMetaclass(forms.models.ModelFormMetaclass):

    def __new__(mcs, name, bases, attrs):

        # Emulate a declared field for each supported configuration parameter
        param_fields = {}
        for param in PARAMS:
            field_kwargs = {
                'required': False,
                'label': param.label,
                'help_text': param.description,
            }
            field_kwargs.update(**param.field_kwargs)
            param_fields[param.name] = param.field(**field_kwargs)
        attrs.update(param_fields)

        return super().__new__(mcs, name, bases, attrs)


class ConfigRevisionForm(BootstrapMixin, forms.ModelForm, metaclass=ConfigFormMetaclass):
    """
    Form for creating a new ConfigRevision.
    """

    fieldsets = (
        (_('Rack Elevations'), ('RACK_ELEVATION_DEFAULT_UNIT_HEIGHT', 'RACK_ELEVATION_DEFAULT_UNIT_WIDTH')),
        (_('Power'), ('POWERFEED_DEFAULT_VOLTAGE', 'POWERFEED_DEFAULT_AMPERAGE', 'POWERFEED_DEFAULT_MAX_UTILIZATION')),
        (_('IPAM'), ('ENFORCE_GLOBAL_UNIQUE', 'PREFER_IPV4')),
        (_('Security'), ('ALLOWED_URL_SCHEMES',)),
        (_('Banners'), ('BANNER_LOGIN', 'BANNER_MAINTENANCE', 'BANNER_TOP', 'BANNER_BOTTOM')),
        (_('Pagination'), ('PAGINATE_COUNT', 'MAX_PAGE_SIZE')),
        (_('Validation'), ('CUSTOM_VALIDATORS', 'PROTECTION_RULES')),
        (_('User Preferences'), ('DEFAULT_USER_PREFERENCES',)),
        (_('Miscellaneous'), (
            'MAINTENANCE_MODE', 'GRAPHQL_ENABLED', 'CHANGELOG_RETENTION', 'JOB_RETENTION', 'MAPS_URL',
        )),
        (_('Config Revision'), ('comment',))
    )

    class Meta:
        model = ConfigRevision
        fields = '__all__'
        widgets = {
            'BANNER_LOGIN': forms.Textarea(attrs={'class': 'font-monospace'}),
            'BANNER_MAINTENANCE': forms.Textarea(attrs={'class': 'font-monospace'}),
            'BANNER_TOP': forms.Textarea(attrs={'class': 'font-monospace'}),
            'BANNER_BOTTOM': forms.Textarea(attrs={'class': 'font-monospace'}),
            'CUSTOM_VALIDATORS': forms.Textarea(attrs={'class': 'font-monospace'}),
            'PROTECTION_RULES': forms.Textarea(attrs={'class': 'font-monospace'}),
            'comment': forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Append current parameter values to form field help texts and check for static configurations
        config = get_config()
        for param in PARAMS:
            value = getattr(config, param.name)

            # Set the field's initial value, if it can be serialized. (This may not be the case e.g. for
            # CUSTOM_VALIDATORS, which may reference Python objects.)
            try:
                json.dumps(value)
                if type(value) in (tuple, list):
                    self.fields[param.name].initial = ', '.join(value)
                else:
                    self.fields[param.name].initial = value
            except TypeError:
                pass

            # Check whether this parameter is statically configured (e.g. in configuration.py)
            if hasattr(settings, param.name):
                self.fields[param.name].disabled = True
                self.fields[param.name].help_text = _(
                    'This parameter has been defined statically and cannot be modified.'
                )
                continue

            # Set the field's help text
            help_text = self.fields[param.name].help_text
            if help_text:
                help_text += '<br />'  # Line break
            help_text += _('Current value: <strong>{value}</strong>').format(value=value or '&mdash;')
            if value == param.default:
                help_text += _(' (default)')
            self.fields[param.name].help_text = help_text

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Populate JSON data on the instance
        instance.data = self.render_json()

        if commit:
            instance.save()

        return instance

    def render_json(self):
        json = {}

        # Iterate through each field and populate non-empty values
        for field_name in self.declared_fields:
            if field_name in self.cleaned_data and self.cleaned_data[field_name] not in EMPTY_VALUES:
                json[field_name] = self.cleaned_data[field_name]

        return json
