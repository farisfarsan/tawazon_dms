from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta
from decimal import Decimal


class Client(models.Model):
    CLIENT_TYPE_CHOICES = [
        ('agency', 'Agency'),
        ('bank', 'Bank'),
        ('corporate', 'Corporate'),
        ('education', 'Education'),
        ('finance', 'Finance'),
        ('hospital', 'Hospital'),
        ('hotel', 'Hotel'),
        ('individual', 'Individual'),
        ('insurance', 'Insurance'),
        ('telecommunication', 'Telecommunication'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]

    CONTRACT_TYPE_CHOICES = [
        ('one_time', 'One time'),
        ('fixed_regular', 'Fixed Regular'),
        ('variable_regular', 'Variable Regular'),
    ]

    client_id = models.CharField(max_length=50, unique=True, blank=True, help_text="Auto-generated like TWZ/2025/01/C001")
    name = models.CharField(max_length=200)
    alias_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    mobile = models.CharField(max_length=50, blank=True)
    contact_person = models.CharField(max_length=200, blank=True)
    client_type = models.CharField(max_length=20, choices=CLIENT_TYPE_CHOICES, default='corporate')
    contract_type = models.CharField(max_length=20, choices=CONTRACT_TYPE_CHOICES, blank=True)
    country = models.CharField(max_length=100, default='Oman')
    address = models.CharField(max_length=300, blank=True)
    address2 = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    po_box = models.CharField(max_length=50, blank=True)
    google_location = models.CharField(max_length=500, blank=True, help_text='Google Maps link or location')
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['name']),
            models.Index(fields=['status']),
            models.Index(fields=['client_id']),
        ]

    def save(self, *args, **kwargs):
        if not self.client_id:
            from django.utils import timezone
            now = timezone.now()
            count = Client.objects.count() + 1
            self.client_id = f"TWZ/{now.year}/{now.month:02d}/C{count:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ClientContact(models.Model):
    CONTACT_TYPE_CHOICES = [
        ('accounts', 'Accounts'),
        ('sales_manager', 'Sales Manager'),
        ('chairman', 'Chairman'),
        ('assistant_manager', 'Assistant Manager'),
        ('managing_partner', 'Managing Partner'),
        ('owner', 'Owner'),
        ('other', 'Other'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=200)
    contact_type = models.CharField(max_length=30, choices=CONTACT_TYPE_CHOICES, default='other')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.client.name})"


class Debtor(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]

    debtor_id = models.CharField(max_length=50, unique=True, blank=True, help_text="Auto-generated like TWZ/2025/D0001")
    is_organization = models.BooleanField(default=False)
    name = models.CharField(max_length=200)
    first_name = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    passport_cr_number = models.CharField(max_length=100, blank=True)
    id_number = models.CharField(max_length=100, blank=True)
    cr_no = models.CharField(max_length=100, blank=True)
    occi_no = models.CharField(max_length=100, blank=True)
    vatin_no = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    email2 = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    employer_name = models.CharField(max_length=200, blank=True)
    employer_phone = models.CharField(max_length=255, blank=True, help_text='Multiple numbers may be comma-separated.')
    employer_email = models.EmailField(blank=True)
    employer_address = models.TextField(blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='debtors_created')
    collector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='debtors_collected')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['name']),
            models.Index(fields=['status']),
            models.Index(fields=['debtor_id']),
            models.Index(fields=['email']),
        ]

    def save(self, *args, **kwargs):
        if not self.debtor_id:
            from django.utils import timezone
            now = timezone.now()
            count = Debtor.objects.count() + 1
            self.debtor_id = f"TWZ/{now.year}/D{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# Cached result of Case.all_status_choices(); cleared by signals when a
# CaseStatus row is added/edited/deleted in Settings → Case Status.
_status_choices_cache = None
# Cached {status_key: '#hex'} from Settings → Case Status (same invalidation).
_status_colors_cache = None


def case_status_color_map():
    """{status key: configured hex color} for every status whose Settings →
    Case Status row has a color. Keys match Case.all_status_choices()."""
    global _status_colors_cache
    if _status_colors_cache is None:
        by_label = {cs.name.strip().lower(): (cs.color or '').strip()
                    for cs in CaseStatus.objects.filter(is_enabled=True)}
        colors = {}
        for key, label in Case.all_status_choices():
            color = by_label.get(label.strip().lower())
            if color:
                colors[key] = color
        _status_colors_cache = colors
    return dict(_status_colors_cache)


