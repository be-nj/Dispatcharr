"""A stream played by channel uuid and by its hash shares one upstream session."""

import fnmatch
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.proxy.live_proxy.views import _live_session_for_stream, _shared_session_id

CHANNEL_UUID = "5c80bb7b-e932-49e9-a406-338ad53e3b9e"
STREAM_HASH = "efa4cf31bc31c268d2bdf0e9e2ec275322b1b6a5959ef00552669cb2cb6ff1df"


class FakeRedis:
    def __init__(self, sessions):
        self.hashes = {
            f"live:channel:{session_id}:metadata".encode(): {
                k.encode(): v.encode() for k, v in fields.items()
            }
            for session_id, fields in sessions.items()
        }

    def scan_iter(self, match, count=None):
        return [k for k in self.hashes if fnmatch.fnmatch(k.decode(), match)]

    def hgetall(self, key):
        key = key.encode() if isinstance(key, str) else key
        return self.hashes.get(key, {})


def _stream(stream_id=10344):
    stream = MagicMock()
    stream.id = stream_id
    stream.get_stream_profile.return_value.is_redirect.return_value = False
    return stream


class LiveSessionForStreamTests(SimpleTestCase):
    def test_finds_channel_session_playing_the_stream(self):
        redis = FakeRedis({CHANNEL_UUID: {"state": "active", "stream_id": "10344"}})
        self.assertEqual(
            _live_session_for_stream(redis, 10344, STREAM_HASH), CHANNEL_UUID
        )

    def test_ignores_other_streams_and_dead_sessions(self):
        redis = FakeRedis(
            {
                CHANNEL_UUID: {"state": "active", "stream_id": "10343"},
                "other": {"state": "stopping", "stream_id": "10344"},
                "errored": {"state": "error", "stream_id": "10344"},
            }
        )
        self.assertIsNone(_live_session_for_stream(redis, 10344, STREAM_HASH))

    def test_never_returns_the_requested_session(self):
        redis = FakeRedis({STREAM_HASH: {"state": "active", "stream_id": "10344"}})
        self.assertIsNone(_live_session_for_stream(redis, 10344, STREAM_HASH))


class SharedSessionIdTests(SimpleTestCase):
    def _proxy(self, sessions):
        proxy_server = MagicMock()
        proxy_server.redis_client = FakeRedis(sessions)
        return proxy_server

    def test_hash_request_joins_live_channel(self):
        proxy = self._proxy({CHANNEL_UUID: {"state": "active", "stream_id": "10344"}})
        self.assertEqual(
            _shared_session_id(proxy, STREAM_HASH, _stream()), CHANNEL_UUID
        )

    def test_live_request_keeps_its_own_session(self):
        proxy = self._proxy(
            {
                CHANNEL_UUID: {"state": "active", "stream_id": "10344"},
                STREAM_HASH: {"state": "active", "stream_id": "10344"},
            }
        )
        self.assertIsNone(_shared_session_id(proxy, STREAM_HASH, _stream()))

    def test_redirect_profiles_never_share(self):
        proxy = self._proxy({CHANNEL_UUID: {"state": "active", "stream_id": "10344"}})
        stream = _stream()
        stream.get_stream_profile.return_value.is_redirect.return_value = True
        self.assertIsNone(_shared_session_id(proxy, STREAM_HASH, stream))

    def test_channel_request_joins_live_hash_session_of_its_first_stream(self):
        from apps.channels.models import Channel

        proxy = self._proxy({STREAM_HASH: {"state": "active", "stream_id": "10344"}})
        channel = MagicMock(spec=Channel)
        channel.get_stream_profile.return_value.is_redirect.return_value = False
        channel.streams.order_by.return_value.values_list.return_value.first.return_value = 10344
        self.assertEqual(
            _shared_session_id(proxy, CHANNEL_UUID, channel), STREAM_HASH
        )
