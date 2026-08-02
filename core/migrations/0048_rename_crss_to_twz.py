from django.db import migrations
from django.db.models.functions import Replace
from django.db.models import Value, F


def rename_crss_to_twz(apps, schema_editor):
    Client  = apps.get_model('core', 'Client')
    Debtor  = apps.get_model('core', 'Debtor')
    Case    = apps.get_model('core', 'Case')
    Payment = apps.get_model('core', 'Payment')

    Client.objects.filter(client_id__startswith='CRSS/').update(
        client_id=Replace(F('client_id'), Value('CRSS/'), Value('TWZ/'))
    )
    Debtor.objects.filter(debtor_id__startswith='CRSS/').update(
        debtor_id=Replace(F('debtor_id'), Value('CRSS/'), Value('TWZ/'))
    )
    Case.objects.filter(case_id__startswith='CRSS/').update(
        case_id=Replace(F('case_id'), Value('CRSS/'), Value('TWZ/'))
    )
    Payment.objects.filter(payment_id__startswith='CRSS/').update(
        payment_id=Replace(F('payment_id'), Value('CRSS/'), Value('TWZ/'))
    )


def reverse_twz_to_crss(apps, schema_editor):
    Client  = apps.get_model('core', 'Client')
    Debtor  = apps.get_model('core', 'Debtor')
    Case    = apps.get_model('core', 'Case')
    Payment = apps.get_model('core', 'Payment')

    Client.objects.filter(client_id__startswith='TWZ/').update(
        client_id=Replace(F('client_id'), Value('TWZ/'), Value('CRSS/'))
    )
    Debtor.objects.filter(debtor_id__startswith='TWZ/').update(
        debtor_id=Replace(F('debtor_id'), Value('TWZ/'), Value('CRSS/'))
    )
    Case.objects.filter(case_id__startswith='TWZ/').update(
        case_id=Replace(F('case_id'), Value('TWZ/'), Value('CRSS/'))
    )
    Payment.objects.filter(payment_id__startswith='TWZ/').update(
        payment_id=Replace(F('payment_id'), Value('TWZ/'), Value('CRSS/'))
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0047_case_additional_users'),
    ]

    operations = [
        migrations.RunPython(rename_crss_to_twz, reverse_twz_to_crss),
    ]
