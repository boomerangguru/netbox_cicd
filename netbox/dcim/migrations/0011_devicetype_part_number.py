# -*- coding: utf-8 -*-
# Generated by Django 1.9.8 on 2016-07-26 15:05
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dcim', '0010_devicebay_installed_device_set_null'),
    ]

    operations = [
        migrations.AddField(
            model_name='devicetype',
            name='part_number',
            field=models.CharField(blank=True, help_text=b'Discrete part number (optional)', max_length=50),
        ),
    ]
