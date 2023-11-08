# Generated by Django 4.2.5 on 2023-10-31 14:37

from django.contrib.contenttypes.models import ContentType
from django.db import migrations, models
import django.db.models.deletion
from extras.choices import *
import extras.utils
import taggit.managers
import utilities.json


def move_webhooks(apps, schema_editor):
    Webhook = apps.get_model("extras", "Webhook")
    EventRule = apps.get_model("extras", "EventRule")

    for webhook in Webhook.objects.all():
        event = EventRule()

        event.name = webhook.name
        event.type_create = webhook.type_create
        event.type_update = webhook.type_update
        event.type_delete = webhook.type_delete
        event.type_job_start = webhook.type_job_start
        event.type_job_end = webhook.type_job_end
        event.enabled = webhook.enabled
        event.conditions = webhook.conditions

        event.action_type = EventRuleActionChoices.WEBHOOK
        event.object_type_id = ContentType.objects.get_for_model(webhook).id
        event.object_id = webhook.id
        event.save()
        event.content_types.add(*webhook.content_types.all())


class Migration(migrations.Migration):
    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('extras', '0098_webhook_custom_field_data_webhook_tags'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                (
                    'custom_field_data',
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                ('name', models.CharField(max_length=150, unique=True)),
                ('type_create', models.BooleanField(default=False)),
                ('type_update', models.BooleanField(default=False)),
                ('type_delete', models.BooleanField(default=False)),
                ('type_job_start', models.BooleanField(default=False)),
                ('type_job_end', models.BooleanField(default=False)),
                ('enabled', models.BooleanField(default=True)),
                ('conditions', models.JSONField(blank=True, null=True)),
                ('action_type', models.CharField(default='webhook', max_length=30)),
                ('object_id', models.PositiveBigIntegerField(blank=True, null=True)),
                (
                    'content_types',
                    models.ManyToManyField(
                        limit_choices_to=extras.utils.FeatureQuery('eventrules'),
                        related_name='eventrules',
                        to='contenttypes.contenttype',
                    ),
                ),
                (
                    'object_type',
                    models.ForeignKey(
                        limit_choices_to=models.Q(('app_label', 'extras'), ('model__in', ('webhook', 'script'))),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='eventrule_actions',
                        to='contenttypes.contenttype',
                    ),
                ),
                ('object_identifier', models.CharField(max_length=80, blank=True)),
                ('parameters', models.JSONField(blank=True, null=True)),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'eventrule',
                'verbose_name_plural': 'eventrules',
                'ordering': ('name',),
            },
        ),
        migrations.RunPython(move_webhooks),
        migrations.RemoveConstraint(
            model_name='webhook',
            name='extras_webhook_unique_payload_url_types',
        ),
        migrations.RemoveField(
            model_name='webhook',
            name='conditions',
        ),
        migrations.RemoveField(
            model_name='webhook',
            name='content_types',
        ),
        migrations.RemoveField(
            model_name='webhook',
            name='enabled',
        ),
        migrations.RemoveField(
            model_name='webhook',
            name='type_create',
        ),
        migrations.RemoveField(
            model_name='webhook',
            name='type_delete',
        ),
        migrations.RemoveField(
            model_name='webhook',
            name='type_job_end',
        ),
        migrations.RemoveField(
            model_name='webhook',
            name='type_job_start',
        ),
        migrations.RemoveField(
            model_name='webhook',
            name='type_update',
        ),
        migrations.AlterField(
            model_name='eventrule',
            name='object_type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='eventrule_actions',
                to='contenttypes.contenttype',
            ),
        ),
    ]
