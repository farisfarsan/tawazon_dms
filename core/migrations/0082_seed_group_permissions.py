from django.db import migrations

# Existing groups were created before the permission matrix existed; seed them
# with full permissions so current staff lose nothing until an admin edits.

PERMISSION_ACTIONS = ['view', 'add', 'edit', 'delete', 'print']
PERMISSION_MODULES = ['clients', 'debtors', 'cases', 'legal_cases', 'payments',
                      'follow_ups', 'reports', 'lawyers', 'agencies', 'users', 'settings']


def seed(apps, schema_editor):
    UserGroup = apps.get_model('core', 'UserGroup')
    full = {m: list(PERMISSION_ACTIONS) for m in PERMISSION_MODULES}
    for g in UserGroup.objects.all():
        if not g.permissions:
            g.permissions = full
            g.save(update_fields=['permissions'])


def unseed(apps, schema_editor):
    apps.get_model('core', 'UserGroup').objects.update(permissions={})


class Migration(migrations.Migration):
    dependencies = [('core', '0081_usergroup_permissions_userprofile_perm_grants_and_more')]
    operations = [migrations.RunPython(seed, unseed)]
