from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import Client, Debtor, Case, CaseType, FollowUp, Payment
from decimal import Decimal
import random
from datetime import date, timedelta

EMPLOYEES = [
    {'username': 'twz1_faris',  'first_name': 'Faris',  'last_name': 'Al Balushi',  'email': 'faris@tawazon.om'},
    {'username': 'twz2_ahmed',  'first_name': 'Ahmed',  'last_name': 'Al Rashdi',   'email': 'ahmed@tawazon.om'},
    {'username': 'twz3_sara',   'first_name': 'Sara',   'last_name': 'Al Mansoori', 'email': 'sara@tawazon.om'},
    {'username': 'twz4_omar',   'first_name': 'Omar',   'last_name': 'Al Harthi',   'email': 'omar@tawazon.om'},
    {'username': 'twz5_laila',  'first_name': 'Laila',  'last_name': 'Al Zadjali',  'email': 'laila@tawazon.om'},
]

CLIENTS = [
    {'name': 'Tawazon Capital Bank',      'client_type': 'bank',      'country': 'Oman',   'city': 'Muscat',      'phone': '+968 2411 0011', 'email': 'accounts@tawazoncapital.om',  'contact_person': 'Faris Al Balushi'},
    {'name': 'Tawazon Finance Group',     'client_type': 'finance',   'country': 'Oman',   'city': 'Sohar',       'phone': '+968 2672 3300', 'email': 'finance@tawazonfg.om',        'contact_person': 'Ahmed Al Rashdi'},
    {'name': 'Tawazon Medical LLC',       'client_type': 'hospital',  'country': 'Oman',   'city': 'Salalah',     'phone': '+968 2323 8800', 'email': 'billing@tawmed.om',           'contact_person': 'Sara Al Mansoori'},
    {'name': 'Tawazon Auto Group',        'client_type': 'corporate', 'country': 'Oman',   'city': 'Muscat',      'phone': '+968 2491 5500', 'email': 'credit@twzauto.om',           'contact_person': 'Omar Al Harthi'},
    {'name': 'Tawazon Telecom Services',  'client_type': 'corporate', 'country': 'Oman',   'city': 'Nizwa',       'phone': '+968 2541 7700', 'email': 'ar@twztelecom.om',            'contact_person': 'Laila Al Zadjali'},
    {'name': 'Tawazon Education Trust',   'client_type': 'education', 'country': 'Oman',   'city': 'Muscat',      'phone': '+968 2433 2200', 'email': 'admin@twzedu.om',             'contact_person': 'Faris Al Balushi'},
]

DEBTORS = [
    {'name': 'Khalid Nasser Al Farsi',    'nationality': 'Omani',  'phone': '+968 9911 2233', 'email': 'khalid.farsi@mail.om',   'city': 'Muscat'},
    {'name': 'Maryam Said Al Wahaibi',    'nationality': 'Omani',  'phone': '+968 9922 3344', 'email': 'maryam.wahaibi@mail.om', 'city': 'Sohar'},
    {'name': 'Tariq Hamad Al Amri',       'nationality': 'Omani',  'phone': '+968 9933 4455', 'email': 'tariq.amri@mail.om',     'city': 'Nizwa'},
    {'name': 'Fatima Yusuf Al Kindi',     'nationality': 'Omani',  'phone': '+968 9944 5566', 'email': 'fatima.kindi@mail.om',   'city': 'Salalah'},
    {'name': 'Hamed Saif Al Maawali',     'nationality': 'Omani',  'phone': '+968 9955 6677', 'email': 'hamed.maawali@mail.om',  'city': 'Muscat'},
    {'name': 'Noura Abdullah Al Siyabi',  'nationality': 'Omani',  'phone': '+968 9966 7788', 'email': 'noura.siyabi@mail.om',   'city': 'Muscat'},
    {'name': 'Bader Khalil Al Habsi',     'nationality': 'Omani',  'phone': '+968 9977 8899', 'email': 'bader.habsi@mail.om',    'city': 'Sur'},
    {'name': 'Aisha Mahmoud Al Lawati',   'nationality': 'Omani',  'phone': '+968 9988 9900', 'email': 'aisha.lawati@mail.om',   'city': 'Muscat'},
    {'name': 'Salim Rashid Al Busaidi',   'nationality': 'Omani',  'phone': '+968 9900 1122', 'email': 'salim.busaidi@mail.om',  'city': 'Ibri'},
    {'name': 'Reem Ahmed Al Maskari',     'nationality': 'Omani',  'phone': '+968 9811 2233', 'email': 'reem.maskari@mail.om',   'city': 'Muscat'},
    {'name': 'Walid Juma Al Shaibani',    'nationality': 'Omani',  'phone': '+968 9822 3344', 'email': 'walid.shaibani@mail.om', 'city': 'Muscat'},
    {'name': 'Dina Faisal Al Ghafri',     'nationality': 'Omani',  'phone': '+968 9833 4455', 'email': 'dina.ghafri@mail.om',    'city': 'Sohar'},
]

