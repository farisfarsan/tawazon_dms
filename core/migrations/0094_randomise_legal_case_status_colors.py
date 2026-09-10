import random

from django.db import migrations

# A spread of distinct, readable badge colours. Assigned in shuffled order so
# every Legal Case Status gets one (falling back to a random hex if there are
# more statuses than palette entries). Any colour already set is overwritten.
PALETTE = [
    "#2563eb", "#0d9488", "#7c3aed", "#db2777", "#ea580c", "#16a34a",
    "#0891b2", "#9333ea", "#e11d48", "#d97706", "#4f46e5", "#059669",
    "#c026d3", "#dc2626", "#65a30d", "#0284c7", "#f59e0b", "#be123c",
    "#15803d", "#6d28d9", "#0e7490", "#b45309", "#1d4ed8", "#a21caf",
]


def apply(apps, schema_editor):
    LegalCaseStatus = apps.get_model("core", "LegalCaseStatus")
    rows = list(LegalCaseStatus.objects.all().order_by("name"))
    pool = PALETTE[:]
    random.shuffle(pool)
    used = set()
    for i, s in enumerate(rows):
        if i < len(pool):
            colour = pool[i]
        else:
            while True:
                colour = "#%06x" % random.randint(0, 0xFFFFFF)
                if colour not in used and colour not in pool:
                    break
        used.add(colour)
        s.color = colour
        s.save(update_fields=["color"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0093_recalc_case_received_cleared_only"),
    ]

    operations = [
        migrations.RunPython(apply, migrations.RunPython.noop),
    ]
