from django.db import migrations

# Mark the pre-existing admin-style groups as admin groups and elevate their
# current members, so accounts like the one already placed in "Admin" behave
# as admins the way the group name promises.

ADMIN_GROUP_NAMES = ['admin', 'super admin']


def flag(apps, schema_editor):
    UserGroup = apps.get_model('core', 'UserGroup')
    UserProfile = apps.get_model('core', 'UserProfile')
    User = apps.get_model('auth', 'User')
    admin_groups = UserGroup.objects.filter(name__iregex=r'^(' + '|'.join(ADMIN_GROUP_NAMES) + r')$')
    admin_groups.update(is_admin=True)
    member_ids = UserProfile.objects.filter(user_group__in=admin_groups).values_list('user_id', flat=True)
    User.objects.filter(pk__in=list(member_ids)).update(is_superuser=True, is_staff=True)


def unflag(apps, schema_editor):
    apps.get_model('core', 'UserGroup').objects.update(is_admin=False)


class Migration(migrations.Migration):
    dependencies = [('core', '0083_usergroup_is_admin')]
    operations = [migrations.RunPython(flag, unflag)]
