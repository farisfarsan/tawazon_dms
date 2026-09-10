from django.db import migrations

# The only countries kept in the system. Every other Country row is deleted
# (which also cascade-deletes its States — none of them are referenced by
# clients/debtors/cases, those store country as free text).
#
# To restore the full list later, reverse-then-reapply migrations
# 0014_seed_countries and 0016_seed_states.
KEEP_COUNTRIES = [
    # Arab League
    "Algeria", "Bahrain", "Comoros", "Djibouti", "Egypt", "Iraq", "Jordan",
    "Kuwait", "Lebanon", "Libya", "Mauritania", "Morocco", "Oman", "Palestine",
    "Qatar", "Saudi Arabia", "Somalia", "Sudan", "Syria", "Tunisia",
    "United Arab Emirates", "Yemen",
    # plus
    "India",
]


def apply(apps, schema_editor):
    Country = apps.get_model("core", "Country")
    keep = {n.lower() for n in KEEP_COUNTRIES}
    to_delete = [c.pk for c in Country.objects.all() if c.name.strip().lower() not in keep]
    Country.objects.filter(pk__in=to_delete).delete()
    # Make sure the survivors are enabled.
    Country.objects.update(is_enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0091_enable_regional_countries_only"),
    ]

    operations = [
        # Irreversible: deleted rows can't be brought back automatically.
        migrations.RunPython(apply, migrations.RunPython.noop),
    ]
