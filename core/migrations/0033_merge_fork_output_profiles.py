from django.db import migrations


class Migration(migrations.Migration):
    """Join the fork's seeded output profiles with upstream's 0029-0032 chain."""

    dependencies = [
        ("core", "0029_seed_fork_output_profiles"),
        ("core", "0032_limit_default_interleave_delta"),
    ]

    operations = []
