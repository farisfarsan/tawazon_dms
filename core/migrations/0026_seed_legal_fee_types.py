from django.db import migrations

FEE_TYPES = [
    "Court Fee", "Registration Fee", "Announcement Fee", "Translation Fee",
    "Travel Ban Registration Fee", "Account Expert Fee",
    "Catch Order Fee", "Account Freezing Fee",
    "Lawyer Fee", "Enforcement Fee", "Appeal Fee", "Notary Fee",
]


def seed(apps, schema_editor):
    LegalFeeType = apps.get_model('core', 'LegalFeeType')
    for name in FEE_TYPES:
        LegalFeeType.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    apps.get_model('core', 'LegalFeeType').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0025_legalfeetype')]
    operations = [migrations.RunPython(seed, unseed)]
