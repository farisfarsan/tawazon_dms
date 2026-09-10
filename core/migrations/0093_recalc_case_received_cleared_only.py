from django.db import migrations
from django.db.models import Sum


def apply(apps, schema_editor):
    Case = apps.get_model("core", "Case")
    for case in Case.objects.all():
        total = (
            case.payments.filter(status="cleared").aggregate(t=Sum("received_amount"))["t"]
            or 0
        )
        if case.received_amount != total:
            case.received_amount = total
            case.save(update_fields=["received_amount"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0092_delete_nonregional_countries"),
    ]

    operations = [
        migrations.RunPython(apply, migrations.RunPython.noop),
    ]
