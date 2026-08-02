from django.db import migrations

# Old name -> new name (Compass branding replaced with Tawazon)
RENAMES = {
    "Cash in Compass":        "Cash in Tawazon",
    "Compass Bank Muscat":    "Tawazon Bank Muscat",
    "Compass NBO":            "Tawazon NBO",
    "Cheque in Compass Name": "Cheque in Tawazon Name",
}


def forwards(apps, schema_editor):
    PaymentMode = apps.get_model('core', 'PaymentMode')
    for old, new in RENAMES.items():
        PaymentMode.objects.filter(name=old).update(name=new)


def backwards(apps, schema_editor):
    PaymentMode = apps.get_model('core', 'PaymentMode')
    for old, new in RENAMES.items():
        PaymentMode.objects.filter(name=new).update(name=old)


class Migration(migrations.Migration):
    dependencies = [('core', '0053_attachment_type_fields')]
    operations = [migrations.RunPython(forwards, backwards)]
