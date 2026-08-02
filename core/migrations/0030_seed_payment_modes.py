from django.db import migrations

MODES = [
    "Cash in Compass", "Compass Bank Muscat", "Compass NBO",
    "Cheque in Compass Name", "Direct to Client", "Cheque in Client Name",
    "Bank Transfer", "Online Payment", "Credit Card", "Debit Card",
]


def seed(apps, schema_editor):
    PaymentMode = apps.get_model('core', 'PaymentMode')
    for name in MODES:
        PaymentMode.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    apps.get_model('core', 'PaymentMode').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0029_paymentmode')]
    operations = [migrations.RunPython(seed, unseed)]