class Case(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('broken_promise', 'Broken Promise'),
        ('contactable', 'Contactable'),
        ('promise_to_pay', 'Promise to Pay'),
        ('legal_action_approved', 'Legal Action Approved'),
        ('closed_by_client', 'Closed by Client request'),
        ('closed', 'Closed'),
    ]

    @classmethod
    def all_status_choices(cls):
        """STATUS_CHOICES merged with the enabled rows of Settings → Case
        Status. A row whose name matches a legacy label keeps the legacy key
        (existing data lines up); other rows get a slug key, e.g.
        "Closed-Payment Done" → closed_payment_done. Sorted by label."""
        global _status_choices_cache
        if _status_choices_cache is None:
            choices = list(cls.STATUS_CHOICES)
            seen = {label.strip().lower() for _, label in choices}
            for cs in CaseStatus.objects.filter(is_enabled=True):
                label = cs.name.strip()
                if not label or label.lower() in seen:
                    continue
                seen.add(label.lower())
                choices.append((slugify(label).replace('-', '_')[:30], label))
            choices.sort(key=lambda c: c[1].lower())
            _status_choices_cache = choices
        return list(_status_choices_cache)

    def get_status_display(self):
        # Overrides Django's auto method so statuses added via Settings →
        # Case Status (not in the field's hardcoded choices) still show
        # their proper label.
        return dict(type(self).all_status_choices()).get(self.status, self.status)

    # Statuses that require a date when set (Change Status modal enforces this).
    DATE_REQUIRED_STATUSES = {'promise_to_pay'}

    # Statuses hidden from the default All Cases load (revealed via "Show All").
    # Any status whose key contains "closed" is hidden, plus legal_action_approved.
    LEGAL_STATUS = 'legal_action_approved'

    case_id = models.CharField(max_length=60, unique=True, blank=True, help_text="Auto-generated like TWZ/2025/01/0001")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='cases')
    debtor = models.ForeignKey(Debtor, on_delete=models.CASCADE, related_name='cases')
    approved_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    received_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    currency = models.ForeignKey('Currency', on_delete=models.SET_NULL, null=True, blank=True, related_name='cases')
    principal_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    # Gross amount owed before discount (Total Approved = outstanding − discount).
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    commission = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    discount_given = models.BooleanField(default=False)
    # Basis / justification for the discount, shown next to it on the Financials tab.
    discount_note = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='active')
    # Date the debtor promised to pay by — set when status is changed to "Promise
    # to Pay"; surfaced date-wise in the Reminders → Payments tab.
    promise_to_pay_date = models.DateField(null=True, blank=True)
    # When that promise was marked Done from Reminders. A completed promise
    # stays listed there for 14 days (as "Completed"), then quietly drops off —
    # promise_to_pay_date itself is kept, and the case's status is untouched.
    promise_completed_at = models.DateTimeField(null=True, blank=True)
    collector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cases_collected')
    notes = models.TextField(blank=True)
    creditor_name = models.CharField(max_length=200, blank=True)
    received_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    case_type = models.ForeignKey('CaseType', on_delete=models.SET_NULL, null=True, blank=True, related_name='cases')
    account_no = models.CharField(max_length=100, blank=True)
    relationship_no = models.CharField(max_length=100, blank=True)
    shadow_account_no = models.CharField(max_length=100, blank=True)
    cif_no = models.CharField(max_length=100, blank=True)
    case_country = models.CharField(max_length=100, blank=True)
    is_agency = models.BooleanField(default=False)
    agency = models.ForeignKey('Agency', on_delete=models.SET_NULL, null=True, blank=True, related_name='cases')
    additional_users = models.ManyToManyField(User, blank=True, related_name='additional_cases')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['client']),
            models.Index(fields=['debtor']),
            models.Index(fields=['collector']),
        ]

    def save(self, *args, **kwargs):
        if not self.case_id:
            import re
            from django.utils import timezone
            now = timezone.now()
            # Use max existing sequence + 1, not count()+1 — after a deletion
            # the count can point at a number that is still taken.
            max_seq = 0
            for cid in Case.objects.values_list('case_id', flat=True):
                m = re.search(r'(\d+)$', cid or '')
                if m:
                    max_seq = max(max_seq, int(m.group(1)))
            self.case_id = f"TWZ/{now.year}/{now.month:02d}/{max_seq + 1:04d}"
        super().save(*args, **kwargs)
        # When a case is approved for legal action it should appear in the Legal
        # Cases section automatically — create the linked LegalCase if missing.
        if self.status == self.LEGAL_STATUS:
            self.ensure_legal_case()

    def ensure_legal_case(self, created_by=None):
        """Create the linked LegalCase record if it doesn't exist yet. Safe to
        call repeatedly (no-op when one already exists)."""
        from django.utils import timezone
        LegalCase.objects.get_or_create(
            case=self,
            defaults={
                # Mirror the case's status (e.g. "Legal Action Approved") as the
                # initial legal status; staff can change it later.
                'legal_status': self.get_status_display(),
                'legal_approved_date': timezone.now().date(),
                'created_by': created_by,
            },
        )

    @property
    def remaining_amount(self):
        # Case-currency equivalent of remaining_amount_omr so every screen
        # shows the same outstanding — driven by what has been COLLECTED,
        # matching the case Financials tab (not by transferred/received sums).
        rate = float(self.currency.value) if self.currency and self.currency.value else 1
        return self.remaining_amount_omr * rate

    @property
    def remaining_amount_omr(self):
        # OMR equivalent of the remaining amount, matching the Financials tab exactly:
        # approved (OMR) − total collected (OMR), where each payment's collection
        # amount is converted via its own collection currency.
        # Convention: OMR = amount / currency.value (units of currency per 1 OMR).
        rate = float(self.currency.value) if self.currency and self.currency.value else 1
        approved_omr = float(self.approved_amount) / rate if rate else float(self.approved_amount)
        total_collected_omr = 0.0
        for p in self.payments.all():
            # Only an Approved (cleared) payment has actually landed — a
            # Pending one hasn't been confirmed yet and a Rejected one never
            # will be, so neither reduces the outstanding balance.
            if p.is_installment or p.status != 'cleared':
                continue
            pr = float(p.collection_currency.value) if p.collection_currency and p.collection_currency.value else rate
            amt = float(p.amount or 0)
            total_collected_omr += amt / pr if pr else amt
        return approved_omr - total_collected_omr

    @property
    def age_of_case(self):
        from datetime import date
        start = self.received_date or self.created_at.date()
        today = date.today()
        delta = today - start
        years = delta.days // 365
        months = (delta.days % 365) // 30
        days = (delta.days % 365) % 30
        parts = []
        if years: parts.append(f"{years} Year{'s' if years != 1 else ''}")
        if months: parts.append(f"{months} Month{'s' if months != 1 else ''}")
        if days or not parts: parts.append(f"{days} Day{'s' if days != 1 else ''}")
        return ' '.join(parts)

    def __str__(self):
        return f"{self.client.name} vs {self.debtor.name}"


