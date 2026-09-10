from django.db import migrations

# Only these countries stay enabled (shown in dropdowns). Everything else is
# disabled — not deleted, so it can be turned back on from
# Settings → Localisation → Countries at any time.
ENABLED_COUNTRIES = [
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
    keep = {n.lower() for n in ENABLED_COUNTRIES}
    for c in Country.objects.all():
        want = c.name.strip().lower() in keep
        if c.is_enabled != want:
            c.is_enabled = want
            c.save(update_fields=["is_enabled"])


def revert(apps, schema_editor):
    # Re-enable everything (original state after the country seed).
    Country = apps.get_model("core", "Country")
    Country.objects.filter(is_enabled=False).update(is_enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0090_backfill_client_case_access_v2"),
    ]

    operations = [
        migrations.RunPython(apply, revert),
    ]
