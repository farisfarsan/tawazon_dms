from django.db import migrations

TYPES = [
    "Direct Call", "Email", "Email to Client", "Email to Debtor",
    "Field Visit", "Meeting", "Message", "Third Party Contact",
    "Visit in Compass", "Whatsapp", "SMS", "Letter",
]


def seed(apps, schema_editor):
    FollowupType = apps.get_model('core', 'FollowupType')
    for name in TYPES:
        FollowupType.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    apps.get_model('core', 'FollowupType').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0027_followuptype')]
    operations = [migrations.RunPython(seed, unseed)]
