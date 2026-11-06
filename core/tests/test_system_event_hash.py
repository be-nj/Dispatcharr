from django.test import TestCase

from core.models import SystemEvent
from core.utils import log_system_event

STREAM_HASH = "9dbe9cb24d82d39dc4484d2abcb7041e42a05f2406a8f09b9c4ddd2c11a2b5e3"
CHANNEL_UUID = "2f1b7a54-8c1e-4c8e-9a53-6f0d3a1b2c3d"


class SystemEventChannelIdTests(TestCase):
    def setUp(self):
        SystemEvent.objects.all().delete()

    def test_stream_hash_is_kept_in_details(self):
        log_system_event("client_connect", channel_id=STREAM_HASH, channel_name="ZDF")
        event = SystemEvent.objects.get()
        self.assertIsNone(event.channel_id)
        self.assertEqual(event.details["stream_hash"], STREAM_HASH)

    def test_channel_uuid_stays_in_its_column(self):
        log_system_event("client_connect", channel_id=CHANNEL_UUID, channel_name="ZDF")
        event = SystemEvent.objects.get()
        self.assertEqual(str(event.channel_id), CHANNEL_UUID)
        self.assertNotIn("stream_hash", event.details)