FOLLOWUP_NOTES = [
    'Called debtor, no answer. Left voicemail.',
    'Spoke with debtor, promised to pay by end of month.',
    'Debtor requested payment plan. Under review.',
    'Follow-up call made. Debtor is abroad.',
    'Email sent with payment details.',
    'SMS reminder sent. Awaiting response.',
    'Debtor visited office. Partial payment made.',
    'Debtor disputes the outstanding amount.',
    'Contacted guarantor. Will discuss with debtor.',
    'Debtor requested more time due to financial hardship.',
]


class Command(BaseCommand):
    help = 'Seed employee users and sample data attributed to them'

    def handle(self, *args, **options):
        self.stdout.write('Creating employee users...')
        employees = []
        for e in EMPLOYEES:
            user, created = User.objects.get_or_create(
                username=e['username'],
                defaults={
                    'first_name': e['first_name'],
                    'last_name':  e['last_name'],
                    'email':      e['email'],
                    'is_staff':   True,
                }
            )
            if created:
                user.set_password('Tawazon@123')
                user.save()
                self.stdout.write(f'  Created user: {user.username}')
            else:
                self.stdout.write(f'  User already exists: {user.username}')
            employees.append(user)

        self.stdout.write('Creating clients...')
        created_clients = []
        for cd in CLIENTS:
            client, created = Client.objects.get_or_create(
                name=cd['name'],
                defaults={
                    'client_type':    cd['client_type'],
                    'country':        cd['country'],
                    'city':           cd['city'],
                    'phone':          cd['phone'],
                    'email':          cd['email'],
                    'contact_person': cd['contact_person'],
                    'contract_type':  'fixed_regular',
                    'status':         'active',
                    'created_by':     random.choice(employees),
                }
            )
            created_clients.append(client)
            if created:
                self.stdout.write(f'  Created client: {client.name}')

        self.stdout.write('Creating debtors...')
        created_debtors = []
        for dd in DEBTORS:
            debtor, created = Debtor.objects.get_or_create(
                name=dd['name'],
                defaults={
                    'phone':       dd['phone'],
                    'email':       dd['email'],
                    'city':        dd['city'],
                    'nationality': dd.get('nationality', 'Omani'),
                    'status':      'active',
                    'created_by':  random.choice(employees),
                }
            )
            created_debtors.append(debtor)
            if created:
                self.stdout.write(f'  Created debtor: {debtor.name}')

        case_types = list(CaseType.objects.all())
        statuses   = ['active', 'contactable', 'broken_promise', 'active', 'active', 'contactable']

        self.stdout.write('Creating cases...')
        created_cases = []
        today = date.today()

        for i in range(25):
            client    = random.choice(created_clients)
            debtor    = random.choice(created_debtors)
            employee  = random.choice(employees)
            approved  = Decimal(random.randint(500, 50000))
            received  = Decimal(random.randint(0, int(approved * Decimal('0.6'))))
            recv_date = today - timedelta(days=random.randint(30, 730))

            case = Case.objects.create(
                client=client,
                debtor=debtor,
                approved_amount=approved,
                received_amount=received,
                status=random.choice(statuses),
                collector=employee,
                creditor_name=client.name,
                received_date=recv_date,
                case_type=random.choice(case_types) if case_types else None,
                account_no=f'ACC{random.randint(100000, 999999)}',
                case_country='Oman',
            )
            created_cases.append(case)

        self.stdout.write(f'  Created {len(created_cases)} cases')

        self.stdout.write('Creating follow-ups...')
        fu_types   = ['call', 'email', 'visit', 'sms']
        fu_count   = 0
        for case in created_cases:
            num_fus = random.randint(1, 4)
            for j in range(num_fus):
                fu_date = today - timedelta(days=random.randint(1, 180))
                FollowUp.objects.create(
                    case=case,
                    follow_up_date=fu_date,
                    follow_up_type=random.choice(fu_types),
                    case_status=case.status,
                    followed_by=case.collector,
                    notes=random.choice(FOLLOWUP_NOTES),
                    is_legal=False,
                )
                fu_count += 1
        self.stdout.write(f'  Created {fu_count} follow-ups')

        self.stdout.write('Creating payments...')
        pay_count = 0
        for case in created_cases:
            if case.received_amount > 0 and random.random() > 0.3:
                Payment.objects.create(
                    case=case,
                    payment_date=today - timedelta(days=random.randint(1, 90)),
                    amount=case.received_amount,
                    payment_method=random.choice(['bank_transfer', 'cheque', 'cash']),
                    status=random.choice(['cleared', 'pending']),
                    created_by=case.collector,
                )
                pay_count += 1
        self.stdout.write(f'  Created {pay_count} payments')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone. 5 employees, {len(created_clients)} clients, '
            f'{len(created_debtors)} debtors, {len(created_cases)} cases, '
            f'{fu_count} follow-ups, {pay_count} payments.'
        ))
        self.stdout.write('\nEmployee login credentials:')
        for e in EMPLOYEES:
            self.stdout.write(f"  {e['username']} / Tawazon@123")
