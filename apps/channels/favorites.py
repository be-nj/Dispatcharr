"""Per-user channel favorites.

Kept in a dedicated module so the fork stays easy to rebase; the model lives
in apps.channels.models (ChannelFavorite).
"""

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import Authenticated

from .models import Channel, ChannelFavorite


class FavoritesAPIView(APIView):
    """GET returns the current user's favorite channel ids; PUT replaces the
    whole set; POST /<id>/ and DELETE /<id>/ toggle a single channel."""

    permission_classes = [Authenticated]

    def get(self, request):
        ids = ChannelFavorite.objects.filter(user=request.user).values_list(
            "channel_id", flat=True
        )
        return Response({"channels": list(ids)})

    def put(self, request):
        ids = request.data.get("channels", [])
        if not isinstance(ids, list):
            return Response({"error": "channels must be a list"}, status=400)
        valid = set(
            Channel.objects.filter(id__in=ids).values_list("id", flat=True)
        )
        ChannelFavorite.objects.filter(user=request.user).exclude(
            channel_id__in=valid
        ).delete()
        existing = set(
            ChannelFavorite.objects.filter(user=request.user).values_list(
                "channel_id", flat=True
            )
        )
        ChannelFavorite.objects.bulk_create(
            [
                ChannelFavorite(user=request.user, channel_id=cid)
                for cid in valid - existing
            ]
        )
        return self.get(request)


class FavoriteToggleAPIView(APIView):
    permission_classes = [Authenticated]

    def post(self, request, channel_id):
        if not Channel.objects.filter(id=channel_id).exists():
            return Response({"error": "unknown channel"}, status=404)
        ChannelFavorite.objects.get_or_create(
            user=request.user, channel_id=channel_id
        )
        return Response({"favorite": True, "channel": channel_id})

    def delete(self, request, channel_id):
        ChannelFavorite.objects.filter(
            user=request.user, channel_id=channel_id
        ).delete()
        return Response({"favorite": False, "channel": channel_id})
