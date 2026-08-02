from django.db import migrations

CASE_TYPES = [
    "Personal Loan", "Purchase of Goods", "Purchase of Service", "Overdraft",
    "Vehicle Loan", "Company Loan", "School fee", "Credit Card",
    "Vehicle Insurance", "Investment Murabaha", "TAWARRUQ", "NETWORK",
    "DINERS", "Medical Loan", "Home Loan", "Business Loan",
    "Equipment Loan", "Travel Loan", "Education Loan", "Mortgage",
]


def seed(apps, schema_editor):
    CaseType = apps.get_model('core', 'CaseType')
    for name in CASE_TYPES:
        CaseType.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    apps.get_model('core', 'CaseType').objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0019_casetype')]
    operations = [migrations.RunPython(seed, unseed)]