class DebtorContact(models.Model):
    # Organization-relationship types (shown when the debtor is a company)
    CONTACT_TYPE_CHOICES_ORG = [
        ('self', 'Self'),
        ('ceo', 'CEO'),
        ('chairman', 'Chairman'),
        ('managing_partner', 'Managing Partner'),
        ('owner', 'Owner'),
        ('sales_manager', 'Sales Manager'),
        ('assistant_manager', 'Assistant Manager'),
        ('accounts', 'Accounts'),
        ('guarantor', 'Guarantor'),
        ('other', 'Other'),
    ]
    # Family/personal-relationship types (shown when the debtor is an individual)
    CONTACT_TYPE_CHOICES_INDIVIDUAL = [
        ('self', 'Self'),
        ('guarantor', 'Guarantor'),
        ('father', 'Father'),
        ('mother', 'Mother'),
        ('spouse', 'Spouse'),
        ('son', 'Son'),
        ('daughter', 'Daughter'),
        ('sibling', 'Sibling'),
        ('guardian', 'Guardian'),
        ('friend', 'Friend'),
        ('colleague', 'Colleague'),
        ('other', 'Other'),
    ]
    CONTACT_TYPE_CHOICES = sorted(
        set(CONTACT_TYPE_CHOICES_ORG) | set(CONTACT_TYPE_CHOICES_INDIVIDUAL),
        key=lambda pair: pair[1],
    )

    debtor = models.ForeignKey(Debtor, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=200)
    contact_type = models.CharField(max_length=30, choices=CONTACT_TYPE_CHOICES, default='other')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=255, blank=True, help_text='Multiple numbers may be comma-separated.')
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.debtor.name})"


