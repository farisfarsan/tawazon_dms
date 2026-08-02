from django.db import migrations

# The canonical mode list. The first three are "Tawazon" modes whose payments
# get a downloadable receipt (see Payment.RECEIPT_MODES).
CANONICAL = [
    'Cash in Tawazon',
    'Transfer to Tawazon',
    'Cheque to Tawazon',
    'Direct to Client',
    'Cheque to Client',
]

# Old name → canonical name (renaming keeps existing payments' FK intact).
RENAMES = {
    'Bank Transfer': 'Transfer to Tawazon',
    'Cheque in Tawazon Name': 'Cheque to Tawazon',
    'Cheque in Client Name': 'Cheque to Client',
}


def forwards(apps, schema_editor):
    PaymentMode = apps.get_model('core', 'PaymentMode')

    for old, new in RENAMES.items():
        if not PaymentMode.objects.filter(name__iexact=new).exists():
            PaymentMode.objects.filter(name__iexact=old).update(name=new)

    for name in CANONICAL:
        mode, _ = PaymentMode.objects.get_or_create(name=name)
        if not mode.is_enabled:
            mode.is_enabled = True
            mode.save(update_fields=['is_enabled'])

    for mode in PaymentMode.objects.exclude(name__in=CANONICAL):
        if mode.payments.exists():
            # Still referenced by payments — keep the history but hide it
            # from the dropdowns.
            mode.is_enabled = False
            mode.save(update_fields=['is_enabled'])
        else:
            mode.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0084_flag_admin_groups'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
