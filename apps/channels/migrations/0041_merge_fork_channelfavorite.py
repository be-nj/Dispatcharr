from django.db import migrations


class Migration(migrations.Migration):
    """Join the fork's ChannelFavorite branch with upstream's 0039/0040 chain."""

    dependencies = [
        ("dispatcharr_channels", "0039_channelfavorite"),
        ("dispatcharr_channels", "0040_channelgroup_custom_relation"),
    ]

    operations = []