class FollowUp(models.Model):
    FOLLOW_UP_TYPE_CHOICES = [
        ('call', 'Call'),
        ('email', 'Email'),
        ('letter', 'Letter'),
        ('visit', 'Visit'),
        ('legal', 'Legal'),
        ('sms', 'SMS'),
        ('other', 'Other'),
    ]

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='follow_ups')
    # Stores either a legacy choice key or a configured FollowupType name
    # (Settings → Followup Types); get_follow_up_type_display falls back to
    # the raw value for names not in the legacy choices.
    follow_up_type = models.CharField(max_length=100, choices=FOLLOW_UP_TYPE_CHOICES, default='call')
    is_legal = models.BooleanField(default=False)
    follow_up_date = models.DateField()
    followed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='follow_ups_done')
    case_status = models.CharField(max_length=30, choices=Case.STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_case_status_display(self):
        # Like Case.get_status_display: resolves labels for statuses added
        # via Settings → Case Status that aren't in the hardcoded choices.
        return dict(Case.all_status_choices()).get(self.case_status, self.case_status)

    def __str__(self):
        return f"Follow Up #{self.pk} — {self.case}"


class CaseGroup(models.Model):
    name = models.CharField(max_length=200)
    cases = models.ManyToManyField(Case, related_name='groups', blank=True)
    collector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='case_groups_collected')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='case_groups_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class LegalCase(models.Model):
    # Legal statuses are managed in Settings → Legal Case Status (LegalCaseStatus).
    # The chosen status NAME is stored here as text. Legacy key → label map is
    # only used to migrate/display old records that predate the settings list.
    DEFAULT_STATUS = 'New Legal Case'
    LEGACY_STATUS_LABELS = {
        'pending': 'Pending',
        'under_execution': 'Under Execution',
        'in_court_hearing': 'In Court Hearing',
        'closed_payment_done': 'Closed-Payment Done',
        'closed': 'Closed',
        'other': 'Other',
    }

    case = models.OneToOneField(Case, on_delete=models.CASCADE, related_name='legal_case')
    lawyer_name = models.CharField(max_length=200, blank=True)
    lawyer = models.ForeignKey('Lawyer', on_delete=models.SET_NULL, null=True, blank=True, related_name='legal_cases')
    legal_approved_date = models.DateField(null=True, blank=True)
    legal_date = models.DateField(null=True, blank=True)
    legal_case_no = models.CharField(max_length=100, blank=True)
    legal_advisor = models.CharField(max_length=200, blank=True)
    judgment_no = models.CharField(max_length=100, blank=True)
    judgement_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    lawyer_fee = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    next_hearing = models.DateField(null=True, blank=True)
    legal_status = models.CharField(max_length=100, default=DEFAULT_STATUS)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='legal_cases_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Legal — {self.case}"

    @property
    def lawyer_display(self):
        """Lawyer name from the FK if set, else the legacy free-text name."""
        if self.lawyer_id:
            return self.lawyer.name
        return self.lawyer_name or ''

    @property
    def status_label(self):
        """Friendly status text — maps any leftover legacy key to its label,
        otherwise shows the stored status name as-is."""
        return self.LEGACY_STATUS_LABELS.get(self.legal_status, self.legal_status) or '—'

    @property
    def status_color(self):
        """Colour from the matching settings status, if any (for badges)."""
        s = LegalCaseStatus.objects.filter(name=self.status_label).first()
        return s.color if s and s.color else ''

    @property
    def total_fees(self):
        return sum((f.amount for f in self.fees.all()), Decimal('0'))


class LegalFee(models.Model):
    legal_case = models.ForeignKey(LegalCase, on_delete=models.CASCADE, related_name='fees')
    fee_type   = models.ForeignKey('LegalFeeType', on_delete=models.SET_NULL, null=True, blank=True, related_name='fees')
    fee_date   = models.DateField()
    amount     = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    notes      = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='legal_fees_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fee_date', '-created_at']

    def __str__(self):
        return f"{self.fee_type} — {self.amount}"


