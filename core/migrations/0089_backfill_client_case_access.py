from django.db import migrations

FULL_GRANT = {
    'can_status': True, 'can_financial': True, 'can_collector': True,
    'can_followup': True, 'can_history': True, 'can_payment_history': True,
    'can_attachments': True,
}


def forwards(apps, schema_editor):
    """Every case now grants full portal visibility to its client's logins as
    soon as it's created (see _grant_full_client_case_access in views.py).
    Before this fix, that grant never happened automatically — cases only
    became visible if staff manually ticked permissions in Settings → Client
    Portal Access, which had never actually been done. Backfill every
    existing case so it isn't stuck invisible."""
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
    # No safe reverse — undoing this would revoke access an admin may have
    # since customized by hand. Leave grants in place.
    pass


class Migration(migrations.Migration):
    dependencies = [('core', '0088_rename_compass_statuses')]
    operations = [migrations.RunPython(forwards, backwards)]
