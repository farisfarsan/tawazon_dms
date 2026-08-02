from django.db import migrations

# Old name -> new name (Compass branding replaced with Tawazon)
CASE_STATUS_RENAMES = {
    "Closed by Compass Request": "Closed by Tawazon Request",
    "Compass Request to close":  "Tawazon Request to close",
}
LEGAL_CASE_STATUS_RENAMES = {
    "Closed-by Compass Request": "Closed-by Tawazon Request",
}


def forwards(apps, schema_editor):
    CaseStatus = apps.get_model('core', 'CaseStatus')
    LegalCaseStatus = apps.get_model('core', 'LegalCaseStatus')
    for old, new in CASE_STATUS_RENAMES.items():
        CaseStatus.objects.filter(name=old).update(name=new)
    for old, new in LEGAL_CASE_STATUS_RENAMES.items():
        LegalCaseStatus.objects.filter(name=old).update(name=new)


def backwards(apps, schema_editor):
    CaseStatus = apps.get_model('core', 'CaseStatus')
    LegalCaseStatus = apps.get_model('core', 'LegalCaseStatus')
    for old, new in CASE_STATUS_RENAMES.items():
        CaseStatus.objects.filter(name=new).update(name=old)
    for old, new in LEGAL_CASE_STATUS_RENAMES.items():
        LegalCaseStatus.objects.filter(name=new).update(name=old)


class Migration(migrations.Migration):
    dependencies = [('core', '0087_alter_debtorcontact_contact_type')]
    operations = [migrations.RunPython(forwards, backwards)]