class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('cheque', 'Cheque'),
        ('bank_transfer', 'Bank Transfer'),
        ('online', 'Online Payment'),
        ('other', 'Other'),
        ('direct', 'Direct'),
        ('check', 'Check'),
        ('promise', 'Promise'),
    ]

    # Method options offered when creating/editing an installment
    INSTALLMENT_METHOD_CHOICES = [
        ('direct', 'Direct'),
        ('check', 'Check'),
        ('promise', 'Promise'),
    ]

    # Keys are legacy ('cleared'/'bounced'); labels follow the Collection
    # Confirmation workflow: admin approves or rejects a pending payment.
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('cleared', 'Approved'),
        ('bounced', 'Rejected'),
    ]

    payment_id          = models.CharField(max_length=60, unique=True, blank=True)
    case                = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='payments')
    payment_mode        = models.ForeignKey('PaymentMode', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    payment_date        = models.DateField()
    collection_currency = models.ForeignKey('Currency', on_delete=models.SET_NULL, null=True, blank=True, related_name='collection_payments')
    amount              = models.DecimalField(max_digits=12, decimal_places=3)
    transfer_date       = models.DateField(null=True, blank=True)
    received_date       = models.DateField(null=True, blank=True)
    received_currency   = models.ForeignKey('Currency', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_payments')
    received_amount     = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    confirmation_date   = models.DateField(null=True, blank=True)
    payment_method      = models.CharField(max_length=20, choices=METHOD_CHOICES, default='bank_transfer')
    reference_number    = models.CharField(max_length=100, blank=True)
    cheque_number       = models.CharField(max_length=100, blank=True)
    bank_name           = models.CharField(max_length=100, blank=True)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_installment      = models.BooleanField(default=False)
    # When an installment was marked Done from Reminders → Payments. Cleared
    # installments stay listed there (as "Completed") for 14 days, then quietly
    # drop off — the Payment row itself is never deleted.
    completed_at        = models.DateTimeField(null=True, blank=True)
    notes               = models.TextField(blank=True)
    created_by          = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_created')
    created_at          = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.payment_id:
            import re
            from django.utils import timezone
            now = timezone.now()
            # Use max existing sequence + 1, not count()+1 — after a deletion
            # the count can point at a number that is still taken.
            max_seq = 0
            for pid in Payment.objects.values_list('payment_id', flat=True):
                m = re.search(r'(\d+)$', pid or '')
                if m:
                    max_seq = max(max_seq, int(m.group(1)))
            self.payment_id = f"TWZ/PAY/{now.year}/{max_seq + 1:04d}"
        super().save(*args, **kwargs)

    # Payment modes whose payments get a downloadable receipt (money came
    # into Tawazon; client-side payments have no Tawazon receipt).
    RECEIPT_MODES = ('Cash in Tawazon', 'Transfer to Tawazon', 'Cheque to Tawazon')

    @property
    def receipt_no(self):
        return (self.payment_id or '').replace('/PAY/', '/RPT/')

    @property
    def can_download_receipt(self):
        return bool(self.payment_mode and self.payment_mode.name in self.RECEIPT_MODES)

    def __str__(self):
        return f"{self.payment_id} — {self.amount} OMR"

# ── Permission catalog ──────────────────────────────────────────────────────
# Single source of truth for the permission matrix used by User Groups and
# per-user overrides. Keys are stored in JSON fields; labels drive the UI.
PERMISSION_ACTIONS = ['view', 'add', 'edit', 'delete', 'print']
PERMISSION_MODULES = [
    ('clients',     'Clients'),
    ('debtors',     'Debtors'),
    ('cases',       'Cases'),
    ('legal_cases', 'Legal Cases'),
    ('payments',    'Payments'),
    ('follow_ups',  'Follow Ups'),
    ('reports',     'Reports'),
    ('lawyers',     'Lawyers'),
    ('agencies',    'Agencies'),
    ('users',       'Users'),
    ('settings',    'Settings'),
]


def full_permissions():
    """Every module with every action — the seed for admin-like groups."""
    return {key: list(PERMISSION_ACTIONS) for key, _ in PERMISSION_MODULES}


def _clean_perm_map(raw):
    """Keep only known modules/actions from a client-supplied permission map."""
    valid_modules = {key for key, _ in PERMISSION_MODULES}
    out = {}
    for module, actions in (raw or {}).items():
        if module in valid_modules and isinstance(actions, list):
            keep = [a for a in PERMISSION_ACTIONS if a in actions]
            if keep:
                out[module] = keep
    return out


class UserGroup(models.Model):
    name       = models.CharField(max_length=60, unique=True)
    is_enabled = models.BooleanField(default=True)
    # Members of an admin group are made Django superusers (the app's
    # is_superuser checks are what actually grant admin UI/actions).
    is_admin   = models.BooleanField(default=False)
    # {"cases": ["view", "add"], ...} — the baseline every member inherits.
    permissions = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    # user.email is the company email and `phone` the company phone; the
    # personal contact details live here alongside them.
    phone      = models.CharField(max_length=30, blank=True)
    personal_email = models.EmailField(blank=True)
    personal_phone = models.CharField(max_length=30, blank=True)
    id_number  = models.CharField(max_length=50, blank=True)
    address    = models.CharField(max_length=300, blank=True)
    notes      = models.TextField(blank=True)
    user_group = models.ForeignKey(UserGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    is_enabled = models.BooleanField(default=True)
    # Per-user tuning on top of the group baseline: grants add permissions the
    # group doesn't have, revokes remove ones it does. Effective permissions =
    # (group ∪ grants) − revokes, so two staff in one group can still differ.
    perm_grants  = models.JSONField(default=dict, blank=True)
    perm_revokes = models.JSONField(default=dict, blank=True)
    allowed_ips = models.CharField(
        max_length=255, blank=True,
        help_text="Comma-separated IP addresses this user may log in from. Leave blank to allow any IP.",
    )

    def allowed_ip_list(self):
        return [ip.strip() for ip in self.allowed_ips.split(',') if ip.strip()]

    def group_permissions(self):
        if self.user_group and self.user_group.is_enabled:
            return {m: list(a) for m, a in (self.user_group.permissions or {}).items()}
        return {}

    def effective_permissions(self):
        """{module: [actions]} after applying this user's grants and revokes."""
        eff = {m: set(a) for m, a in self.group_permissions().items()}
        for m, actions in (self.perm_grants or {}).items():
            eff.setdefault(m, set()).update(actions)
        for m, actions in (self.perm_revokes or {}).items():
            if m in eff:
                eff[m] -= set(actions)
        return {m: [a for a in PERMISSION_ACTIONS if a in acts] for m, acts in eff.items() if acts}

    def set_effective_permissions(self, desired):
        """Store the diff between the desired effective matrix and the group
        baseline as this user's grants/revokes."""
        desired = _clean_perm_map(desired)
        base = self.group_permissions()
        grants, revokes = {}, {}
        modules = {key for key, _ in PERMISSION_MODULES}
        for m in modules:
            want = set(desired.get(m, []))
            have = set(base.get(m, []))
            extra = want - have
            missing = have - want
            if extra:
                grants[m] = [a for a in PERMISSION_ACTIONS if a in extra]
            if missing:
                revokes[m] = [a for a in PERMISSION_ACTIONS if a in missing]
        self.perm_grants = grants
        self.perm_revokes = revokes

    def __str__(self):
        return f"{self.user.username} profile"


def user_has_perm(user, module, action):
    """App-level permission check. Superusers can do everything; everyone
    else needs the action on the module via group + per-user overrides."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    if profile is None:
        return False
    return action in profile.effective_permissions().get(module, [])


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    # raw=True means this save came from loaddata (a fixture, e.g. restoring
    # a Backup & Export database dump) — skip it there. Without this check,
    # restoring a backup double-creates the profile: this signal makes one
    # via get_or_create, then the dump's own core.userprofile row for that
    # same user fails to load with a UNIQUE constraint on user_id.
    if created and not kwargs.get('raw'):
        UserProfile.objects.get_or_create(user=instance)


class Country(models.Model):
    name         = models.CharField(max_length=100, unique=True)
    code         = models.CharField(max_length=3, blank=True)   # ISO 2-letter
    country_code = models.CharField(max_length=10, blank=True)  # dial code e.g. +968
    is_enabled   = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class State(models.Model):
    name       = models.CharField(max_length=100)
    country    = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='states', null=True, blank=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [('name', 'country')]

    def __str__(self):
        return self.name


class Currency(models.Model):
    name         = models.CharField(max_length=100, unique=True)
    code         = models.CharField(max_length=10)
    symbol_left  = models.CharField(max_length=10, blank=True)
    symbol_right = models.CharField(max_length=10, blank=True)
    value        = models.DecimalField(max_digits=14, decimal_places=5, default=1)
    is_enabled   = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class CaseType(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class CaseStatus(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    color      = models.CharField(max_length=7, blank=True)   # hex e.g. #f51418
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Case Statuses'

    def __str__(self):
        return self.name


@receiver(post_save, sender=CaseStatus)
@receiver(post_delete, sender=CaseStatus)
def _clear_case_status_choices_cache(sender, **kwargs):
    global _status_choices_cache, _status_colors_cache
    _status_choices_cache = None
    _status_colors_cache = None


class LegalCaseStatus(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    color      = models.CharField(max_length=7, blank=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Legal Case Statuses'

    def __str__(self):
        return self.name


class LegalFeeType(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class FollowupType(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PaymentMode(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ClientType(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ContractType(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ContactType(models.Model):
    TYPE_CHOICES = [('client', 'Client'), ('debtor', 'Debtor')]

    name       = models.CharField(max_length=100)
    type       = models.CharField(max_length=10, choices=TYPE_CHOICES, default='client')
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [('name', 'type')]

    def __str__(self):
        return f"{self.name} ({self.type})"


class AttachmentType(models.Model):
    TYPE_CHOICES = [('client', 'Client'), ('debtor', 'Debtor'), ('case', 'Case')]

    name       = models.CharField(max_length=100, unique=True)
    # Comma-separated subset of TYPE_CHOICES keys, e.g. "client,case" — an
    # attachment type can apply to more than one context at once. Stored as
    # plain CSV rather than ArrayField so this keeps working on the SQLite
    # fallback used for local dev, not just Postgres.
    type       = models.CharField(max_length=30, default='case')
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_type_list(self):
        """['client', 'case'] from the stored 'client,case' — in
        TYPE_CHOICES order, ignoring anything stale/unrecognised so a
        since-removed choice can't blow up the badges/checkboxes."""
        valid = {key for key, _ in self.TYPE_CHOICES}
        stored = {t.strip() for t in (self.type or '').split(',') if t.strip()}
        return [key for key, _ in self.TYPE_CHOICES if key in stored & valid]

    def get_type_display_list(self):
        labels = dict(self.TYPE_CHOICES)
        return [labels[key] for key in self.get_type_list()]

    def applies_to(self, context):
        return context in self.get_type_list()


class Agency(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]
    name         = models.CharField(max_length=200)
    organisation = models.CharField(max_length=200, blank=True)
    phone        = models.CharField(max_length=50, blank=True)
    email        = models.EmailField(blank=True)
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Agencies'

    def __str__(self):
        return self.name


class Lawyer(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]
    name       = models.CharField(max_length=200)
    phone      = models.CharField(max_length=50, blank=True)
    email      = models.EmailField(blank=True)
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ContactDirectory(models.Model):
    contact_name     = models.CharField(max_length=200)
    contact_type     = models.CharField(max_length=100, blank=True)
    email            = models.EmailField(blank=True)
    phone_number1    = models.CharField(max_length=30, blank=True)
    phone_number2    = models.CharField(max_length=30, blank=True)
    id_number        = models.CharField(max_length=100, blank=True)
    passport_number  = models.CharField(max_length=100, blank=True)
    nationality      = models.CharField(max_length=100, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['contact_name']

    def __str__(self):
        return self.contact_name


class ClientLoginAccess(models.Model):
    client            = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='login_accesses')
    email             = models.EmailField()
    password          = models.CharField(max_length=255)
    visible_date_from = models.DateField(null=True, blank=True)
    expires_on        = models.DateField(null=True, blank=True, help_text='Access auto-disables after this date. Blank = never.')
    is_enabled        = models.BooleanField(default=False)
    login_count       = models.PositiveIntegerField(default=0)
    last_login        = models.DateTimeField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_expired(self):
        from django.utils import timezone
        return self.expires_on is not None and timezone.now().date() > self.expires_on

    def __str__(self):
        return f'{self.client} — {self.email}'


class ClientLoginOTP(models.Model):
    """A one-time passcode emailed to a client for passwordless login."""
    access     = models.ForeignKey(ClientLoginAccess, on_delete=models.CASCADE, related_name='otps')
    code_hash  = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    is_used    = models.BooleanField(default=False)
    attempts   = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f'OTP for {self.access.email} ({"used" if self.is_used else "active"})'


class ClientLoginLog(models.Model):
    """One row per successful client portal login — for the login-history viewer."""
    access     = models.ForeignKey(ClientLoginAccess, on_delete=models.CASCADE, related_name='login_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.access.email} @ {self.created_at:%Y-%m-%d %H:%M}'


class ChatMessage(models.Model):
    """A per-case chat message between a client (portal) and the staff handling
    the case. A conversation is the (case, access) pair; the staff side is the
    case's collector (admins can see everything)."""
    SENDER_CLIENT = 'client'
    SENDER_STAFF  = 'staff'
    SENDER_CHOICES = [(SENDER_CLIENT, 'Client'), (SENDER_STAFF, 'Staff')]

    case       = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='chat_messages')
    access     = models.ForeignKey('ClientLoginAccess', on_delete=models.CASCADE, related_name='chat_messages')
    sender     = models.CharField(max_length=10, choices=SENDER_CHOICES)
    staff_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='chat_messages')
    body       = models.TextField()
    is_read    = models.BooleanField(default=False)   # read by the recipient
    is_edited  = models.BooleanField(default=False)
    is_auto    = models.BooleanField(default=False)   # system auto-reply
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['case', 'access', 'created_at']),
        ]

    def __str__(self):
        return f'{self.sender} @ {self.case} — {self.body[:30]}'


