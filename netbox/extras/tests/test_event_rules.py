import json
import uuid
from unittest.mock import patch

import django_rq
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.urls import reverse
from requests import Session
from rest_framework import status

from dcim.choices import SiteStatusChoices
from dcim.models import Site
from extras.choices import ObjectChangeActionChoices
from extras.models import Tag, EventRule, Webhook
from extras.events import enqueue_object, flush_events, serialize_for_event
from extras.events_worker import eval_conditions
from extras.webhooks import generate_signature
from extras.webhooks_worker import process_webhook
from utilities.testing import APITestCase


class EventRuleTest(APITestCase):

    def setUp(self):
        super().setUp()

        # Ensure the queue has been cleared for each test
        self.queue = django_rq.get_queue('default')
        self.queue.empty()

    @classmethod
    def setUpTestData(cls):

        site_ct = ContentType.objects.get_for_model(Site)
        DUMMY_URL = 'http://localhost:9000/'
        DUMMY_SECRET = 'LOOKATMEIMASECRETSTRING'

        webhooks = Webhook.objects.bulk_create((
            Webhook(name='Webhook 1',),
            Webhook(name='Webhook 2',),
            Webhook(name='Webhook 3',),
        ))

        Tag.objects.bulk_create((
            Tag(name='Foo', slug='foo'),
            Tag(name='Bar', slug='bar'),
            Tag(name='Baz', slug='baz'),
        ))
