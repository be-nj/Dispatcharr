"""Seed the fork's default output profiles.

"audiofix" copies video and converts audio to stereo AAC — the common fix for
TVs that cannot decode AC3/EAC3. "720p" additionally downscales and caps the
video bitrate for constrained clients. Clients select them per request via
`?output_profile=audiofix` (or by id); `?output_profile=raw` bypasses any
transcode step.
"""

from django.db import migrations

PROFILES = [
    (
        "audiofix",
        "ffmpeg",
        "-hide_banner -loglevel error -i pipe:0 -map 0:v -map 0:a -c:v copy "
        "-c:a aac -ac 2 -b:a 160k -f mpegts pipe:1",
    ),
    (
        "720p",
        "ffmpeg",
        "-hide_banner -loglevel error -i pipe:0 -map 0:v -map 0:a "
        "-c:v libx264 -preset veryfast -b:v 2500k -maxrate 3000k -bufsize 6000k "
        "-vf scale=-2:720 -c:a aac -ac 2 -b:a 160k -f mpegts pipe:1",
    ),
]


def seed(apps, schema_editor):
    OutputProfile = apps.get_model("core", "OutputProfile")
    for name, command, parameters in PROFILES:
        OutputProfile.objects.get_or_create(
            name=name,
            defaults={"command": command, "parameters": parameters, "is_active": True},
        )


def unseed(apps, schema_editor):
    OutputProfile = apps.get_model("core", "OutputProfile")
    OutputProfile.objects.filter(name__in=[p[0] for p in PROFILES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_vlc_play_and_exit"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