class ClientCaseAccess(models.Model):
    """Per-case visibility/permissions granted to a client login. A case is shown
    in the client portal only if a row exists here with at least one permission,
    and inside the case only the permitted sections are revealed."""
    access              = models.ForeignKey(ClientLoginAccess, on_delete=models.CASCADE, related_name='case_accesses')
    case                = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='client_accesses')
    can_status          = models.BooleanField(default=False)
    can_financial       = models.BooleanField(default=False)
    can_collector       = models.BooleanField(default=False)
    can_followup        = models.BooleanField(default=False)
    can_history         = models.BooleanField(default=False)
    can_payment_history = models.BooleanField(default=False)
    can_attachments     = models.BooleanField(default=False)
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('access', 'case')]

    @property
    def any_permission(self):
        return any([self.can_status, self.can_financial, self.can_collector,
                    self.can_followup, self.can_history, self.can_payment_history,
                    self.can_attachments])

    def __str__(self):
        return f'{self.access.email} → {self.case.case_id}'


class ActivityLog(models.Model):
    LOG_TYPE_CHOICES = [
        ('login',    'Login'),
        ('logout',   'Logout'),
        ('create',   'Create'),
        ('update',   'Update'),
        ('delete',   'Delete'),
        ('export',   'Export'),
        ('import',   'Import'),
        ('payment',  'Payment'),
        ('view',     'View'),
        ('security', 'Security'),
        ('other',    'Other'),
    ]

    user       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    log_type   = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES, default='other')
    action     = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.log_type} — {self.user} — {self.created_at:%Y-%m-%d %H:%M}'


