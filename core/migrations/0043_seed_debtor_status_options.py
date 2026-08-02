from django.db import migrations

INDIVIDUAL_STATUSES = ['Active', 'Passed Away', 'Differentially Abled']
ORG_STATUSES = ['Active', 'Closed', 'Suspended', 'Liquidated', 'Not Found']

def seed(apps, schema_editor):
    DebtorStatusOption = apps.get_model('core', 'DebtorStatusOption')
    for i, name in enumerate(INDIVIDUAL_STATUSES):
        DebtorStatusOption.objects.get_or_create(name=name, debtor_type='individual', defaults={'order': i})
    for i, name in enumerate(ORG_STATUSES):
        DebtorStatusOption.objects.get_or_create(name=name, debtor_type='organization', defaults={'order': i})

def unseed(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [('core', '0042_add_debtor_status_option')]
    operations = [migrations.RunPython(seed, unseed)]
