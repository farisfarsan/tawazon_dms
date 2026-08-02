from django.db import migrations

FULL_GRANT = {
    'can_status': True, 'can_financial': True, 'can_collector': True,
    'can_followup': True, 'can_history': True, 'can_payment_history': True,
    'can_attachments': True,
}


def forwards(apps, schema_editor):
    """Re-run of 0089's backfill: catches any ClientLoginAccess created
    between that migration and this one (client_login_access_create didn't
    grant access to the client's existing cases until this fix)."""
    Case = apps.get_model('core', 'Case')
    ClientLoginAccess = apps.get_model('core', 'ClientLoginAccess')
    ClientCaseAccess = apps.get_model('core', 'ClientCaseAccess')

    accesses_by_client = {}
    for acc in ClientLoginAccess.objects.all():
        accesses_by_client.setdefault(acc.client_id, []).append(acc)

    for case in Case.objects.all():
        for acc in accesses_by_client.get(case.client_id, []):
            ClientCaseAccess.objects.update_or_create(
                access=acc, case=case, defaults=FULL_GRANT,
            )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('core', '0089_backfill_client_case_access')]
    operations = [migrations.RunPython(forwards, backwards)]
