from django.db import migrations

TYPES = [
    "Individual", "Corporate", "Education", "Bank", "Insurance",
    "Telecommunication", "Hotel", "Finance", "Agency", "Hospital",
    "Government", "NGO",
]


def seed(apps, schema_editor):
    ClientType = apps.get_model('core', 'ClientType')
    for name in TYPES:
        ClientType.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    apps.get_model('core', 'ClientType').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0031_clienttype')]
    operations = [migrations.RunPython(seed, unseed)]
