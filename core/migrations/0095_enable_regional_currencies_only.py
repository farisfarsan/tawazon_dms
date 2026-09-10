from django.db import migrations

# Currencies of the enabled countries (Arab League + India), plus OMR (the
# system base) and USD (used for cross-border settlement). Everything else is
# disabled — NOT deleted, because payments/cases reference currencies and a
# delete would blank that history. Re-enable any from
# Settings → Localisation → Currencies.
ENABLED_CODES = {
    "OMR", "USD",
    "AED", "SAR", "QAR", "KWD", "BHD",       # GCC
    "INR", "EGP", "JOD", "LBP", "MAD",       # India + Levant/North Africa
    "IQD", "DZD", "TND", "LYD", "SDG",
    "SYP", "YER", "SOS", "MRU", "DJF", "KMF", "ILS",
}


def apply(apps, schema_editor):
    Currency = apps.get_model("core", "Currency")
    for c in Currency.objects.all():
        want = c.code.strip().upper() in ENABLED_CODES
        if c.is_enabled != want:
            c.is_enabled = want
            c.save(update_fields=["is_enabled"])


def revert(apps, schema_editor):
    Currency = apps.get_model("core", "Currency")
    Currency.objects.filter(is_enabled=False).update(is_enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0094_randomise_legal_case_status_colors"),
    ]

    operations = [
        migrations.RunPython(apply, revert),
    ]