class CaseAttachment(models.Model):
    case            = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='attachments')
    file            = models.FileField(upload_to='case_attachments/')
    filename        = models.CharField(max_length=255, blank=True)
    attachment_type = models.ForeignKey('AttachmentType', on_delete=models.SET_NULL, null=True, blank=True, related_name='case_attachments')
    description     = models.CharField(max_length=255, blank=True)
    uploaded_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='case_attachments')
    uploaded_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.filename} — {self.case}"


class CaseHistory(models.Model):
    case       = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='case_history')
    action_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='case_history_entries')
    action     = models.CharField(max_length=500)
    ip_address = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.case} — {self.action}"


class Reminder(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('completed', 'Completed')]

    case        = models.ForeignKey('Case', on_delete=models.CASCADE, related_name='reminders', null=True, blank=True)
    title       = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    reminder_date = models.DateField()
    other_users = models.ManyToManyField(User, blank=True, related_name='shared_reminders')
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # When it was marked done. Completed reminders stay visible for 14 days
    # and are then purged (see views._purge_completed_reminders).
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reminders_created')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['reminder_date']

    def __str__(self):
        return f'{self.title} — {self.reminder_date}'


class Todo(models.Model):
    title    = models.CharField(max_length=200)
    remarks  = models.TextField(blank=True)
    date     = models.DateField(null=True, blank=True)
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='todos')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class DebtorStatusOption(models.Model):
    TYPE_CHOICES = [
        ('individual', 'Individual'),
        ('organization', 'Organization'),
    ]

    name        = models.CharField(max_length=100)
    debtor_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    is_enabled  = models.BooleanField(default=True)
    order       = models.IntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['debtor_type', 'order', 'name']
        unique_together = [('name', 'debtor_type')]

    def __str__(self):
        return f"{self.name} ({self.debtor_type})"


class DebtorRelatedCompany(models.Model):
    RELATION_CHOICES = [
        ('parent', 'Parent Company'),
        ('sister', 'Sister Company'),
        ('subsidiary', 'Subsidiary'),
        ('other', 'Other'),
    ]
    debtor        = models.ForeignKey(Debtor, on_delete=models.CASCADE, related_name='related_companies')
    name          = models.CharField(max_length=200)
    relation_type = models.CharField(max_length=20, choices=RELATION_CHOICES, default='sister')
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['relation_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.relation_type})"


class AttendanceSession(models.Model):
    """One working session per staff login. `login_at` is set when the user
    signs in, `last_activity` is bumped by a periodic heartbeat while the tab
    is active, and `logout_at` is set when the session ends. Worked hours are
    measured up to the LAST detected activity, so idle/abandoned time after a
    staff member walks away is never counted as work."""

    LOGOUT_MANUAL   = 'manual'
    LOGOUT_IDLE     = 'auto_idle'
    LOGOUT_RELOGIN  = 'relogin'
    LOGOUT_TYPE_CHOICES = [
        (LOGOUT_MANUAL,  'Manual logout'),
        (LOGOUT_IDLE,    'Auto logout (idle)'),
        (LOGOUT_RELOGIN, 'Closed on new login'),
    ]

    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_sessions')
    login_at      = models.DateTimeField(default=timezone.now)
    last_activity = models.DateTimeField(default=timezone.now)
    logout_at     = models.DateTimeField(null=True, blank=True)
    logout_type   = models.CharField(max_length=20, choices=LOGOUT_TYPE_CHOICES, null=True, blank=True)
    ip_address    = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['-login_at']
        indexes = [
            models.Index(fields=['user', 'login_at']),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.login_at:%Y-%m-%d %H:%M}"

    @property
    def is_open(self):
        return self.logout_at is None

    @property
    def effective_end(self):
        """The moment work is counted up to: the real logout time for closed
        sessions, otherwise the last detected activity (never `now`, so an
        abandoned open tab stops accruing hours)."""
        return self.logout_at or self.last_activity

    @property
    def duration(self):
        """Worked time for this session as a timedelta (never negative)."""
        delta = self.effective_end - self.login_at
        return delta if delta.total_seconds() > 0 else timedelta(0)

    def close(self, logout_type=LOGOUT_MANUAL, when=None):
        """End the session. Caps logout time at last_activity for idle/relogin
        closes so post-activity idle time is not paid; a manual logout counts
        right up to the click."""
        if not self.is_open:
            return
        now = when or timezone.now()
        if logout_type == self.LOGOUT_MANUAL:
            self.logout_at = now
            if now > self.last_activity:
                self.last_activity = now
        else:
            # idle / relogin: don't count time after the user went quiet
            self.logout_at = self.last_activity
        self.logout_type = logout_type
        self.save(update_fields=['logout_at', 'logout_type', 'last_activity'])
