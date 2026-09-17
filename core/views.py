import csv
import io
import json
import os
import re
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models import Sum, Count, Q, Max, Prefetch
from django.db.models.functions import Lower
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from django.core.validators import validate_email as django_validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.cache import cache
from .models import Client, ClientContact, Debtor, DebtorContact, Case, Payment, FollowUp, CaseGroup, LegalCase, UserProfile, UserGroup, Country, State, Currency, CaseType, CaseStatus, LegalCaseStatus, LegalFeeType, FollowupType, PaymentMode, ClientType, ContractType, ContactType, AttachmentType, Agency, Lawyer, ContactDirectory, ActivityLog, ClientLoginAccess, ClientLoginOTP, ClientCaseAccess, ClientLoginLog, Reminder, Todo, DebtorStatusOption, DebtorRelatedCompany, CaseAttachment, CaseHistory, AttendanceSession, LegalFee, ChatMessage, PERMISSION_MODULES, PERMISSION_ACTIONS, _clean_perm_map, user_has_perm, case_status_color_map
from .forms import ClientForm, ClientContactForm
from .currencies import enabled_currencies


from functools import wraps
from django.utils import timezone
from django.conf import settings
from datetime import timedelta, datetime, time as dtime


def admin_required(view):
    """Allow only superusers (admins). Non-admins get a 403 on POST/AJAX or a
    redirect to the dashboard on a normal page request."""
    @wraps(view)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            if request.method == 'POST':
                return JsonResponse(
                    {'success': False, 'error': 'Permission denied. Client Access is restricted to administrators.'},
                    status=403,
                )
            messages.error(request, 'Client Access is restricted to administrators.')
            return redirect('dashboard')
        return view(request, *args, **kwargs)
    return _wrapped


def perm_required(module, action):
    """Enforce an app-level permission (see models.PERMISSION_MODULES).
    Superusers always pass; others need the action via their group and
    per-user overrides."""
    def deco(view):
        @wraps(view)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not user_has_perm(request.user, module, action):
                if request.method == 'POST':
                    return JsonResponse(
                        {'success': False, 'ok': False,
                         'message': 'Permission denied.', 'error': 'Permission denied.'},
                        status=403,
                    )
                messages.error(request, 'You do not have permission for that action.')
                return redirect('dashboard')
            return view(request, *args, **kwargs)
        return _wrapped
    return deco


def _scope_cases_to_staff(request, qs):
    """Reports for non-admin staff only ever cover their own assigned cases."""
    if request.user.is_superuser:
        return qs
    return qs.filter(collector=request.user)


def _scope_payments_to_staff(request, qs):
    """Payment-based reports for non-admin staff cover only payments on their
    own assigned cases."""
    if request.user.is_superuser:
        return qs
    return qs.filter(case__collector=request.user)


def _log_case(request, case, action):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '') or request.META.get('REMOTE_ADDR', '')
    if ',' in ip:
        ip = ip.split(',')[0].strip()
    CaseHistory.objects.create(
        case=case,
        action_by=request.user if request.user.is_authenticated else None,
        action=action,
        ip_address=ip[:50],
    )


# A new case is fully visible right away to every client-portal login the
# owning client has, instead of staying hidden until someone remembers to
# grant it manually from Settings → Client Portal Access.
_CLIENT_ACCESS_FULL_GRANT = {
    'can_status': True, 'can_financial': True, 'can_collector': True,
    'can_followup': True, 'can_history': True, 'can_payment_history': True,
    'can_attachments': True,
}


def _grant_full_client_case_access(case):
    for acc in ClientLoginAccess.objects.filter(client_id=case.client_id):
        ClientCaseAccess.objects.update_or_create(
            access=acc, case=case, defaults=_CLIENT_ACCESS_FULL_GRANT,
        )


# ---------- ATTENDANCE HELPERS ----------
def _client_ip(request):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '') or request.META.get('REMOTE_ADDR', '')
    if ',' in ip:
        ip = ip.split(',')[0].strip()
    return ip[:50]


def _secure_client_ip(request):
    """The real visitor IP for this request, for use in the staff IP-allowlist
    security check and other security-sensitive log entries.

    This app is only ever reached through the platform's edge proxy (Railway)
    — it has no public IP of its own — so that edge is a trusted single hop
    that sets X-Forwarded-For to the real client IP on every request. Trusting
    only REMOTE_ADDR here would be wrong in this deployment: it's the proxy's
    own (internal, and not necessarily stable) address, not the visitor's, so
    two tabs on the same machine could log different "IPs" and the allowlist
    check would never see a real employee IP. Same logic as _client_ip(); kept
    as a separate name since the two serve different purposes.
    """
    return _client_ip(request)


def _format_hours(td):
    """Render a timedelta for display. Shows seconds for sub-minute spans (so a
    brief session reads '12s' instead of a confusing '0h 00m'), minutes under an
    hour, otherwise 'Hh Mm' (e.g. '6h 32m')."""
    total = int(max(td.total_seconds(), 0))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    h, m = total // 3600, (total % 3600) // 60
    return f"{h}h {m:02d}m"


def _hours_today(user, ref=None):
    """Sum of worked time for `user` across all sessions that started today
    (local time). Returns a timedelta. Counts up to last activity per session."""
    now = ref or timezone.now()
    local_now = timezone.localtime(now)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = start_local
    total = timedelta(0)
    for s in AttendanceSession.objects.filter(user=user, login_at__gte=start):
        total += s.duration
    return total


def _motivation_for(td):
    """An appreciation line scaled to time worked today."""
    mins = td.total_seconds() / 60.0
    if mins >= 9 * 60:
        return "Incredible commitment today — that's a full, powerful day. Go rest, you earned it! 🏆"
    if mins >= 8 * 60:
        return "Outstanding dedication today — you went above and beyond. The team is lucky to have you! 🌟"
    if mins >= 6 * 60:
        return "Fantastic work today! Your consistency and focus really show. 💪"
    if mins >= 4 * 60:
        return "Solid effort today — you kept the momentum going. Well done! 👍"
    if mins >= 2 * 60:
        return "Good job putting in the hours today. Every bit of effort moves us forward. 🙂"
    if mins >= 60:
        return "Nice, a focused hour-plus of work today. Keep that rhythm going! ✨"
    if mins >= 30:
        return "Good check-in today — every focused minute adds up. 🙂"
    if mins > 0:
        return "Short session today — thanks for stopping by, see you next time! 🌱"
    return "Have a great day ahead!"


def _close_open_sessions(user, logout_type):
    """Close any dangling open sessions for a user (e.g. on re-login)."""
    for s in AttendanceSession.objects.filter(user=user, logout_at__isnull=True):
        s.close(logout_type=logout_type)


# ---------- DASHBOARD ----------
@login_required
def dashboard(request):
    # This view runs ~10 aggregates plus full case/debtor scans. It's the same
    # for a given user until case data changes, so cache the computed context
    # for a short window (settings.DASHBOARD_CACHE_SECONDS) — staff won't notice
    # a slightly stale total, and it keeps the dashboard from re-hitting the DB
    # on every load even while client-portal traffic is coming in.
    is_admin = request.user.is_superuser
    cache_key = f'dashboard:v1:{request.user.pk}:{"admin" if is_admin else "staff"}'
    context = cache.get(cache_key)
    if context is None:
        context = _build_dashboard_context(request, is_admin)
        cache.set(cache_key, context, settings.DASHBOARD_CACHE_SECONDS)
    context = {**context, 'active_page': 'dashboard'}
    return render(request, 'dashboard.html', context)


def _build_dashboard_context(request, is_admin):
    # Staff only see data tied to cases they collect; admins see everything.
    case_q = Q() if is_admin else Q(collector=request.user)
    case_count_filter = None if is_admin else Q(cases__collector=request.user)

    active_cases = Case.objects.filter(case_q).exclude(status='closed').exclude(status='closed_by_client')

    total_active_cases = active_cases.count()
    total_approved = active_cases.aggregate(total=Sum('approved_amount'))['total'] or 0
    total_received = active_cases.aggregate(total=Sum('received_amount'))['total'] or 0
    total_remaining = total_approved - total_received

    if is_admin:
        total_debtors = Debtor.objects.count()
        total_clients = Client.objects.count()
    else:
        total_debtors = Debtor.objects.filter(cases__collector=request.user).distinct().count()
        total_clients = Client.objects.filter(cases__collector=request.user).distinct().count()

    # ----- SUMMARY TAB: Case Status -----
    status_data = (
        Case.objects.filter(case_q).values('status')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('status')
    )
    status_labels_map = dict(Case.all_status_choices())
    chart_labels = [status_labels_map.get(item['status'], item['status']) for item in status_data]
    chart_values = [item['count'] for item in status_data]

    status_table = []
    total_count = 0
    total_approved_sum = 0
    total_received_sum = 0
    for item in status_data:
        approved = item['approved'] or 0
        received = item['received'] or 0
        status_table.append({
            'label': status_labels_map.get(item['status'], item['status']),
            'count': item['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })
        total_count += item['count']
        total_approved_sum += approved
        total_received_sum += received

    # ----- DEBTORS TAB: per-debtor stats (staff: only their own cases for that debtor) -----
    debtor_rows = []
    debtors_total = {'count': 0, 'approved': 0, 'received': 0, 'remaining': 0}
    debtor_qs = Debtor.objects.annotate(
        case_count=Count('cases', filter=case_count_filter, distinct=True),
        approved=Sum('cases__approved_amount', filter=case_count_filter),
        received=Sum('cases__received_amount', filter=case_count_filter),
    ).order_by('name')
    if not is_admin:
        debtor_qs = debtor_qs.filter(case_count__gt=0)
    for d in debtor_qs:
        approved = d.approved or 0
        received = d.received or 0
        debtor_rows.append({
            'id': f"TWZ/D{d.id:04d}",
            'name': d.name,
            'count': d.case_count,
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })
        debtors_total['count'] += d.case_count
        debtors_total['approved'] += approved
        debtors_total['received'] += received
    debtors_total['remaining'] = debtors_total['approved'] - debtors_total['received']

    # ----- CLIENTS TAB: pie chart per client (staff: only their own cases for that client) -----
    client_data = Client.objects.annotate(
        case_count=Count('cases', filter=case_count_filter, distinct=True)
    ).filter(case_count__gt=0).order_by('name')
    clients_chart_labels = [c.name for c in client_data]
    clients_chart_values = [c.case_count for c in client_data]
    clients_chart_data = list(zip(clients_chart_labels, clients_chart_values))
    clients_chart_total = sum(clients_chart_values)

    # ----- CASES TAB: full list -----
    cases_rows = []
    cases_total_outstanding = 0
    for case in Case.objects.filter(case_q).select_related('client', 'debtor', 'collector').order_by('client__name', 'case_id'):
        cases_rows.append({
            'id': case.case_id,
            'client': case.client.name,
            'debtor': case.debtor.name,
            'agency': '—',
            'outstanding': case.remaining_amount,
            'collector': (case.collector.get_full_name() or case.collector.username) if case.collector else '—',
            'status': case.status,
            'status_label': case.get_status_display(),
        })
        cases_total_outstanding += case.remaining_amount or 0

    return {
        'total_active_cases': total_active_cases,
        'total_approved': total_approved,
        'total_received': total_received,
        'total_remaining': total_remaining,
        'total_debtors': total_debtors,
        'total_clients': total_clients,
        # Summary tab
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'status_table': status_table,
        'table_totals': {
            'count': total_count,
            'approved': total_approved_sum,
            'received': total_received_sum,
            'remaining': total_approved_sum - total_received_sum,
        },
        # Debtors tab
        'debtor_rows': debtor_rows,
        'debtors_total': debtors_total,
        # Clients tab
        'clients_chart_labels': clients_chart_labels,
        'clients_chart_values': clients_chart_values,
        'clients_chart_data': clients_chart_data,
        'clients_chart_total': clients_chart_total,
        # Cases tab
        'cases_rows': cases_rows,
        'cases_total_outstanding': cases_total_outstanding,
    }


# ---------- CLIENTS ----------
@login_required
def clients(request):
    from django.core.paginator import Paginator
    is_admin = request.user.is_superuser
    case_count_filter = None if is_admin else Q(cases__collector=request.user)
    filter_q = request.GET.get('filter', '')
    qs = Client.objects.annotate(total_cases=Count('cases', filter=case_count_filter, distinct=True)).order_by('-created_at')

    # Staff only see clients they have at least one case with; admins see everyone.
    if not is_admin:
        qs = qs.filter(total_cases__gt=0)

    if filter_q:
        qs = qs.filter(
            Q(name__icontains=filter_q) |
            Q(client_id__icontains=filter_q) |
            Q(email__icontains=filter_q)
        )

    total_count = qs.count()
    page_size_options = [10, 50, 100, 'All']
    show = request.GET.get('show', '10')
    page_size = total_count or 1 if show == 'All' else int(show) if show.isdigit() else 10

    paginator  = Paginator(qs, page_size)
    page_obj   = paginator.get_page(request.GET.get('page', 1))
    params     = request.GET.copy(); params.pop('page', None)
    query_string = params.urlencode()

    if is_admin:
        total_cases_sum = Case.objects.filter(client__in=qs).count()
    else:
        total_cases_sum = Case.objects.filter(client__in=qs, collector=request.user).count()

    return render(request, 'clients.html', {
        'active_page': 'clients',
        'active_sub': 'all_clients',
        'clients': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'total_cases_sum': total_cases_sum,
        'filter_q': filter_q,
        'query_string': query_string,
        'page_size': show,
        'page_size_options': page_size_options,
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
    })


def _sync_client_primary_contact(client):
    """Auto-create a primary ClientContact from the client's own phone/email if no contacts exist."""
    if client.contacts.exists():
        return
    phone = client.phone or client.mobile or ''
    email = client.email or ''
    name  = client.contact_person or client.name
    if phone or email:
        ClientContact.objects.get_or_create(
            client=client,
            name=name,
            defaults={'contact_type': 'other', 'phone': phone, 'email': email, 'enabled': True},
        )


def _sync_debtor_primary_contact(debtor):
    """Auto-create a primary DebtorContact from the debtor's own phone/email if no contacts exist."""
    if debtor.contacts.exists():
        return
    phone = debtor.phone or debtor.telephone or ''
    email = debtor.email or ''
    if phone or email:
        DebtorContact.objects.get_or_create(
            debtor=debtor,
            name=debtor.name,
            defaults={'contact_type': 'other', 'phone': phone, 'email': email, 'enabled': True},
        )


def _split_phone_code(value, country_codes):
    """Split a stored '+968 12345678'-style value into (code, number) so an edit form
    can prefill a country-code select without duplicating the code on save."""
    value = (value or '').strip()
    if not value:
        return '', ''
    for code in country_codes:
        if code and value.startswith(code):
            return code, value[len(code):].strip()
    return '', value


def _valid_email(value):
    """True if value is empty or a well-formed email address."""
    if not value:
        return True
    try:
        django_validate_email(value)
        return True
    except DjangoValidationError:
        return False


def _valid_phone(value):
    """True if value is empty or a '+<code> <digits>'-style phone (6-14 digits)."""
    if not value:
        return True
    return bool(re.fullmatch(r'\+\d{1,4}\s?\d{6,14}', value))


def _valid_ip_list(value):
    """True if value is empty or a comma-separated list of valid IP addresses."""
    import ipaddress
    if not value:
        return True
    for part in value.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            ipaddress.ip_address(part)
        except ValueError:
            return False
    return True


@admin_required
def client_add(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            if request.user.is_authenticated:
                client.created_by = request.user
            client.save()
            _sync_client_primary_contact(client)
            messages.success(request, f'Client "{client.name}" created successfully.')
            next_url = request.GET.get('next', '')
            return redirect(next_url if next_url else 'clients')
    else:
        form = ClientForm()

    return render(request, 'client_form.html', {
        'active_page': 'clients',
        'active_sub': 'all_clients',
        'form': form,
        'title': 'Add New Client',
        'submit_label': 'Create Client',
    })


def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            _sync_client_primary_contact(client)
            messages.success(request, f'Client "{client.name}" updated successfully.')
            return redirect('clients')
    else:
        form = ClientForm(instance=client)

    return render(request, 'client_form.html', {
        'active_page': 'clients',
        'active_sub': 'all_clients',
        'form': form,
        'title': f'Edit Client — {client.name}',
        'submit_label': 'Save Changes',
        'client': client,
    })


def client_detail_json(request, pk):
    client = get_object_or_404(Client, pk=pk)
    contacts = [
        {
            'id': c.pk,
            'name': c.name,
            'contact_type': c.get_contact_type_display(),
            'contact_type_raw': c.contact_type,
            'email': c.email or '',
            'phone': c.phone or '',
        }
        for c in client.contacts.filter(enabled=True).order_by('name')
    ]
    return JsonResponse({
        'id': client.pk,
        'client_id': client.client_id or '',
        'name': client.name,
        'alias_name': client.alias_name or '',
        'email': client.email or '',
        'phone': client.phone or '',
        'mobile': client.mobile or '',
        'contact_person': client.contact_person or '',
        'client_type': client.get_client_type_display(),
        'client_type_raw': client.client_type,
        'contract_type': client.get_contract_type_display() if client.contract_type else '',
        'contract_type_raw': client.contract_type or '',
        'country': client.country or '',
        'address': client.address or '',
        'address2': client.address2 or '',
        'google_location': client.google_location or '',
        'notes': client.notes or '',
        'status': client.get_status_display(),
        'status_class': client.status,
        'status_raw': client.status,
        'contacts': contacts,
    })


@admin_required
@require_POST
def client_update_ajax(request, pk):
    client = get_object_or_404(Client, pk=pk)
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Client name is required.'})
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    mobile = request.POST.get('mobile', '').strip()
    if not _valid_email(email):
        return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'})
    if not _valid_phone(phone) or not _valid_phone(mobile):
        return JsonResponse({'success': False, 'message': 'Please enter a valid phone number (country code + number).'})
    client.name = name
    client.alias_name = request.POST.get('alias_name', '').strip()
    client.email = email
    client.phone = phone
    client.mobile = mobile
    client.contact_person = request.POST.get('contact_person', '').strip()
    client.client_type = request.POST.get('client_type', 'corporate')
    client.contract_type = request.POST.get('contract_type', '')
    client.status = request.POST.get('status', 'active')
    client.country = request.POST.get('country', '').strip()
    client.address = request.POST.get('address', '').strip()
    client.address2 = request.POST.get('address2', '').strip()
    client.google_location = request.POST.get('google_location', '').strip()
    client.notes = request.POST.get('notes', '').strip()
    client.save()
    return JsonResponse({'success': True, 'message': f'Client "{client.name}" updated successfully.'})


@require_POST
def client_toggle_status(request):
    pk = request.POST.get('id', '').strip()
    client = get_object_or_404(Client, pk=pk)
    client.status = 'inactive' if client.status == 'active' else 'active'
    client.save(update_fields=['status'])
    return JsonResponse({'success': True, 'status': client.status, 'message': f'Client "{client.name}" {client.get_status_display()}.'})


@admin_required
@require_POST
def client_create_modal(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Client name is required.'})
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    mobile = request.POST.get('mobile', '').strip()
    if not _valid_email(email):
        return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'})
    if not _valid_phone(phone) or not _valid_phone(mobile):
        return JsonResponse({'success': False, 'message': 'Please enter a valid phone number (country code + number).'})

    client = Client(
        name=name,
        alias_name=request.POST.get('alias_name', '').strip(),
        email=email,
        phone=phone,
        mobile=mobile,
        contact_person=request.POST.get('contact_person', '').strip(),
        client_type=request.POST.get('client_type', 'corporate'),
        contract_type=request.POST.get('contract_type', ''),
        country=request.POST.get('country', 'Oman').strip() or 'Oman',
        address=request.POST.get('address', '').strip(),
        address2=request.POST.get('address2', '').strip(),
        city=request.POST.get('city', '').strip(),
        state=request.POST.get('state', '').strip(),
        po_box=request.POST.get('po_box', '').strip(),
        google_location=request.POST.get('google_location', '').strip(),
        notes=request.POST.get('notes', '').strip(),
        status=request.POST.get('status', 'active'),
    )
    if request.user.is_authenticated:
        client.created_by = request.user
    client.save()

    # Support multiple contacts: contact_name[], contact_type[], contact_email[], contact_phone[]
    contact_names = request.POST.getlist('contact_name[]') or ([request.POST.get('contact_name', '').strip()] if request.POST.get('contact_name') else [])
    contact_types = request.POST.getlist('contact_type[]') or [request.POST.get('contact_type', 'other')]
    contact_emails = request.POST.getlist('contact_email[]') or [request.POST.get('contact_email', '').strip()]
    contact_phones = request.POST.getlist('contact_phone[]') or [request.POST.get('contact_phone', '').strip()]
    for i, cname in enumerate(contact_names):
        cname = cname.strip()
        if cname:
            ClientContact.objects.create(
                client=client,
                name=cname,
                contact_type=contact_types[i] if i < len(contact_types) else 'other',
                email=contact_emails[i].strip() if i < len(contact_emails) else '',
                phone=contact_phones[i].strip() if i < len(contact_phones) else '',
            )

    return JsonResponse({
        'success': True,
        'id': client.pk,
        'name': client.name,
        'message': f'Client "{client.name}" ({client.client_id}) created successfully.',
    })


@admin_required
@require_POST
def client_delete(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'success': False, 'message': 'No clients selected.'})
    count = Client.objects.filter(id__in=ids).count()
    Client.objects.filter(id__in=ids).delete()
    return JsonResponse({'success': True, 'message': f'{count} client(s) deleted successfully.'})


@admin_required
@require_POST
def client_merge(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if len(ids) < 2:
        return JsonResponse({'success': False, 'message': 'Select at least 2 clients to merge.'})

    clients_qs = Client.objects.filter(id__in=ids).order_by('created_at')
    primary = clients_qs.first()
    others = clients_qs.exclude(pk=primary.pk)

    Case.objects.filter(client__in=others).update(client=primary)
    ClientContact.objects.filter(client__in=others).update(client=primary)

    deleted_count = others.count()
    others.delete()

    return JsonResponse({
        'success': True,
        'message': f'Merged {deleted_count} client(s) into "{primary.name}".'
    })


@admin_required
def client_export(request, format):
    qs = Client.objects.all().annotate(total_cases=Count('cases')).order_by('-created_at')
    headers = ['Client ID', 'Name', 'Phone', 'Email', 'Type', 'Country', 'Total Cases', 'Status', 'Created At']
    rows = [
        [
            c.client_id, c.name, c.phone, c.email,
            c.get_client_type_display(), c.country, c.total_cases,
            c.get_status_display(), c.created_at.strftime('%Y-%m-%d'),
        ]
        for c in qs
    ]

    if format == 'csv':
        return _export_csv('clients', headers, rows)
    if format == 'excel':
        return _export_excel('Clients', headers, rows)
    if format == 'pdf':
        return _export_pdf('Clients Report', headers, rows)
    return redirect('clients')


# ---------- CLIENT CONTACTS ----------
def client_contacts(request):
    contact_name = request.GET.get('contact_name', '')
    email = request.GET.get('email', '')
    client_id = request.GET.get('client', '')

    # Backfill: auto-create primary contacts for clients that have phone/email but no contacts yet
    for c in Client.objects.filter(contacts__isnull=True).filter(
        Q(phone__gt='') | Q(mobile__gt='') | Q(email__gt='')
    ):
        _sync_client_primary_contact(c)

    qs = ClientContact.objects.select_related('client').order_by(Lower('client__name'), Lower('name'))

    if contact_name:
        qs = qs.filter(name__icontains=contact_name)
    if email:
        qs = qs.filter(email__icontains=email)
    if client_id:
        qs = qs.filter(client_id=client_id)

    return render(request, 'client_contacts.html', {
        'active_page': 'clients',
        'active_sub': 'contacts',
        'contacts': qs,
        'all_clients': Client.objects.all().order_by('name'),
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
        'contact_name': contact_name,
        'email': email,
        'selected_client': client_id,
    })


@require_POST
def contact_create_modal(request):
    name = request.POST.get('name', '').strip()
    client_id = request.POST.get('client_id', '').strip()
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Contact name is required.'})
    if not client_id:
        return JsonResponse({'success': False, 'message': 'Please select a client.'})
    if email:
        try:
            django_validate_email(email)
        except DjangoValidationError:
            return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'})
    if phone and not re.fullmatch(r'\+\d{1,4}\s?\d{6,14}', phone):
        return JsonResponse({'success': False, 'message': 'Please enter a valid phone number (country code + number).'})
    try:
        client = Client.objects.get(pk=client_id)
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Client not found.'})
    contact = ClientContact.objects.create(
        client=client,
        name=name,
        contact_type=request.POST.get('contact_type', 'other'),
        phone=phone,
        email=email,
    )
    return JsonResponse({
        'success': True,
        'message': f'Contact "{contact.name}" added to {client.name}.',
        'contact': {
            'id': contact.pk,
            'name': contact.name,
            'contact_type': contact.get_contact_type_display(),
            'email': contact.email,
            'phone': contact.phone,
        }
    })


def contact_add(request):
    if request.method == 'POST':
        form = ClientContactForm(request.POST)
        if form.is_valid():
            contact = form.save()
            messages.success(request, f'Contact "{contact.name}" created successfully.')
            return redirect('client_contacts')
    else:
        form = ClientContactForm()

    return render(request, 'contact_form.html', {
        'active_page': 'clients',
        'active_sub': 'contacts',
        'form': form,
        'title': 'Add New Contact',
        'submit_label': 'Create Contact',
    })


@admin_required
def contact_edit(request, pk):
    contact = get_object_or_404(ClientContact, pk=pk)
    if request.method == 'POST':
        form = ClientContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            messages.success(request, f'Contact "{contact.name}" updated successfully.')
            return redirect('client_contacts')
    else:
        form = ClientContactForm(instance=contact)

    return render(request, 'contact_form.html', {
        'active_page': 'clients',
        'active_sub': 'contacts',
        'form': form,
        'title': f'Edit Contact — {contact.name}',
        'submit_label': 'Save Changes',
        'contact': contact,
    })


@admin_required
@require_POST
def contact_delete(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'success': False, 'message': 'No contacts selected.'})
    count = ClientContact.objects.filter(id__in=ids).count()
    ClientContact.objects.filter(id__in=ids).delete()
    return JsonResponse({'success': True, 'message': f'{count} contact(s) deleted successfully.'})


@admin_required
def contact_export(request, format):
    qs = ClientContact.objects.select_related('client').order_by(Lower('client__name'), Lower('name'))
    headers = ['Contact Name', 'Contact Type', 'Client', 'Email', 'Phone', 'Enabled', 'Date Created']
    rows = [
        [
            c.name, c.get_contact_type_display(), c.client.name,
            c.email, c.phone,
            'Yes' if c.enabled else 'No',
            c.created_at.strftime('%d-%b-%Y'),
        ]
        for c in qs
    ]

    if format == 'csv':
        return _export_csv('contacts', headers, rows)
    if format == 'excel':
        return _export_excel('Client Contacts', headers, rows)
    if format == 'pdf':
        return _export_pdf('Client Contacts Report', headers, rows)
    return redirect('client_contacts')


# ---------- DEBTORS & CASES ----------
def debtors(request):
    from django.core.paginator import Paginator
    filter_q = request.GET.get('filter', '')
    qs = Debtor.objects.select_related('created_by', 'collector').annotate(
        total_cases=Count('cases')
    ).order_by('-created_at')

    if filter_q:
        qs = qs.filter(
            Q(name__icontains=filter_q) |
            Q(debtor_id__icontains=filter_q) |
            Q(email__icontains=filter_q) |
            Q(passport_cr_number__icontains=filter_q) |
            Q(id_number__icontains=filter_q)
        )

    total_count = qs.count()
    page_size_options = [10, 50, 100, 'All']
    show = request.GET.get('show', '10')
    page_size = total_count or 1 if show == 'All' else int(show) if show.isdigit() else 10

    paginator  = Paginator(qs, page_size)
    page_obj   = paginator.get_page(request.GET.get('page', 1))
    params     = request.GET.copy(); params.pop('page', None)
    query_string = params.urlencode()

    total_cases_sum = Case.objects.filter(debtor__in=qs).count()

    individual_statuses = list(DebtorStatusOption.objects.filter(debtor_type='individual', is_enabled=True).values('name', 'order'))
    org_statuses = list(DebtorStatusOption.objects.filter(debtor_type='organization', is_enabled=True).values('name', 'order'))
    return render(request, 'debtors.html', {
        'active_page': 'debtors',
        'active_sub': 'all_debtors',
        'debtors': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'total_cases_sum': total_cases_sum,
        'filter_q': filter_q,
        'query_string': query_string,
        'page_size': show,
        'page_size_options': page_size_options,
        'all_users': User.objects.filter(is_active=True).order_by('username'),
        'individual_statuses': individual_statuses,
        'org_statuses': org_statuses,
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
    })


def _normalize_debtor_status(raw):
    """Map the posted status name onto the canonical lowercase keys where it
    matches ('Active' → 'active'); richer settings-driven names pass through."""
    raw = (raw or '').strip()
    if raw.lower() in ('active', 'inactive'):
        return raw.lower()
    return raw or 'active'


@login_required
@require_POST
def debtor_create_modal(request):
    first_name = request.POST.get('first_name', '').strip()
    middle_name = request.POST.get('middle_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    name_parts = [p for p in [first_name, middle_name, last_name] if p]
    name = ' '.join(name_parts) if name_parts else request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'First name is required.'})

    contact_phones_raw = request.POST.getlist('contact_phone[]') or (
        [request.POST.get('contact_phone', '').strip()] if request.POST.get('contact_phone') else []
    )
    contact_phones_raw = [p.strip() for p in contact_phones_raw if p.strip()]
    employer_phones_raw = request.POST.getlist('employer_phone[]') or (
        [request.POST.get('employer_phone', '').strip()] if request.POST.get('employer_phone') else []
    )
    employer_phones_raw = [p.strip() for p in employer_phones_raw if p.strip()]
    if not all(_valid_phone(p) for p in [
        request.POST.get('phone', '').strip(),
        request.POST.get('telephone', '').strip(),
        *employer_phones_raw,
        *contact_phones_raw,
    ]):
        return JsonResponse({'success': False, 'message': 'Please enter a valid phone number (country code + number).'})
    if not all(_valid_email(e) for e in [
        request.POST.get('email', '').strip(),
        request.POST.get('email2', '').strip(),
        request.POST.get('employer_email', '').strip(),
        request.POST.get('contact_email', '').strip(),
    ]):
        return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'})

    dob_raw = request.POST.get('date_of_birth', '').strip()
    dob = None
    if dob_raw:
        try:
            from datetime import date
            dob = date.fromisoformat(dob_raw)
        except ValueError:
            pass

    debtor = Debtor(
        name=name,
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        is_organization=request.POST.get('is_organization') == '1',
        phone=request.POST.get('phone', '').strip(),
        telephone=request.POST.get('telephone', '').strip(),
        email=request.POST.get('email', '').strip(),
        email2=request.POST.get('email2', '').strip(),
        gender=request.POST.get('gender', '').strip(),
        date_of_birth=dob,
        nationality=request.POST.get('nationality', '').strip(),
        address_line1=request.POST.get('address_line1', '').strip(),
        address_line2=request.POST.get('address_line2', '').strip(),
        city=request.POST.get('city', '').strip(),
        country=request.POST.get('country', '').strip(),
        state=request.POST.get('state', '').strip(),
        passport_cr_number=request.POST.get('passport_cr_number', '').strip(),
        id_number=request.POST.get('id_number', '').strip(),
        cr_no=request.POST.get('cr_no', '').strip(),
        occi_no=request.POST.get('occi_no', '').strip(),
        vatin_no=request.POST.get('vatin_no', '').strip(),
        notes=request.POST.get('notes', '').strip(),
        employer_name=request.POST.get('employer_name', '').strip(),
        employer_phone=', '.join(employer_phones_raw),
        employer_email=request.POST.get('employer_email', '').strip(),
        employer_address=request.POST.get('employer_address', '').strip(),
        job_title=request.POST.get('job_title', '').strip(),
        # The wizard posts the Settings → Debtor Statuses display name (e.g.
        # "Active"); normalise the canonical keys so status='active' filters
        # (case dropdowns, reports) keep matching.
        status=_normalize_debtor_status(request.POST.get('status', 'active')),
    )
    if request.user.is_authenticated:
        debtor.created_by = request.user

    collector_id = request.POST.get('collector_id', '').strip()
    if collector_id:
        try:
            debtor.collector = User.objects.get(pk=collector_id)
        except User.DoesNotExist:
            pass

    debtor.save()

    contact_name = request.POST.get('contact_name', '').strip()
    contact_phones = request.POST.getlist('contact_phone[]')
    contact_types = request.POST.getlist('contact_type[]')
    # Per-number contact name (e.g. a sibling's number and a friend's number
    # belong to different people); falls back to the primary Contact Name
    # when a row's own name was left blank.
    contact_phone_names = request.POST.getlist('contact_phone_name[]')
    if not contact_phones and request.POST.get('contact_phone', '').strip():
        contact_phones = [request.POST.get('contact_phone', '').strip()]
        contact_types = [request.POST.get('contact_type', 'other').strip()]
    contact_email = request.POST.get('contact_email', '').strip()

    if contact_name or any(p.strip() for p in contact_phones):
        # Numbers are grouped by their resolved name so one person's multiple
        # numbers merge into a single DebtorContact while different named
        # contacts (e.g. sibling vs. friend) become separate records.
        contacts_by_name = {}
        for i, phone in enumerate(contact_phones):
            phone = phone.strip()
            if not phone:
                continue
            ctype = (contact_types[i].strip() if i < len(contact_types) and contact_types[i].strip() else 'other')
            row_name = (contact_phone_names[i].strip() if i < len(contact_phone_names) and contact_phone_names[i].strip() else contact_name) or 'Contact'
            entry = contacts_by_name.setdefault(row_name, {'type': ctype, 'phones': []})
            entry['phones'].append(phone)
        if contacts_by_name:
            for cname, entry in contacts_by_name.items():
                DebtorContact.objects.create(
                    debtor=debtor,
                    name=cname,
                    contact_type=entry['type'],
                    phone=', '.join(entry['phones']),
                    email=contact_email,
                )
        elif contact_name:
            DebtorContact.objects.create(
                debtor=debtor,
                name=contact_name,
                contact_type='other',
                phone='',
                email=contact_email,
            )
    else:
        _sync_debtor_primary_contact(debtor)

    rc_names = request.POST.getlist('related_company_name[]')
    rc_types = request.POST.getlist('related_company_type[]')
    for i, rc_name in enumerate(rc_names):
        rc_name = rc_name.strip()
        if rc_name:
            DebtorRelatedCompany.objects.create(
                debtor=debtor,
                name=rc_name,
                relation_type=rc_types[i] if i < len(rc_types) else 'sister',
            )

    return JsonResponse({
        'success': True,
        'id': debtor.pk,
        'name': debtor.name,
        'message': f'Debtor "{debtor.name}" ({debtor.debtor_id}) created successfully.',
    })


def debtor_detail(request, pk):
    debtor = get_object_or_404(
        Debtor.objects.prefetch_related('contacts', 'cases__client', 'cases__payments'),
        pk=pk,
    )
    cases = debtor.cases.all().order_by('-created_at')
    contacts = debtor.contacts.all().order_by('name')
    all_users = User.objects.filter(is_active=True).order_by('first_name', 'username')
    all_countries = Country.objects.filter(is_enabled=True).order_by('name')
    country_codes = [c.country_code for c in all_countries]
    default_code = next((c.country_code for c in all_countries if c.name == 'Oman'), '')
    phone_code, phone_number = _split_phone_code(debtor.phone, country_codes)
    telephone_code, telephone_number = _split_phone_code(debtor.telephone, country_codes)
    phone_code = phone_code or default_code
    telephone_code = telephone_code or default_code
    emp_phones = []
    for p in (debtor.employer_phone or '').split(','):
        p = p.strip()
        if not p:
            continue
        code, number = _split_phone_code(p, country_codes)
        emp_phones.append({'code': code or default_code, 'number': number})
    if not emp_phones:
        emp_phones = [{'code': default_code, 'number': ''}]
    individual_statuses = list(DebtorStatusOption.objects.filter(debtor_type='individual', is_enabled=True).values('name', 'order'))
    org_statuses = list(DebtorStatusOption.objects.filter(debtor_type='organization', is_enabled=True).values('name', 'order'))
    return render(request, 'debtor_detail.html', {
        'active_page': 'debtors',
        'debtor': debtor,
        'cases': cases,
        'contacts': contacts,
        'all_users': all_users,
        'all_countries': all_countries,
        'phone_code': phone_code, 'phone_number': phone_number,
        'telephone_code': telephone_code, 'telephone_number': telephone_number,
        'emp_phones': emp_phones,
        'individual_statuses': individual_statuses,
        'org_statuses': org_statuses,
    })


@admin_required
@require_POST
def debtor_update(request, pk):
    debtor = get_object_or_404(Debtor, pk=pk)
    first_name = request.POST.get('first_name', '').strip()
    middle_name = request.POST.get('middle_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    name_parts = [p for p in [first_name, middle_name, last_name] if p]
    name = ' '.join(name_parts) if name_parts else request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'First name is required.'})

    employer_phones_raw = request.POST.getlist('employer_phone[]') or (
        [request.POST.get('employer_phone', '').strip()] if request.POST.get('employer_phone') else []
    )
    employer_phones_raw = [p.strip() for p in employer_phones_raw if p.strip()]
    if not all(_valid_phone(p) for p in [
        request.POST.get('phone', '').strip(),
        request.POST.get('telephone', '').strip(),
        *employer_phones_raw,
    ]):
        return JsonResponse({'success': False, 'message': 'Please enter a valid phone number (country code + number).'})
    if not all(_valid_email(e) for e in [
        request.POST.get('email', '').strip(),
        request.POST.get('email2', '').strip(),
        request.POST.get('employer_email', '').strip(),
    ]):
        return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'})

    dob_raw = request.POST.get('date_of_birth', '').strip()
    dob = None
    if dob_raw:
        try:
            from datetime import date
            dob = date.fromisoformat(dob_raw)
        except ValueError:
            pass

    debtor.name = name
    debtor.first_name = first_name
    debtor.middle_name = middle_name
    debtor.last_name = last_name
    debtor.is_organization = request.POST.get('is_organization') == '1'
    debtor.phone = request.POST.get('phone', '').strip()
    debtor.telephone = request.POST.get('telephone', '').strip()
    debtor.email = request.POST.get('email', '').strip()
    debtor.email2 = request.POST.get('email2', '').strip()
    debtor.gender = request.POST.get('gender', '').strip()
    debtor.date_of_birth = dob
    debtor.nationality = request.POST.get('nationality', '').strip()
    debtor.address_line1 = request.POST.get('address_line1', '').strip()
    debtor.address_line2 = request.POST.get('address_line2', '').strip()
    debtor.city = request.POST.get('city', '').strip()
    debtor.country = request.POST.get('country', '').strip()
    debtor.state = request.POST.get('state', '').strip()
    debtor.passport_cr_number = request.POST.get('passport_cr_number', '').strip()
    debtor.id_number = request.POST.get('id_number', '').strip()
    debtor.notes = request.POST.get('notes', '').strip()
    debtor.employer_name = request.POST.get('employer_name', '').strip()
    debtor.employer_phone = ', '.join(employer_phones_raw)
    debtor.employer_email = request.POST.get('employer_email', '').strip()
    debtor.employer_address = request.POST.get('employer_address', '').strip()
    debtor.job_title = request.POST.get('job_title', '').strip()
    debtor.cr_no = request.POST.get('cr_no', '').strip()
    debtor.occi_no = request.POST.get('occi_no', '').strip()
    debtor.vatin_no = request.POST.get('vatin_no', '').strip()
    debtor.status = request.POST.get('status', 'active')

    collector_id = request.POST.get('collector_id', '').strip()
    if collector_id:
        try:
            debtor.collector = User.objects.get(pk=collector_id)
        except User.DoesNotExist:
            debtor.collector = None
    else:
        debtor.collector = None

    debtor.save()
    _sync_debtor_primary_contact(debtor)
    return JsonResponse({'success': True, 'message': f'Debtor "{debtor.name}" updated successfully.'})


@admin_required
def debtor_detail_json(request, pk):
    debtor = get_object_or_404(Debtor, pk=pk)
    return JsonResponse({
        'id': debtor.pk,
        'first_name': debtor.first_name or '',
        'middle_name': debtor.middle_name or '',
        'last_name': debtor.last_name or '',
        'is_organization': debtor.is_organization,
        'phone': debtor.phone or '',
        'telephone': debtor.telephone or '',
        'email': debtor.email or '',
        'email2': debtor.email2 or '',
        'gender': debtor.gender or '',
        'date_of_birth': str(debtor.date_of_birth) if debtor.date_of_birth else '',
        'nationality': debtor.nationality or '',
        'address_line1': debtor.address_line1 or '',
        'address_line2': debtor.address_line2 or '',
        'city': debtor.city or '',
        'state': debtor.state or '',
        'country': debtor.country or '',
        'passport_cr_number': debtor.passport_cr_number or '',
        'id_number': debtor.id_number or '',
        'cr_no': debtor.cr_no or '',
        'occi_no': debtor.occi_no or '',
        'vatin_no': debtor.vatin_no or '',
        'notes': debtor.notes or '',
        'employer_name': debtor.employer_name or '',
        'employer_phone': debtor.employer_phone or '',
        'employer_email': debtor.employer_email or '',
        'employer_address': debtor.employer_address or '',
        'job_title': debtor.job_title or '',
        'status': debtor.status or 'active',
        'collector_id': debtor.collector_id or '',
    })


@admin_required
@require_POST
def debtor_delete(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'success': False, 'message': 'No debtors selected.'})
    count = Debtor.objects.filter(id__in=ids).count()
    Debtor.objects.filter(id__in=ids).delete()
    return JsonResponse({'success': True, 'message': f'{count} debtor(s) deleted successfully.'})


@admin_required
def debtor_merge_compare(request):
    _MERGE_FIELDS = [
        ('Name', 'name'),
        ('First Name', 'first_name'),
        ('Middle Name', 'middle_name'),
        ('Last Name', 'last_name'),
        ('Is Organization', 'is_organization'),
        ('Passport / CR Number', 'passport_cr_number'),
        ('ID Number', 'id_number'),
        ('CR No', 'cr_no'),
        ('OCCI No', 'occi_no'),
        ('VATIN No', 'vatin_no'),
        ('Email 2', 'email2'),
        ('Phone', 'phone'),
        ('Telephone', 'telephone'),
        ('Gender', 'gender'),
        ('Date of Birth', 'date_of_birth'),
        ('Nationality', 'nationality'),
        ('Address Line 1', 'address_line1'),
        ('Address Line 2', 'address_line2'),
        ('City', 'city'),
        ('State', 'state'),
        ('Country', 'country'),
        ('Address', 'address'),
        ('Employer Name', 'employer_name'),
        ('Employer Phone', 'employer_phone'),
        ('Employer Email', 'employer_email'),
        ('Employer Address', 'employer_address'),
        ('Job Title', 'job_title'),
        ('Notes', 'notes'),
        ('Status', 'status'),
    ]

    if request.method == 'POST':
        d1_id = request.POST.get('d1_id')
        d2_id = request.POST.get('d2_id')
        master_id = request.POST.get('master_id')
        d1 = get_object_or_404(Debtor, pk=d1_id)
        d2 = get_object_or_404(Debtor, pk=d2_id)
        master = d1 if str(master_id) == str(d1.pk) else d2
        other = d2 if master == d1 else d1

        for _, fname in _MERGE_FIELDS:
            selected = request.POST.get(f'field_{fname}')
            if selected == 'd1':
                source = d1
            elif selected == 'd2':
                source = d2
            else:
                # No (valid) choice submitted for this field — keep the master's
                # own value rather than silently falling back to "other".
                source = master
            setattr(master, fname, getattr(source, fname))

        # Email supports keeping both: checking both sources fills Email + Email 2
        # instead of picking just one, so neither address is lost on merge.
        chosen_emails = []
        if request.POST.get('email_use_d1'):
            chosen_emails.append(d1.email)
        if request.POST.get('email_use_d2'):
            chosen_emails.append(d2.email)
        chosen_emails = [e for e in chosen_emails if e]
        if chosen_emails:
            master.email = chosen_emails[0]
            if len(chosen_emails) > 1:
                master.email2 = chosen_emails[1]

        master.save()
        Case.objects.filter(debtor=other).update(debtor=master)
        from .models import DebtorContact
        DebtorContact.objects.filter(debtor=other).update(debtor=master)
        other.delete()
        return redirect('debtors')

    # GET
    ids = request.GET.getlist('ids[]') or request.GET.getlist('ids')
    if len(ids) < 2:
        return redirect('debtors')
    d1 = get_object_or_404(Debtor, pk=ids[0])
    d2 = get_object_or_404(Debtor, pk=ids[1])
    fields = [
        (label, fname, str(getattr(d1, fname) or ''), str(getattr(d2, fname) or ''))
        for label, fname in _MERGE_FIELDS
    ]
    return render(request, 'debtor_merge_compare.html', {'d1': d1, 'd2': d2, 'fields': fields})


@admin_required
@require_POST
def debtor_merge(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if len(ids) < 2:
        return JsonResponse({'success': False, 'message': 'Select at least 2 debtors to merge.'})

    debtors_qs = Debtor.objects.filter(id__in=ids).order_by('created_at')
    primary = debtors_qs.first()
    others = debtors_qs.exclude(pk=primary.pk)
    Case.objects.filter(debtor__in=others).update(debtor=primary)
    deleted_count = others.count()
    others.delete()
    return JsonResponse({
        'success': True,
        'message': f'Merged {deleted_count} debtor(s) into "{primary.name}".',
    })


@admin_required
def debtor_export(request, format):
    qs = Debtor.objects.select_related('created_by', 'collector').annotate(
        total_cases=Count('cases')
    ).order_by('-created_at')
    headers = ['Debtor ID', 'Name', 'Passport/CR No.', 'ID Number', 'Email', 'Email 2',
               'Phone', 'Cases', 'Collector', 'Status', 'Created By', 'Created At']
    rows = [
        [
            d.debtor_id, d.name, d.passport_cr_number, d.id_number,
            d.email, d.email2, d.phone, d.total_cases,
            d.collector.get_full_name() or d.collector.username if d.collector else '—',
            d.get_status_display(),
            d.created_by.get_full_name() or d.created_by.username if d.created_by else '—',
            d.created_at.strftime('%Y-%m-%d'),
        ]
        for d in qs
    ]
    if format == 'csv':
        return _export_csv('debtors', headers, rows)
    if format == 'excel':
        return _export_excel('Debtors', headers, rows)
    if format == 'pdf':
        # landscape A4 usable ≈ 802pt; 12 cols
        col_widths = [62, 80, 65, 55, 98, 85, 68, 30, 62, 50, 62, 55]  # total 772
        return _export_pdf('Debtors Report', headers, rows, col_widths)
    return redirect('debtors')


def case_detail(request, pk):
    from .models import CaseType, Country
    case = get_object_or_404(Case, pk=pk)
    case_types = CaseType.objects.filter(is_enabled=True).order_by('name')
    collectors = User.objects.filter(is_active=True).order_by('first_name', 'username')
    clients = Client.objects.filter(status='active').order_by('name')
    debtors = Debtor.objects.order_by('name')
    follow_ups  = case.follow_ups.select_related('followed_by').order_by('-follow_up_date')
    payments    = list(case.payments.filter(is_installment=False).select_related('payment_mode', 'collection_currency', 'received_currency').order_by('-payment_date'))
    installments = list(case.payments.filter(is_installment=True).order_by('payment_date'))
    installments_total = sum(float(i.amount or 0) for i in installments)
    last_payment = payments[0] if payments else None
    from django.db.models import Sum as _PaySum

    # Currency conversion convention: OMR = foreign_amount / currency.value
    # (currency.value = units of that currency per 1 OMR; e.g. AED ≈ 9.524)
    _case_rate = float(case.currency.value) if case.currency and case.currency.value else 1

    def _to_omr(amount, currency):
        if amount is None:
            return 0.0
        r = float(currency.value) if currency and currency.value else _case_rate
        return float(amount) / r if r else float(amount)

    # Per-payment OMR equivalents (shown in brackets in history)
    for _p in payments:
        _p.received_omr = _to_omr(_p.received_amount, _p.received_currency) if _p.received_amount else None
        _p.collection_omr = _to_omr(_p.amount, _p.collection_currency) if _p.amount else None

    # Raw sums across payments are only meaningful when every payment uses the
    # same currency; otherwise the table totals fall back to the OMR figure.
    def _single_currency(codes):
        codes = set(codes)
        return codes.pop() if len(codes) == 1 else None

    _case_code = case.currency.code if case.currency else 'OMR'
    fin_payment_currency = _single_currency(
        (p.collection_currency.code if p.collection_currency else _case_code) for p in payments
    ) if payments else None
    fin_received_currency = _single_currency(
        (p.received_currency.code if p.received_currency else _case_code)
        for p in payments if p.received_amount
    ) if any(p.received_amount for p in payments) else None

    # Only an Approved (cleared) payment has actually landed — Pending hasn't
    # been confirmed yet and Rejected never will be — so both are excluded from
    # the collected total, the Payment History "Total" row, and anything
    # derived from it (Remaining Amount, etc.). Both still stay listed in the
    # table above for the record, just excluded from the sums.
    fin_total_payment     = sum(float(p.amount or 0) for p in payments if p.status == 'cleared')
    fin_total_received    = sum(float(p.received_amount or 0) for p in payments if p.status == 'cleared')   # received-currency total
    fin_total_received_omr = sum(_to_omr(p.received_amount, p.received_currency) for p in payments if p.status == 'cleared')
    fin_total_payment_omr = sum(_to_omr(p.amount, p.collection_currency) for p in payments if p.status == 'cleared')
    fin_last_payment_omr  = _to_omr(last_payment.amount, last_payment.collection_currency) if last_payment else 0
    fin_approved_omr      = float(case.approved_amount) / _case_rate if _case_rate else float(case.approved_amount)
    fin_discount_omr      = float(case.discount_amount or 0) / _case_rate if _case_rate else float(case.discount_amount or 0)
    # Remaining is driven by what has been collected (Total Payment Done), not by
    # the transferred/received amounts — otherwise it stays at the full approved
    # amount until transfers are confirmed. Computed in OMR then converted back so
    # mixed-currency payments net correctly.
    fin_remaining_omr     = fin_approved_omr - fin_total_payment_omr
    fin_remaining         = fin_remaining_omr * _case_rate
    reminders   = case.reminders.order_by('reminder_date')
    attachments = case.attachments.select_related('uploaded_by').order_by('-uploaded_at')
    try:
        legal_case = case.legal_case
    except Exception:
        legal_case = None

    # Legal tab data: settings-managed status options, fee types, fees, and the
    # legal slice of case history (Legal Update History).
    legal_status_options = [s.name for s in LegalCaseStatus.objects.filter(is_enabled=True).order_by('name')]
    if legal_case:
        cur = legal_case.status_label
        if cur and cur not in legal_status_options:
            legal_status_options.insert(0, cur)
    legal_fee_types = LegalFeeType.objects.filter(is_enabled=True).order_by('name')
    legal_fees = legal_case.fees.select_related('fee_type', 'created_by').all() if legal_case else []
    legal_history = case.case_history.filter(action__istartswith='Legal').select_related('action_by') if legal_case else []
    countries     = Country.objects.filter(is_enabled=True).order_by('name')
    payment_modes = PaymentMode.objects.filter(is_enabled=True).order_by('name')
    currencies       = enabled_currencies(include_pks=[case.currency_id])
    attachment_types = AttachmentType.objects.filter(is_enabled=True, type='case').order_by('name')
    case_history  = case.case_history.select_related('action_by').order_by('-created_at')

    # Calculate case age from received_date (or created_at) to now
    from django.utils import timezone
    from datetime import date as _date
    start = case.received_date or case.created_at.date()
    today = _date.today()
    total_days  = (today - start).days
    age_years   = total_days // 365
    age_months  = (total_days % 365) // 30
    age_days    = (total_days % 365) % 30
    age_str = f"{age_years} year{'s' if age_years != 1 else ''} {age_months:02d} months and {age_days:02d} days"

    return render(request, 'case_detail.html', {
        'case': case,
        'case_types': case_types,
        'collectors': collectors,
        'clients': clients,
        'debtors': debtors,
        'follow_ups': follow_ups,
        'payments': payments,
        'installments': installments,
        'installments_total': installments_total,
        'last_payment': last_payment,
        'fin_total_payment': fin_total_payment,
        'fin_total_received': fin_total_received,
        'fin_payment_currency': fin_payment_currency,
        'fin_received_currency': fin_received_currency,
        'fin_total_received_omr': fin_total_received_omr,
        'fin_total_payment_omr': fin_total_payment_omr,
        'fin_last_payment_omr': fin_last_payment_omr,
        'fin_approved_omr': fin_approved_omr,
        'fin_discount_omr': fin_discount_omr,
        'fin_remaining': fin_remaining,
        'fin_remaining_omr': fin_remaining_omr,
        'reminders': reminders,
        'attachments': attachments,
        'legal_case': legal_case,
        'legal_status_options': legal_status_options,
        'legal_fee_types': legal_fee_types,
        'legal_fees': legal_fees,
        'legal_history': legal_history,
        'agencies': Agency.objects.filter(status='active').order_by('name'),
        'lawyers': Lawyer.objects.filter(status='active').order_by('name'),
        'countries': countries,
        'case_history': case_history,
        'case_age_str': age_str,
        'payment_modes': payment_modes,
        'currencies': currencies,
        'attachment_types': attachment_types,
        'followup_type_options': _followup_type_options(),
        'active_sub': 'cases',
    })


@require_POST
def case_detail_update(request, pk):
    case = get_object_or_404(Case, pk=pk)

    account_no = request.POST.get('account_no', '').strip()
    if not account_no:
        return JsonResponse({'success': False, 'message': 'Account No is required.'})

    # Duplicate account_no check for the same client
    client_id = request.POST.get('client_id', '').strip() or case.client_id
    duplicate = Case.objects.filter(
        client_id=client_id, account_no=account_no
    ).exclude(pk=case.pk).first()
    if duplicate:
        return JsonResponse({
            'success': False,
            'message': f'Account No "{account_no}" already exists for this client (Case: {duplicate.case_id}).'
        })

    case.creditor_name = request.POST.get('creditor_name', '').strip()
    # For a non-agency client, the client itself is the creditor.
    if not case.creditor_name and case.client and case.client.client_type != 'agency':
        case.creditor_name = case.client.name
    rd = request.POST.get('received_date', '').strip()
    case.received_date = rd if rd else None
    dd = request.POST.get('due_date', '').strip()
    case.due_date = dd if dd else None
    ct = request.POST.get('case_type_id', '').strip()
    case.case_type_id = int(ct) if ct else None
    case.account_no = account_no
    case.relationship_no = request.POST.get('relationship_no', '').strip()
    case.shadow_account_no = request.POST.get('shadow_account_no', '').strip()
    case.cif_no = request.POST.get('cif_no', '').strip()
    new_status = request.POST.get('status', '').strip()
    if new_status:
        if new_status in Case.DATE_REQUIRED_STATUSES:
            from datetime import date as _date
            praw = request.POST.get('promise_to_pay_date', '').strip()
            if praw:
                try:
                    case.promise_to_pay_date = _date.fromisoformat(praw)
                except ValueError:
                    return JsonResponse({'success': False, 'message': 'Invalid Promise Date.'})
            elif not case.promise_to_pay_date:
                return JsonResponse({'success': False, 'message': 'Promise Date is required for the Promise to Pay status.'})
        case.status = new_status
    coll = request.POST.get('collector_id', '').strip()
    case.collector_id = int(coll) if coll else None
    case.case_country = request.POST.get('case_country', '').strip()
    case.is_agency = request.POST.get('is_agency') == '1'
    agency_id = request.POST.get('agency_id', '').strip()
    # Only keep a linked agency while Is Agency is on; clear it otherwise.
    case.agency_id = int(agency_id) if (case.is_agency and agency_id) else None
    case.notes = request.POST.get('notes', '').strip()
    aa = request.POST.get('approved_amount', '').strip()
    if aa:
        case.approved_amount = aa
    ra = request.POST.get('received_amount', '').strip()
    if ra:
        case.received_amount = ra
    pa = request.POST.get('principal_amount', '').strip()
    if pa:
        case.principal_amount = pa
    comm = request.POST.get('commission', '').strip()
    if comm:
        case.commission = comm
    disc = request.POST.get('discount_amount', '').strip()
    if disc:
        case.discount_amount = disc
    case.discount_given = request.POST.get('discount_given') == '1'
    curr = request.POST.get('currency_id', '').strip()
    case.currency_id = int(curr) if curr else None
    case.save()
    return JsonResponse({'success': True, 'message': 'Case updated successfully.'})


@require_POST
def case_change_legal_status(request, pk):
    """Change the legal status of a case's linked LegalCase from the case detail
    page. Auto-creates the LegalCase if one doesn't exist yet."""
    case = get_object_or_404(Case, pk=pk)
    if not hasattr(case, 'legal_case'):
        case.ensure_legal_case(created_by=request.user if request.user.is_authenticated else None)
    lc = case.legal_case
    new_status = request.POST.get('legal_status', '').strip()
    valid_names = set(LegalCaseStatus.objects.filter(is_enabled=True).values_list('name', flat=True))
    if not new_status or (new_status not in valid_names and new_status != lc.legal_status):
        return JsonResponse({'success': False, 'message': 'Invalid legal status.'})
    update_fields = ['legal_status']
    # Any status mentioning "hearing" (In Court Hearing, In Appeal Hearing, …)
    # requires a Next Hearing Date, the same way Promise to Pay requires one.
    if 'hearing' in new_status.lower():
        from datetime import date as _date
        hearing_date_raw = request.POST.get('next_hearing', '').strip()
        if not hearing_date_raw:
            return JsonResponse({'success': False, 'message': 'Next Hearing Date is required for this status.'})
        try:
            lc.next_hearing = _date.fromisoformat(hearing_date_raw)
        except ValueError:
            return JsonResponse({'success': False, 'message': 'Invalid Next Hearing Date.'})
        update_fields.append('next_hearing')
    lc.legal_status = new_status
    lc.save(update_fields=update_fields)
    _log_case(request, case, f'Legal Status Changed to {new_status}')
    return JsonResponse({'success': True, 'message': f'Legal status updated to {new_status}.'})


@require_POST
def case_change_status(request, pk):
    """Change just the case status (Change Status modal on the detail page).
    Separate from the full General-form save so it doesn't require Account No."""
    case = get_object_or_404(Case, pk=pk)
    status = request.POST.get('status', '').strip()
    valid = dict(Case.all_status_choices())
    if status not in valid:
        return JsonResponse({'success': False, 'message': 'Invalid status.'})
    if status in Case.DATE_REQUIRED_STATUSES:
        from datetime import date as _date
        promise_date_raw = request.POST.get('promise_to_pay_date', '').strip()
        if not promise_date_raw:
            return JsonResponse({'success': False, 'message': 'Promise Date is required for this status.'})
        try:
            promise_date = _date.fromisoformat(promise_date_raw)
        except ValueError:
            return JsonResponse({'success': False, 'message': 'Invalid Promise Date.'})
        case.promise_to_pay_date = promise_date
        case.promise_completed_at = None  # fresh promise — no longer "done"
    case.status = status
    case.save()  # save() auto-creates the LegalCase when status is legal_action_approved
    msg = f'Status changed to {valid[status]}.'
    if status in Case.DATE_REQUIRED_STATUSES:
        msg = f'Status changed to {valid[status]} — promised by {promise_date.strftime("%d/%m/%Y")}.'
    _log_case(request, case, f'Case Status Changed to {valid[status]}')
    return JsonResponse({'success': True, 'message': msg})


@require_POST
def case_change_collector(request, pk):
    """Change just the assigned collector (Change Collector modal)."""
    case = get_object_or_404(Case, pk=pk)
    collector_id = request.POST.get('collector_id', '').strip()
    if collector_id:
        try:
            collector = User.objects.get(pk=collector_id)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'User not found.'})
    else:
        collector = None
    case.collector = collector
    case.save(update_fields=['collector'])
    name = (collector.get_full_name() or collector.username) if collector else '(none)'
    _log_case(request, case, f'Collector Changed to {name}')
    return JsonResponse({'success': True, 'message': f'Collector changed to {name}.'})


@require_POST
def case_legal_info_update(request, pk):
    """Save the full Legal Info form (Legal tab) for a case's legal record."""
    case = get_object_or_404(Case, pk=pk)
    if not hasattr(case, 'legal_case'):
        case.ensure_legal_case(created_by=request.user if request.user.is_authenticated else None)
    lc = case.legal_case

    def _date(name):
        raw = request.POST.get(name, '').strip()
        if not raw:
            return None
        try:
            from datetime import date
            return date.fromisoformat(raw)
        except ValueError:
            return None

    def _dec(name):
        raw = request.POST.get(name, '').strip()
        if not raw:
            return Decimal('0')
        try:
            return Decimal(raw)
        except (InvalidOperation, TypeError):
            return Decimal('0')

    lawyer_id = request.POST.get('lawyer_id', '').strip()
    if not lawyer_id:
        return JsonResponse({'success': False, 'message': 'Please select a lawyer.'})
    lc.lawyer_id = int(lawyer_id)
    lc.legal_date = _date('legal_date')
    lc.next_hearing = _date('next_hearing')
    lc.legal_case_no = request.POST.get('legal_case_no', '').strip()
    lc.legal_advisor = request.POST.get('legal_advisor', '').strip()
    lc.judgment_no = request.POST.get('judgment_no', '').strip()
    lc.judgement_amount = _dec('judgement_amount')
    lc.outstanding_amount = _dec('outstanding_amount')
    lc.remaining_amount = _dec('remaining_amount')
    lc.lawyer_fee = _dec('lawyer_fee')
    lc.notes = request.POST.get('notes', '').strip()

    # Legal status, if the form included it (validated against settings list).
    new_status = request.POST.get('legal_status', '').strip()
    if new_status:
        valid_names = set(LegalCaseStatus.objects.filter(is_enabled=True).values_list('name', flat=True))
        if new_status in valid_names or new_status == lc.legal_status:
            lc.legal_status = new_status

    lc.save()
    _log_case(request, case, 'Legal Info Updated')
    return JsonResponse({'success': True, 'message': 'Legal info saved.'})


@require_POST
def legal_fee_add(request, pk):
    """Add a legal fee to a case's legal record (Legal tab → Legal Fees)."""
    case = get_object_or_404(Case, pk=pk)
    if not hasattr(case, 'legal_case'):
        case.ensure_legal_case(created_by=request.user if request.user.is_authenticated else None)
    lc = case.legal_case

    fee_date_raw = request.POST.get('fee_date', '').strip()
    fee_date = None
    if fee_date_raw:
        try:
            from datetime import date
            fee_date = date.fromisoformat(fee_date_raw)
        except ValueError:
            return JsonResponse({'success': False, 'message': 'Invalid fee date.'})
    if not fee_date:
        return JsonResponse({'success': False, 'message': 'Fee date is required.'})

    try:
        amount = Decimal(request.POST.get('amount', '0') or '0')
    except (InvalidOperation, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid amount.'})

    fee_type_id = request.POST.get('fee_type_id', '').strip()
    fee = LegalFee(
        legal_case=lc,
        fee_type_id=int(fee_type_id) if fee_type_id else None,
        fee_date=fee_date,
        amount=amount,
        notes=request.POST.get('notes', '').strip(),
        created_by=request.user if request.user.is_authenticated else None,
    )
    fee.save()
    _log_case(request, case, f'Legal Fee Added: {fee.fee_type.name if fee.fee_type else "Fee"} — {amount}')
    return JsonResponse({'success': True, 'message': 'Legal fee added.'})


@require_POST
def legal_fee_delete(request):
    fee_id = request.POST.get('id', '').strip()
    fee = LegalFee.objects.select_related('legal_case__case', 'fee_type').filter(pk=fee_id).first() if fee_id else None
    if fee is None:
        return JsonResponse({'success': False, 'message': 'Legal fee not found.'})
    case = fee.legal_case.case
    label = fee.fee_type.name if fee.fee_type else 'Fee'
    fee.delete()
    _log_case(request, case, f'Legal Fee Deleted: {label}')
    return JsonResponse({'success': True, 'message': 'Legal fee deleted.'})


@require_POST
def case_financials_update(request, pk):
    case = get_object_or_404(Case, pk=pk)
    def _dec(key):
        v = request.POST.get(key, '').strip()
        return v if v else None

    if _dec('approved_amount') is not None:
        case.approved_amount = _dec('approved_amount')
    if _dec('principal_amount') is not None:
        case.principal_amount = _dec('principal_amount')
    if _dec('commission') is not None:
        case.commission = _dec('commission')
    if _dec('discount_amount') is not None:
        case.discount_amount = _dec('discount_amount')
    case.discount_given = request.POST.get('discount_given') == '1'
    if 'discount_note' in request.POST:
        case.discount_note = request.POST.get('discount_note', '').strip()
    curr = request.POST.get('currency_id', '').strip()
    case.currency_id = int(curr) if curr else None
    # Only touch notes when the form actually sent the field — otherwise a
    # financials save from a form without a notes input would wipe them.
    if 'notes' in request.POST:
        case.notes = request.POST.get('notes', '').strip()
    case.save()
    _log_case(request, case, 'Updated Case Financials')
    return JsonResponse({'success': True, 'message': 'Financials updated successfully.'})


@login_required
def cases(request):
    from django.core.paginator import Paginator
    is_admin = request.user.is_superuser
    collector_id = request.GET.get('collector', '')
    debtor_id = request.GET.get('debtor', '')
    client_id = request.GET.get('client', '')
    account_no = request.GET.get('account_no', '')
    case_status = request.GET.get('status', '')
    received_date = request.GET.get('received_date', '')
    # By default closed cases (any status containing "closed") and cases approved
    # for legal action are hidden to keep the initial load light. ?show_all=1
    # includes them; picking a status filter explicitly also overrides the hiding.
    show_all = request.GET.get('show_all') == '1'
    from django.db.models import Q as _Q
    hidden_q = _Q(status__icontains='closed') | _Q(status=Case.LEGAL_STATUS)

    qs = Case.objects.select_related('client', 'debtor', 'collector', 'client__created_by', 'currency').prefetch_related(
        Prefetch('payments', queryset=Payment.objects.select_related('received_currency', 'collection_currency'))
    ).annotate(
        last_followup_date=Max('follow_ups__follow_up_date')
    ).order_by('-created_at')

    # Staff only see cases they collect; admins see everything.
    if not is_admin:
        qs = qs.filter(collector=request.user)

    if collector_id:
        qs = qs.filter(collector_id=collector_id)
    if debtor_id:
        qs = qs.filter(debtor_id=debtor_id)
    if client_id:
        qs = qs.filter(client_id=client_id)
    if account_no:
        qs = qs.filter(case_id__icontains=account_no)
    if received_date:
        qs = qs.filter(created_at__date=received_date)

    # How many cases are being hidden (closed + legal action approved) under the
    # current (non-status) filters.
    hidden_count = qs.filter(hidden_q).count()

    if case_status:
        qs = qs.filter(status=case_status)
    elif not show_all:
        qs = qs.exclude(hidden_q)

    total_count = qs.count()
    page_size_options = [10, 50, 100, 'All']
    show = request.GET.get('show', '10')
    page_size = total_count or 1 if show == 'All' else int(show) if show.isdigit() else 10

    paginator  = Paginator(qs, page_size)
    page_obj   = paginator.get_page(request.GET.get('page', 1))
    params     = request.GET.copy(); params.pop('page', None)
    query_string = params.urlencode()
    # Query string for the show-all toggle: all current filters minus page/show_all.
    base_params = request.GET.copy()
    base_params.pop('page', None); base_params.pop('show_all', None)
    base_query_string = base_params.urlencode()

    grouped_case_ids = set(
        CaseGroup.objects.filter(cases__isnull=False).values_list('cases__id', flat=True)
    )

    total_remaining_sum = sum((c.remaining_amount_omr for c in qs), 0.0)

    return render(request, 'cases.html', {
        'active_page': 'cases',
        'active_sub': 'all_cases',
        'cases': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'total_remaining_sum': total_remaining_sum,
        'page_size': show,
        'page_size_options': page_size_options,
        'query_string': query_string,
        'base_query_string': base_query_string,
        'show_all': show_all,
        'hidden_count': hidden_count,
        'all_clients': (Client.objects.filter(status='active') if is_admin
                        else Client.objects.filter(status='active', cases__collector=request.user).distinct()).order_by('name'),
        'all_debtors': (Debtor.objects.filter(status='active') if is_admin
                        else Debtor.objects.filter(status='active', cases__collector=request.user).distinct()).order_by('name'),
        'all_users': User.objects.filter(is_active=True).order_by('username') if is_admin else User.objects.filter(pk=request.user.pk),
        'all_currencies': enabled_currencies(),
        'all_groups': CaseGroup.objects.order_by('name'),
        'all_case_types': CaseType.objects.filter(is_enabled=True).order_by('name'),
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
        'all_agencies': Agency.objects.filter(status='active').order_by('name'),
        'grouped_case_ids': grouped_case_ids,
        'status_choices': Case.all_status_choices(),
        'filter_collector': collector_id,
        'filter_debtor': debtor_id,
        'filter_client': client_id,
        'filter_account_no': account_no,
        'filter_status': case_status,
        'filter_received_date': received_date,
    })


@require_POST
def case_create_modal(request):
    client_id = request.POST.get('client_id', '').strip()
    debtor_id = request.POST.get('debtor_id', '').strip()
    if not client_id or not debtor_id:
        return JsonResponse({'success': False, 'message': 'Client and Debtor are required.'})

    try:
        client = Client.objects.get(pk=client_id)
        debtor = Debtor.objects.get(pk=debtor_id)
    except (Client.DoesNotExist, Debtor.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'Invalid client or debtor.'})

    # When the client is an agency, a creditor name is required (the agency
    # collects on behalf of an actual creditor).
    creditor_name = request.POST.get('creditor_name', '').strip()
    if client.client_type == 'agency' and not creditor_name:
        return JsonResponse({'success': False, 'message': 'Creditor Name is required for an agency client.'})
    # For a non-agency client, the client itself is the creditor.
    if not creditor_name:
        creditor_name = client.name

    # Account No is mandatory and must be unique per client.
    account_no = request.POST.get('account_no', '').strip()
    if not account_no:
        return JsonResponse({'success': False, 'message': 'Account No is required.'})
    if Case.objects.filter(client=client, account_no__iexact=account_no).exists():
        return JsonResponse({'success': False, 'message': f'Account No "{account_no}" already exists for this client.'})

    currency_id    = request.POST.get('currency_id', '').strip()
    discount_raw   = request.POST.get('discount_amount', '').strip()
    principal_raw  = request.POST.get('principal_amount', '').strip()
    total_app_raw  = request.POST.get('total_approved', '').strip()
    # The wizard's gross Outstanding Amount (posts it as both outstanding_amount
    # and, historically, approved_amount).
    outstanding_raw = request.POST.get('outstanding_amount', '').strip() or request.POST.get('approved_amount', '').strip()

    # Status from the form (defaults to active).
    status = request.POST.get('status', 'active').strip() or 'active'
    if status not in dict(Case.all_status_choices()):
        status = 'active'

    # Received Date is mandatory — it drives the New/Additional Allocation report.
    received_raw = request.POST.get('received_date', '').strip()
    if not received_raw:
        return JsonResponse({'success': False, 'message': 'Received Date is required.'})
    try:
        from datetime import date
        received_date = date.fromisoformat(received_raw)
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Invalid Received Date.'})

    case = Case(
        client=client,
        debtor=debtor,
        approved_amount=float(total_app_raw) if total_app_raw else (float(request.POST.get('approved_amount', 0) or 0)),
        received_amount=0,
        principal_amount=float(principal_raw) if principal_raw else 0,
        outstanding_amount=float(outstanding_raw) if outstanding_raw else 0,
        discount_amount=float(discount_raw) if discount_raw else 0,
        discount_given=bool(discount_raw and float(discount_raw) > 0),
        discount_note=request.POST.get('discount_note', '').strip(),
        status=status,
        creditor_name=creditor_name,
        account_no=account_no,
        received_date=received_date,
        case_country=request.POST.get('case_country', '').strip(),
        notes=request.POST.get('notes', '').strip(),
    )
    if currency_id:
        try:
            case.currency_id = int(currency_id)
        except (ValueError, TypeError):
            pass
    case_type_id = request.POST.get('case_type_id', '').strip()
    if case_type_id:
        try:
            case.case_type_id = int(case_type_id)
        except (ValueError, TypeError):
            pass
    case.is_agency = request.POST.get('is_agency') == '1'
    agency_id = request.POST.get('agency_id', '').strip()
    case.agency_id = int(agency_id) if (case.is_agency and agency_id) else None
    collector_id = request.POST.get('collector_id', '').strip()
    if collector_id:
        try:
            case.collector = User.objects.get(pk=collector_id)
        except User.DoesNotExist:
            pass
    case.save()
    _log_case(request, case, 'Added Case')
    _grant_full_client_case_access(case)

    return JsonResponse({
        'success': True,
        'message': f'Case "{case.case_id}" created successfully.',
        # Frontend navigates straight to the new case instead of reloading the list.
        'redirect_url': reverse('case_detail', args=[case.pk]),
    })


@perm_required('cases', 'delete')
@require_POST
def case_delete(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'success': False, 'message': 'No cases selected.'})
    count = Case.objects.filter(id__in=ids).count()
    Case.objects.filter(id__in=ids).delete()
    return JsonResponse({'success': True, 'message': f'{count} case(s) deleted successfully.'})


@require_POST
def case_bulk_change_status(request):
    ids    = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    status = request.POST.get('status', '').strip()
    if not ids:
        return JsonResponse({'success': False, 'message': 'No cases selected.'})
    if not status:
        return JsonResponse({'success': False, 'message': 'Status is required.'})
    if status in Case.DATE_REQUIRED_STATUSES:
        return JsonResponse({'success': False, 'message': 'This status requires a Promise Date — change cases one at a time from the case page.'})
    cases_qs = Case.objects.filter(id__in=ids)
    status_label = dict(Case.all_status_choices()).get(status, status)
    for case in cases_qs:
        _log_case(request, case, f'Case Status Changed to {status_label}')
    count = cases_qs.update(status=status)
    # .update() bypasses Case.save(), so trigger the legal-case sync explicitly.
    if status == Case.LEGAL_STATUS:
        for case in Case.objects.filter(id__in=ids):
            case.ensure_legal_case(created_by=request.user if request.user.is_authenticated else None)
    return JsonResponse({'success': True, 'message': f'Status updated for {count} case(s).'})


@require_POST
def case_bulk_change_collector(request):
    ids          = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    collector_id = request.POST.get('collector_id', '').strip()
    if not ids:
        return JsonResponse({'success': False, 'message': 'No cases selected.'})
    try:
        collector = User.objects.get(pk=collector_id) if collector_id else None
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found.'})
    name = collector.get_full_name() or collector.username if collector else '(none)'
    cases_qs = Case.objects.filter(id__in=ids)
    for case in cases_qs:
        _log_case(request, case, f'Collector Changed to {name}')
    count = cases_qs.update(collector=collector)
    return JsonResponse({'success': True, 'message': f'Collector set to "{name}" for {count} case(s).'})


@require_POST
def case_bulk_add_user(request):
    ids     = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    user_id = request.POST.get('user_id', '').strip()
    if not ids:
        return JsonResponse({'success': False, 'message': 'No cases selected.'})
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found.'})
    cases = Case.objects.filter(id__in=ids)
    for case in cases:
        case.additional_users.add(user)
    name = user.get_full_name() or user.username
    return JsonResponse({'success': True, 'message': f'"{name}" added to {cases.count()} case(s).'})


@require_POST
def case_bulk_remove_user(request):
    ids     = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    user_id = request.POST.get('user_id', '').strip()
    if not ids:
        return JsonResponse({'success': False, 'message': 'No cases selected.'})
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found.'})
    cases = Case.objects.filter(id__in=ids)
    for case in cases:
        case.additional_users.remove(user)
    name = user.get_full_name() or user.username
    return JsonResponse({'success': True, 'message': f'"{name}" removed from {cases.count()} case(s).'})


@require_POST
def case_bulk_group(request):
    ids      = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    group_id = request.POST.get('group_id', '').strip()
    new_name = request.POST.get('new_name', '').strip()
    if not ids:
        return JsonResponse({'success': False, 'message': 'No cases selected.'})
    cases = Case.objects.filter(id__in=ids)
    # A group may only hold cases of a single client — reject mixed selections
    # before touching (or creating) any group.
    client_ids = set(cases.values_list('client_id', flat=True))
    if len(client_ids) > 1:
        return JsonResponse({'success': False, 'message': 'Cannot group: the selected cases belong to different clients.'})
    if group_id:
        try:
            group = CaseGroup.objects.get(pk=group_id)
        except CaseGroup.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Group not found.'})
        existing_clients = set(group.cases.values_list('client_id', flat=True))
        if existing_clients and not client_ids.issubset(existing_clients):
            return JsonResponse({'success': False, 'message': f'Cannot group: group "{group.name}" holds cases of a different client.'})
    elif new_name:
        group = CaseGroup.objects.create(name=new_name, created_by=request.user)
    else:
        return JsonResponse({'success': False, 'message': 'Select an existing group or enter a new group name.'})
    group.cases.add(*cases)
    return JsonResponse({'success': True, 'message': f'{cases.count()} case(s) added to group "{group.name}".'})


def case_export(request, format):
    qs = Case.objects.select_related('client', 'debtor', 'collector').order_by('-created_at')
    headers = ['Case ID', 'Client', 'Debtor', 'Approved (OMR)', 'Received (OMR)',
               'Remaining (OMR)', 'Status', 'Collector', 'Created At']
    rows = [
        [
            c.case_id, c.client.name, c.debtor.name,
            c.approved_amount, c.received_amount, c.remaining_amount,
            c.get_status_display(),
            c.collector.get_full_name() or c.collector.username if c.collector else '—',
            c.created_at.strftime('%Y-%m-%d'),
        ]
        for c in qs
    ]
    if format == 'csv':
        return _export_csv('cases', headers, rows)
    if format == 'excel':
        return _export_excel('Cases', headers, rows)
    if format == 'pdf':
        return _export_pdf('Cases Report', headers, rows)
    return redirect('cases')


# ---------- LEGAL CASES ----------
def legal_cases(request):
    lawyer = request.GET.get('lawyer', '')
    debtor_id = request.GET.get('debtor', '')
    client_id = request.GET.get('client', '')
    agency_id = request.GET.get('agency', '')
    account_no = request.GET.get('account_no', '')
    legal_status = request.GET.get('legal_status', '')
    approved_date = request.GET.get('approved_date', '')

    qs = LegalCase.objects.select_related(
        'case__client', 'case__debtor', 'case__collector', 'case__agency', 'created_by'
    ).annotate(
        last_follow_up=Max('case__follow_ups__follow_up_date')
    ).order_by('-created_at')

    if lawyer:
        # Match the FK lawyer or the legacy free-text name (lawyer_display).
        qs = qs.filter(Q(lawyer__name__icontains=lawyer) | Q(lawyer_name__icontains=lawyer))
    if debtor_id:
        qs = qs.filter(case__debtor_id=debtor_id)
    if client_id:
        qs = qs.filter(case__client_id=client_id)
    if agency_id:
        qs = qs.filter(case__agency_id=agency_id)
    if account_no:
        qs = qs.filter(case__case_id__icontains=account_no)
    if legal_status:
        qs = qs.filter(legal_status=legal_status)
    if approved_date:
        qs = qs.filter(legal_approved_date=approved_date)

    # Dropdown options: lawyers from Settings plus any legacy free-text names
    # still stored on legal cases.
    lawyer_names = set(Lawyer.objects.filter(status='active').values_list('name', flat=True))
    lawyer_names.update(
        n.strip() for n in LegalCase.objects.exclude(lawyer_name='').values_list('lawyer_name', flat=True) if n.strip()
    )
    all_lawyers = sorted(lawyer_names, key=str.lower)

    return render(request, 'legal_cases.html', {
        'active_page': 'legal_cases',
        'legal_cases': qs,
        'all_clients': Client.objects.filter(status='active').order_by('name'),
        'all_debtors': Debtor.objects.filter(status='active').order_by('name'),
        'all_users': User.objects.filter(is_active=True).order_by('username'),
        'all_cases': Case.objects.select_related('client', 'debtor').order_by('-created_at'),
        'all_lawyers': all_lawyers,
        'all_agencies': Agency.objects.filter(status='active').order_by('name'),
        'status_choices': LegalCaseStatus.objects.filter(is_enabled=True).order_by('name'),
        'filter_lawyer': lawyer,
        'filter_debtor': debtor_id,
        'filter_client': client_id,
        'filter_agency': agency_id,
        'filter_account_no': account_no,
        'filter_legal_status': legal_status,
        'filter_approved_date': approved_date,
    })


@require_POST
def legal_case_create(request):
    case_id = request.POST.get('case_id', '').strip()
    if not case_id:
        return JsonResponse({'success': False, 'message': 'Case is required.'})
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Invalid case.'})

    if hasattr(case, 'legal_case'):
        return JsonResponse({'success': False, 'message': 'This case is already a legal case.'})

    approved_raw = request.POST.get('legal_approved_date', '').strip()
    approved_date = None
    if approved_raw:
        try:
            from datetime import date
            approved_date = date.fromisoformat(approved_raw)
        except ValueError:
            pass

    lawyer_name = request.POST.get('lawyer_name', '').strip()
    lc = LegalCase(
        case=case,
        lawyer_name=lawyer_name,
        # Link the Lawyer record when the name matches one (lawyer_display
        # prefers the FK, so keep both in sync).
        lawyer=Lawyer.objects.filter(name__iexact=lawyer_name).first() if lawyer_name else None,
        legal_approved_date=approved_date,
        legal_status=request.POST.get('legal_status', '').strip() or LegalCase.DEFAULT_STATUS,
        notes=request.POST.get('notes', '').strip(),
    )
    if request.user.is_authenticated:
        lc.created_by = request.user
    lc.save()
    return JsonResponse({'success': True, 'message': f'Legal case created for "{case.case_id}".'})


@require_POST
def legal_case_update(request):
    lc_id = request.POST.get('id', '').strip()
    lc = LegalCase.objects.filter(pk=lc_id).first() if lc_id else None
    if lc is None:
        return JsonResponse({'success': False, 'message': 'Legal case not found.'})

    approved_raw = request.POST.get('legal_approved_date', '').strip()
    approved_date = None
    if approved_raw:
        try:
            from datetime import date
            approved_date = date.fromisoformat(approved_raw)
        except ValueError:
            return JsonResponse({'success': False, 'message': 'Invalid approved date.'})

    lawyer_name = request.POST.get('lawyer_name', '').strip()
    lc.lawyer_name = lawyer_name
    # Keep the FK in sync with the chosen name (lawyer_display prefers the FK).
    lc.lawyer = Lawyer.objects.filter(name__iexact=lawyer_name).first() if lawyer_name else None
    lc.legal_approved_date = approved_date
    lc.legal_status = request.POST.get('legal_status', lc.legal_status)
    lc.notes = request.POST.get('notes', '').strip()
    lc.save(update_fields=['lawyer', 'lawyer_name', 'legal_approved_date', 'legal_status', 'notes'])
    return JsonResponse({'success': True, 'message': f'Legal case for "{lc.case.case_id}" updated.'})


@perm_required('legal_cases', 'delete')
@require_POST
def legal_case_delete(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'success': False, 'message': 'No legal cases selected.'})
    count = LegalCase.objects.filter(id__in=ids).count()
    LegalCase.objects.filter(id__in=ids).delete()
    return JsonResponse({'success': True, 'message': f'{count} legal case(s) deleted.'})


# ---------- FOLLOW UPS ----------
def _followup_type_options():
    """Selectable types for the Add Follow Up modals: the enabled types
    configured under Settings → Followup Types, or the legacy hardcoded
    choices when none are configured yet."""
    names = list(FollowupType.objects.filter(is_enabled=True).order_by('name').values_list('name', flat=True))
    return [(n, n) for n in names] if names else list(FollowUp.FOLLOW_UP_TYPE_CHOICES)


def _followup_filter_choices():
    """Types for the filter dropdowns: configured types plus any other values
    still present on existing follow-up records, so old rows stay filterable."""
    opts = _followup_type_options()
    seen = {v for v, _ in opts}
    legacy = dict(FollowUp.FOLLOW_UP_TYPE_CHOICES)
    used = FollowUp.objects.exclude(follow_up_type='').values_list('follow_up_type', flat=True).distinct()
    opts += [(v, legacy.get(v, v)) for v in sorted(used) if v not in seen]
    return opts


def follow_up_create(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    case_id = request.POST.get('case_id', '').strip()
    follow_up_type = request.POST.get('follow_up_type', '').strip() or 'call'
    follow_up_date = request.POST.get('follow_up_date', '').strip()
    followed_by_id = request.POST.get('followed_by_id', '').strip()
    case_status = request.POST.get('case_status', '').strip()
    is_legal = request.POST.get('is_legal', '0') == '1'
    notes = request.POST.get('notes', '').strip()
    if not case_id or not follow_up_date:
        return JsonResponse({'success': False, 'message': 'Case and date are required.'})
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Case not found.'})
    if not case_status:
        case_status = case.status
    fu = FollowUp.objects.create(
        case=case,
        follow_up_type=follow_up_type,
        follow_up_date=follow_up_date,
        followed_by_id=followed_by_id if followed_by_id else None,
        case_status=case_status,
        is_legal=is_legal,
        notes=notes,
    )
    # Update the Case's actual status to match the follow-up's recorded status
    if case_status and case.status != case_status:
        old_status = case.get_status_display()
        case.status = case_status
        # Promise to Pay needs a date; this form has none, so fall back to
        # the follow-up date rather than leaving the promise date empty.
        if case_status in Case.DATE_REQUIRED_STATUSES and not case.promise_to_pay_date:
            case.promise_to_pay_date = follow_up_date
        case.save(update_fields=['status', 'promise_to_pay_date'])
        _log_case(request, case, f'Case Status Changed to {case.get_status_display()}')
    _log_case(request, case, f'Case Followup Added ({fu.get_follow_up_type_display()})')
    return JsonResponse({'success': True, 'message': 'Follow up added successfully.', 'id': fu.id})


def follow_ups(request):
    collector_id = request.GET.get('collector', '')
    debtor_id = request.GET.get('debtor', '')
    client_id = request.GET.get('client', '')
    follow_up_type = request.GET.get('follow_up_type', '')
    is_legal = request.GET.get('is_legal', '')
    follow_up_date = request.GET.get('follow_up_date', '')

    qs = FollowUp.objects.select_related(
        'case__client', 'case__debtor', 'followed_by'
    ).order_by('-follow_up_date', '-created_at')

    if collector_id:
        qs = qs.filter(followed_by_id=collector_id)
    if debtor_id:
        qs = qs.filter(case__debtor_id=debtor_id)
    if client_id:
        qs = qs.filter(case__client_id=client_id)
    if follow_up_type:
        qs = qs.filter(follow_up_type=follow_up_type)
    if is_legal == '1':
        qs = qs.filter(is_legal=True)
    elif is_legal == '0':
        qs = qs.filter(is_legal=False)
    if follow_up_date:
        qs = qs.filter(follow_up_date=follow_up_date)

    return render(request, 'follow_ups.html', {
        'active_page': 'cases',
        'active_sub': 'follow_ups',
        'follow_ups': qs,
        'all_users': User.objects.filter(is_active=True).order_by('username'),
        'all_clients': Client.objects.filter(status='active').order_by('name'),
        'all_debtors': Debtor.objects.filter(status='active').order_by('name'),
        'all_cases': Case.objects.select_related('debtor').order_by('-created_at'),
        'type_choices': _followup_filter_choices(),
        'followup_type_options': _followup_type_options(),
        'status_choices': Case.all_status_choices(),
        'filter_collector': collector_id,
        'filter_debtor': debtor_id,
        'filter_client': client_id,
        'filter_type': follow_up_type,
        'filter_is_legal': is_legal,
        'filter_date': follow_up_date,
    })


def bulk_follow_ups(request):
    collector_id = request.GET.get('collector', '')
    debtor_id = request.GET.get('debtor', '')
    client_id = request.GET.get('client', '')
    follow_up_type = request.GET.get('follow_up_type', '')
    is_legal = request.GET.get('is_legal', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    qs = FollowUp.objects.select_related(
        'case__client', 'case__debtor', 'followed_by'
    ).order_by('-follow_up_date', '-created_at')

    if collector_id:
        qs = qs.filter(followed_by_id=collector_id)
    if debtor_id:
        qs = qs.filter(case__debtor_id=debtor_id)
    if client_id:
        qs = qs.filter(case__client_id=client_id)
    if follow_up_type:
        qs = qs.filter(follow_up_type=follow_up_type)
    if is_legal == '1':
        qs = qs.filter(is_legal=True)
    elif is_legal == '0':
        qs = qs.filter(is_legal=False)
    if date_from:
        qs = qs.filter(follow_up_date__gte=date_from)
    if date_to:
        qs = qs.filter(follow_up_date__lte=date_to)

    return render(request, 'bulk_follow_ups.html', {
        'active_page': 'cases',
        'active_sub': 'bulk_follow_ups',
        'follow_ups': qs,
        'all_users': User.objects.filter(is_active=True).order_by('username'),
        'all_clients': Client.objects.filter(status='active').order_by('name'),
        'all_debtors': Debtor.objects.filter(status='active').order_by('name'),
        'type_choices': _followup_filter_choices(),
        'filter_collector': collector_id,
        'filter_debtor': debtor_id,
        'filter_client': client_id,
        'filter_type': follow_up_type,
        'filter_is_legal': is_legal,
        'filter_date_from': date_from,
        'filter_date_to': date_to,
    })


def follow_up_export(request, format):
    qs = FollowUp.objects.select_related('case__client', 'case__debtor', 'followed_by').order_by('-follow_up_date', '-created_at')
    # Apply the same filters as the Follow Ups / Bulk Follow Ups pages so the
    # export matches what is on screen (the export links carry the query string).
    if request.GET.get('collector'):
        qs = qs.filter(followed_by_id=request.GET['collector'])
    if request.GET.get('debtor'):
        qs = qs.filter(case__debtor_id=request.GET['debtor'])
    if request.GET.get('client'):
        qs = qs.filter(case__client_id=request.GET['client'])
    if request.GET.get('follow_up_type'):
        qs = qs.filter(follow_up_type=request.GET['follow_up_type'])
    if request.GET.get('is_legal') == '1':
        qs = qs.filter(is_legal=True)
    elif request.GET.get('is_legal') == '0':
        qs = qs.filter(is_legal=False)
    if request.GET.get('follow_up_date'):
        qs = qs.filter(follow_up_date=request.GET['follow_up_date'])
    if request.GET.get('date_from'):
        qs = qs.filter(follow_up_date__gte=request.GET['date_from'])
    if request.GET.get('date_to'):
        qs = qs.filter(follow_up_date__lte=request.GET['date_to'])
    # The pages pass the exact rows currently visible on screen (after the
    # client-side quick search / merged view) so the export matches the view.
    if request.GET.get('ids'):
        id_list = [i for i in request.GET['ids'].split(',') if i.strip().isdigit()]
        if id_list:
            qs = qs.filter(pk__in=id_list)
    headers = ['Case ID', 'Client', 'Debtor', 'A/C No', 'Date', 'Type', 'Is Legal',
               'Followed By', 'Case Status', 'Notes']

    def _row(fu, notes):
        return [
            fu.case.case_id, fu.case.client.name, fu.case.debtor.name,
            fu.case.account_no or '—',
            fu.follow_up_date.strftime('%d-%b-%Y') if fu.follow_up_date else '—',
            fu.get_follow_up_type_display(),
            'Yes' if fu.is_legal else 'No',
            (fu.followed_by.get_full_name() or fu.followed_by.username) if fu.followed_by else '—',
            fu.get_case_status_display(),
            notes or '—',
        ]

    if request.GET.get('merged') == '1':
        # Merged VIEW export: one row per case, notes combined into date-wise
        # sections (newest first). Read-only — nothing is changed in the DB.
        grouped = {}
        for fu in qs:  # qs is ordered newest-first
            grouped.setdefault(fu.case_id, []).append(fu)
        rows = []
        for fus in grouped.values():
            parts = []
            for f in fus:
                note = (f.notes or '').strip()
                if note:
                    d = f.follow_up_date.strftime('%d-%b-%Y') if f.follow_up_date else '—'
                    parts.append(f'[{d}]\n{note}')
            rows.append(_row(fus[0], '\n\n'.join(parts)))
    else:
        rows = [_row(fu, fu.notes) for fu in qs]
    # Honour the on-screen column picker: cols=0,1,4 keeps only those header
    # positions (0-based over the headers list above).
    cols = request.GET.get('cols', '')
    if cols:
        keep = [int(c) for c in cols.split(',') if c.strip().isdigit() and int(c) < len(headers)]
        if keep:
            headers = [headers[i] for i in keep]
            rows = [[r[i] for i in keep] for r in rows]

    if format == 'csv':
        return _export_csv('follow_ups', headers, rows)
    if format == 'excel':
        return _export_excel('Follow Ups', headers, rows)
    if format == 'pdf':
        return _export_pdf('Follow Ups Report', headers, rows)
    return redirect('follow_ups')


@require_POST
def follow_ups_merge(request):
    """Merge several follow-ups of the SAME case into one entry. The newest
    entry survives; its notes become a chronological log where every original
    note is prefixed with its date (and type), e.g. "[05-Jun-2026 · Call] ..."."""
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if len(ids) < 2:
        return JsonResponse({'success': False, 'message': 'Select at least two follow ups to merge.'})
    fus = list(FollowUp.objects.filter(pk__in=ids).select_related('case').order_by('follow_up_date', 'created_at'))
    if len(fus) < 2:
        return JsonResponse({'success': False, 'message': 'Selected follow ups not found.'})
    if len({f.case_id for f in fus}) > 1:
        return JsonResponse({'success': False, 'message': 'Cannot merge: the selected follow ups belong to different cases.'})
    survivor = fus[-1]
    # Newest first, one section per date:
    # [05-Jun-2026]
    # Follow-up call made...
    #
    # [18-Mar-2026]
    # ...
    parts = []
    for f in reversed(fus):
        d = f.follow_up_date.strftime('%d-%b-%Y') if f.follow_up_date else '—'
        note = (f.notes or '').strip()
        if note:
            parts.append(f'[{d}]\n{note}')
    survivor.notes = '\n\n'.join(parts)
    survivor.save(update_fields=['notes'])
    FollowUp.objects.filter(pk__in=[f.pk for f in fus if f.pk != survivor.pk]).delete()
    return JsonResponse({'success': True, 'message': f'{len(fus)} follow ups merged into the {survivor.follow_up_date.strftime("%d-%b-%Y")} entry.'})


def case_group_create(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid method'}, status=405)
    name = request.POST.get('name', '').strip()
    collector_id = request.POST.get('collector_id', '').strip()
    if not name:
        return JsonResponse({'success': False, 'message': 'Group name is required.'})
    group = CaseGroup.objects.create(
        name=name,
        collector_id=collector_id if collector_id else None,
        created_by=request.user,
    )
    return JsonResponse({'success': True, 'message': f'Group "{group.name}" created.', 'id': group.id})


@require_POST
def case_group_remove_case(request):
    group_id = request.POST.get('group_id', '').strip()
    case_id  = request.POST.get('case_id', '').strip()
    try:
        group = CaseGroup.objects.get(pk=group_id)
        case  = Case.objects.get(pk=case_id)
    except (CaseGroup.DoesNotExist, Case.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'Group or case not found.'})
    group.cases.remove(case)
    return JsonResponse({'success': True, 'message': f'Case removed from group "{group.name}".'})


@require_POST
def case_group_add_case(request):
    group_id = request.POST.get('group_id', '').strip()
    case_id  = request.POST.get('case_id', '').strip()
    try:
        group = CaseGroup.objects.get(pk=group_id)
        case  = Case.objects.get(pk=case_id)
    except (CaseGroup.DoesNotExist, Case.DoesNotExist):
        return JsonResponse({'success': False, 'message': 'Group or case not found.'})
    # A group may only hold cases of a single client.
    existing_clients = set(group.cases.values_list('client_id', flat=True))
    if existing_clients and case.client_id not in existing_clients:
        return JsonResponse({'success': False, 'message': f'Cannot group: group "{group.name}" holds cases of a different client.'})
    group.cases.add(case)
    _log_case(request, case, f'Case Group Added to {group.name}')
    return JsonResponse({'success': True, 'message': f'Case "{case.case_id}" added to group "{group.name}".'})


def case_groups(request):
    collector_id  = request.GET.get('collector', '')
    debtor_id     = request.GET.get('debtor', '')
    client_id     = request.GET.get('client', '')
    agency_id     = request.GET.get('agency', '')
    status        = request.GET.get('status', '')
    received_date = request.GET.get('received_date', '')
    account_no    = request.GET.get('account_no', '').strip()

    case_qs = Case.objects.select_related('client', 'debtor', 'collector', 'case_type').order_by('case_id')
    if collector_id:
        case_qs = case_qs.filter(collector_id=collector_id)
    if debtor_id:
        case_qs = case_qs.filter(debtor_id=debtor_id)
    if client_id:
        case_qs = case_qs.filter(client_id=client_id)
    if agency_id:
        case_qs = case_qs.filter(client_id=agency_id)
    if status:
        case_qs = case_qs.filter(status=status)
    if received_date:
        case_qs = case_qs.filter(received_date=received_date)
    if account_no:
        case_qs = case_qs.filter(Q(account_no__icontains=account_no) | Q(case_id__icontains=account_no))

    groups_qs = CaseGroup.objects.prefetch_related(
        Prefetch('cases', queryset=case_qs, to_attr='filtered_cases')
    ).order_by('-created_at')

    rows = []
    for group in groups_qs:
        cases = list(group.filtered_cases)
        if not cases:
            continue
        # Cases in a group can be in different currencies (AED, USD, ...), so the
        # group total must be summed in OMR, not each case's own currency.
        group_total = sum(c.remaining_amount_omr for c in cases)
        for i, case in enumerate(cases):
            rows.append({
                'group': group,
                'case': case,
                'is_first': i == 0,
                'is_last': i == len(cases) - 1,
                'rowspan': len(cases),
                'group_total': group_total,
                'group_cases': cases,
            })

    return render(request, 'case_groups.html', {
        'active_page': 'cases',
        'active_sub': 'case_groups',
        'rows': rows,
        'all_users': User.objects.filter(is_active=True).order_by('username'),
        'all_clients': Client.objects.filter(status='active').order_by('name'),
        'all_debtors': Debtor.objects.filter(status='active').order_by('name'),
        'all_cases': Case.objects.select_related('debtor').order_by('-created_at')[:500],
        'all_agencies': Client.objects.filter(client_type='agency', status='active').order_by('name'),
        'status_choices': Case.all_status_choices(),
        'payment_modes': PaymentMode.objects.filter(is_enabled=True).order_by('name'),
        'currencies': enabled_currencies(),
        'followup_type_options': _followup_type_options(),
        'filter_collector': collector_id,
        'filter_debtor': debtor_id,
        'filter_client': client_id,
        'filter_agency': agency_id,
        'filter_status': status,
        'filter_received_date': received_date,
        'filter_account_no': account_no,
    })


def case_group_detail(request, pk):
    group = get_object_or_404(
        CaseGroup.objects.prefetch_related(
            Prefetch('cases', queryset=Case.objects.select_related(
                'client', 'debtor', 'collector', 'case_type', 'currency'
            ).prefetch_related(
                Prefetch('payments', queryset=Payment.objects.select_related('received_currency', 'collection_currency'))
            ).order_by('case_id'))
        ),
        pk=pk,
    )
    cases = list(group.cases.all())
    case_pks = [c.pk for c in cases]

    fin_rows = []
    total_os_omr = total_approved_omr = 0.0
    for c in cases:
        rate = float(c.currency.value) if c.currency and c.currency.value else 1
        os_omr       = c.remaining_amount_omr
        approved_omr = float(c.approved_amount) / rate if rate else float(c.approved_amount)
        total_os_omr       += os_omr
        total_approved_omr += approved_omr
        fin_rows.append({
            'case': c,
            'currency_code': c.currency.code if c.currency else 'OMR',
            'os_amt': c.remaining_amount,
            'os_omr': os_omr,
            'approved_omr': approved_omr,
        })

    follow_ups = FollowUp.objects.filter(case_id__in=case_pks).select_related(
        'case', 'followed_by').order_by('-follow_up_date', '-created_at')
    reminders = Reminder.objects.filter(case_id__in=case_pks).select_related(
        'case', 'created_by').prefetch_related('other_users').order_by('-reminder_date')
    history = CaseHistory.objects.filter(case_id__in=case_pks).select_related(
        'case', 'action_by').order_by('-created_at')[:200]

    return render(request, 'case_group_detail.html', {
        'active_page': 'cases',
        'active_sub': 'case_groups',
        'group': group,
        'cases': cases,
        'fin_rows': fin_rows,
        'total_os_omr': total_os_omr,
        'total_approved_omr': total_approved_omr,
        'follow_ups': follow_ups,
        'reminders': reminders,
        'history': history,
        'payment_modes': PaymentMode.objects.filter(is_enabled=True).order_by('name'),
        'currencies': enabled_currencies(),
    })


def pending_payments(request):
    collector_id = request.GET.get('collector', '')
    debtor_id = request.GET.get('debtor', '')
    client_id = request.GET.get('client', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Approving/rejecting doesn't yank the row away immediately — it stays
    # listed (now showing Approved/Rejected) for 1 day so the action is still
    # visible right after you take it, then quietly drops off this list on its
    # own. Nothing about the payment itself is ever deleted.
    cutoff = timezone.now() - timedelta(days=1)
    # Installments aren't real payments yet — they only belong here once
    # "moved to payment" (which flips is_installment to False).
    qs = Payment.objects.filter(is_installment=False).filter(
        Q(status='pending') | Q(status__in=['cleared', 'bounced'], completed_at__gte=cutoff)
    ).select_related(
        'case__client', 'case__debtor', 'case__collector', 'created_by'
    ).order_by('-payment_date', '-created_at')

    if collector_id:
        qs = qs.filter(case__collector_id=collector_id)
    if debtor_id:
        qs = qs.filter(case__debtor_id=debtor_id)
    if client_id:
        qs = qs.filter(case__client_id=client_id)
    if date_from:
        qs = qs.filter(payment_date__gte=date_from)
    if date_to:
        qs = qs.filter(payment_date__lte=date_to)

    payments = list(qs)
    still_pending_count = sum(1 for p in payments if p.status == 'pending')

    return render(request, 'pending_payments.html', {
        'active_page': 'cases',
        'active_sub': 'pending_payments',
        'payments': payments,
        'still_pending_count': still_pending_count,
        'all_users': User.objects.filter(is_active=True).order_by('username'),
        'all_clients': Client.objects.filter(status='active').order_by('name'),
        'all_debtors': Debtor.objects.filter(status='active').order_by('name'),
        'filter_collector': collector_id,
        'filter_debtor': debtor_id,
        'filter_client': client_id,
        'filter_date_from': date_from,
        'filter_date_to': date_to,
    })


# ---------- DEBTOR CONTACTS ----------
def debtor_contacts(request):
    filter_q = request.GET.get('filter', '')
    email_q  = request.GET.get('email', '')
    debtor_id = request.GET.get('debtor', '')

    # Backfill: auto-create primary contacts for debtors that have phone/email but no contacts yet
    for d in Debtor.objects.filter(contacts__isnull=True).filter(
        Q(phone__gt='') | Q(telephone__gt='') | Q(email__gt='')
    ):
        _sync_debtor_primary_contact(d)

    qs = DebtorContact.objects.select_related('debtor').order_by(Lower('debtor__name'), Lower('name'))
    if filter_q:
        qs = qs.filter(name__icontains=filter_q)
    if email_q:
        qs = qs.filter(email__icontains=email_q)
    if debtor_id:
        qs = qs.filter(debtor_id=debtor_id)

    return render(request, 'debtor_contacts.html', {
        'active_page': 'debtors',
        'active_sub': 'debtors_contacts',
        'contacts': qs,
        'all_debtors': Debtor.objects.order_by('name'),
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
        'filter_q': filter_q,
        'email_q': email_q,
        'selected_debtor': debtor_id,
    })


@require_POST
def debtor_contact_create(request):
    debtor_id = request.POST.get('debtor_id', '').strip()
    name = request.POST.get('name', '').strip()
    if not debtor_id or not name:
        return JsonResponse({'success': False, 'message': 'Debtor and contact name are required.'})
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    if not _valid_email(email):
        return JsonResponse({'success': False, 'message': 'Please enter a valid email address.'})
    if not _valid_phone(phone):
        return JsonResponse({'success': False, 'message': 'Please enter a valid phone number (country code + number).'})
    try:
        debtor = Debtor.objects.get(pk=debtor_id)
    except Debtor.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Invalid debtor.'})

    DebtorContact.objects.create(
        debtor=debtor,
        name=name,
        contact_type=request.POST.get('contact_type', 'other'),
        email=email,
        phone=phone,
        enabled=request.POST.get('enabled', 'true') == 'true',
    )
    return JsonResponse({'success': True, 'message': f'Contact "{name}" added to {debtor.name}.'})


@admin_required
@require_POST
def debtor_contact_delete(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'success': False, 'message': 'No contacts selected.'})
    count = DebtorContact.objects.filter(id__in=ids).count()
    DebtorContact.objects.filter(id__in=ids).delete()
    return JsonResponse({'success': True, 'message': f'{count} contact(s) deleted.'})


@admin_required
def debtor_contact_export(request, format):
    qs = DebtorContact.objects.select_related('debtor').order_by('-created_at')
    headers = ['Contact Name', 'Contact Type', 'Debtor', 'Email', 'Phone', 'Enabled', 'Created At']
    rows = [
        [c.name, c.get_contact_type_display(), c.debtor.name,
         c.email, c.phone, 'Yes' if c.enabled else 'No',
         c.created_at.strftime('%d-%b-%Y')]
        for c in qs
    ]
    if format == 'csv':
        return _export_csv('debtor_contacts', headers, rows)
    if format == 'excel':
        return _export_excel('Debtor Contacts', headers, rows)
    if format == 'pdf':
        return _export_pdf('Debtor Contacts Report', headers, rows)
    return redirect('debtor_contacts')


@admin_required
def debtor_name_suggest(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    qs = Debtor.objects.filter(name__icontains=q).order_by('name')[:8]
    return JsonResponse({'results': [
        {'id': d.id, 'name': d.name, 'debtor_id': d.debtor_id, 'is_organization': d.is_organization}
        for d in qs
    ]})


# ---------- DEBTOR DUPLICATES ----------
def debtor_duplicates(request):
    from collections import defaultdict
    import unicodedata, re

    def normalize(name):
        name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
        return re.sub(r'\s+', ' ', name.strip().lower())

    all_debtors = list(Debtor.objects.annotate(total_cases=Count('cases')).order_by('name'))
    groups = defaultdict(list)
    for d in all_debtors:
        groups[normalize(d.name)].append(d)

    duplicate_groups = [g for g in groups.values() if len(g) > 1]
    duplicate_groups.sort(key=lambda g: g[0].name.lower())

    return render(request, 'debtor_duplicates.html', {
        'active_page': 'debtors',
        'active_sub': 'duplicates',
        'duplicate_groups': duplicate_groups,
        'total_duplicates': sum(len(g) - 1 for g in duplicate_groups),
    })


@admin_required
@require_POST
def debtor_duplicates_merge(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if len(ids) < 2:
        return JsonResponse({'success': False, 'message': 'Select at least 2 debtors to merge.'})
    qs = Debtor.objects.filter(id__in=ids).order_by('created_at')
    primary = qs.first()
    others = qs.exclude(pk=primary.pk)
    Case.objects.filter(debtor__in=others).update(debtor=primary)
    DebtorContact.objects.filter(debtor__in=others).update(debtor=primary)
    deleted = others.count()
    others.delete()
    return JsonResponse({'success': True, 'message': f'Merged {deleted} duplicate(s) into "{primary.name}".'})


# ---------- PAYMENTS ----------
def payments(request):
    filter_q = request.GET.get('filter', '')
    method_filter = request.GET.get('method', '')
    status_filter = request.GET.get('status', '')

    qs = Payment.objects.select_related(
        'case__client', 'case__debtor', 'created_by'
    ).order_by('-payment_date', '-created_at')

    if filter_q:
        qs = qs.filter(
            Q(payment_id__icontains=filter_q) |
            Q(case__case_id__icontains=filter_q) |
            Q(case__client__name__icontains=filter_q) |
            Q(case__debtor__name__icontains=filter_q) |
            Q(reference_number__icontains=filter_q) |
            Q(cheque_number__icontains=filter_q)
        )
    if method_filter:
        qs = qs.filter(payment_method=method_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)

    total_amount = qs.aggregate(total=Sum('amount'))['total'] or 0

    return render(request, 'payments.html', {
        'active_page': 'payments',
        'active_sub': 'all_payments',
        'payments': qs,
        'filter_q': filter_q,
        'method_filter': method_filter,
        'status_filter': status_filter,
        'total_amount': total_amount,
        'all_cases': Case.objects.select_related('client', 'debtor').order_by('-created_at'),
        'method_choices': Payment.METHOD_CHOICES,
        'status_choices': Payment.STATUS_CHOICES,
    })


def _recalc_case_received(case):
    """Refresh the denormalised case.received_amount from payments.

    Only APPROVED (status='cleared') payments count as money received —
    pending and rejected payments stay listed on the case but are excluded
    from the total (and from everything derived from it: dashboards, case
    lists, remaining-amount, reports)."""
    from django.db.models import Sum as _S
    case.received_amount = (
        case.payments.filter(status='cleared').aggregate(t=_S('received_amount'))['t'] or 0
    )
    case.save(update_fields=['received_amount'])


@require_POST
def payment_create_modal(request):
    case_id      = request.POST.get('case_id', '').strip()
    amount       = request.POST.get('amount', '').strip()
    payment_date = request.POST.get('payment_date', '').strip()

    if not case_id or not amount or not payment_date:
        return JsonResponse({'success': False, 'message': 'Case, collection amount, and date are required.'})

    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Invalid case selected.'})

    try:
        amount_val = float(amount)
        if amount_val <= 0:
            raise ValueError
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Amount must be a positive number.'})

    def _date_or_none(key):
        v = request.POST.get(key, '').strip()
        return v if v else None

    def _fk_or_none(model, key):
        v = request.POST.get(key, '').strip()
        if not v:
            return None
        try:
            return model.objects.get(pk=v)
        except model.DoesNotExist:
            return None

    recv_amount_raw = request.POST.get('received_amount', '').strip()
    recv_amount_val = float(recv_amount_raw) if recv_amount_raw else None

    # "Move to Payment": convert an existing installment into a real payment
    # (keeps the same record/payment_id instead of creating a duplicate).
    from_installment = request.POST.get('from_installment', '').strip()
    payment = None
    moved = False
    if from_installment:
        payment = Payment.objects.filter(pk=from_installment, case=case, is_installment=True).first()
        if payment:
            payment.is_installment = False
            moved = True
    if payment is None:
        payment = Payment(case=case)

    payment.amount = amount_val
    payment.payment_date = payment_date
    payment.payment_mode = _fk_or_none(PaymentMode, 'payment_mode_id')
    payment.collection_currency = _fk_or_none(Currency, 'collection_currency_id')
    payment.transfer_date = _date_or_none('transfer_date')
    payment.received_date = _date_or_none('received_date')
    payment.received_currency = _fk_or_none(Currency, 'received_currency_id')
    payment.received_amount = recv_amount_val
    payment.confirmation_date = _date_or_none('confirmation_date')
    payment.reference_number = request.POST.get('reference_number', '').strip()
    cheque = request.POST.get('cheque_number', '').strip()
    if cheque or not moved:
        payment.cheque_number = cheque
    payment.bank_name = request.POST.get('bank_name', '').strip()
    payment.status = request.POST.get('status', 'pending')
    payment.notes = request.POST.get('notes', '').strip()
    if request.user.is_authenticated and not payment.created_by_id:
        payment.created_by = request.user
    payment.save()

    _recalc_case_received(case)

    action = 'Installment Moved to Payment' if moved else 'Case Payment Added'
    _log_case(request, case, f'{action} ({payment.payment_id})')

    verb = 'moved to' if moved else 'recorded as'
    return JsonResponse({
        'success': True,
        'message': f'Installment {verb} payment "{payment.payment_id}" of {amount_val:.3f}.' if moved
                   else f'Payment "{payment.payment_id}" of {amount_val:.3f} recorded successfully.',
    })


@require_POST
def group_payment_create(request):
    """One payment recorded across several cases of a group: the shared fields
    (mode, dates, currencies, notes) are the same, and the collection amount is
    allocated per selected case (installment-style). A received amount, if
    given, is split proportionally to each case's allocation."""
    payment_date = request.POST.get('payment_date', '').strip()
    if not payment_date:
        return JsonResponse({'success': False, 'message': 'Collection date is required.'})

    case_ids = request.POST.getlist('case_ids[]')
    amounts  = request.POST.getlist('case_amounts[]')
    allocs, total = [], 0.0
    for cid, amt in zip(case_ids, amounts):
        try:
            a = float(amt)
        except (TypeError, ValueError):
            a = 0
        if a > 0:
            allocs.append((cid, a))
            total += a
    if not allocs:
        return JsonResponse({'success': False, 'message': 'Select at least one case and enter its amount.'})

    def _date_or_none(key):
        v = request.POST.get(key, '').strip()
        return v if v else None

    def _fk_or_none(model, key):
        v = request.POST.get(key, '').strip()
        if not v:
            return None
        try:
            return model.objects.get(pk=v)
        except model.DoesNotExist:
            return None

    recv_raw = request.POST.get('received_amount', '').strip()
    recv_total = float(recv_raw) if recv_raw else None

    mode          = _fk_or_none(PaymentMode, 'payment_mode_id')
    col_currency  = _fk_or_none(Currency, 'collection_currency_id')
    recv_currency = _fk_or_none(Currency, 'received_currency_id')
    notes = request.POST.get('notes', '').strip()

    from django.db.models import Sum as _S
    created = []
    for cid, a in allocs:
        case = Case.objects.filter(pk=cid).first()
        if case is None:
            continue
        p = Payment(
            case=case, amount=a, payment_date=payment_date,
            payment_mode=mode, collection_currency=col_currency,
            transfer_date=_date_or_none('transfer_date'),
            received_date=_date_or_none('received_date'),
            received_currency=recv_currency,
            received_amount=round(recv_total * a / total, 3) if recv_total else None,
            confirmation_date=_date_or_none('confirmation_date'),
            notes=notes,
            created_by=request.user if request.user.is_authenticated else None,
        )
        p.save()
        _recalc_case_received(case)
        _log_case(request, case, f'Case Payment Added ({p.payment_id}) — group payment')
        created.append(p.payment_id)

    if not created:
        return JsonResponse({'success': False, 'message': 'No valid cases found.'})
    return JsonResponse({'success': True, 'message': f'{len(created)} payment(s) of {total:.3f} total recorded.'})


@require_POST
def payment_update(request):
    payment_id = request.POST.get('payment_pk', '').strip()
    amount       = request.POST.get('amount', '').strip()
    payment_date = request.POST.get('payment_date', '').strip()

    if not payment_id:
        return JsonResponse({'success': False, 'message': 'Payment not specified.'})
    if not amount or not payment_date:
        return JsonResponse({'success': False, 'message': 'Collection amount and date are required.'})

    try:
        payment = Payment.objects.select_related('case').get(pk=payment_id)
    except Payment.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Payment not found.'})

    try:
        amount_val = float(amount)
        if amount_val <= 0:
            raise ValueError
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Amount must be a positive number.'})

    def _date_or_none(key):
        v = request.POST.get(key, '').strip()
        return v if v else None

    def _fk_or_none(model, key):
        v = request.POST.get(key, '').strip()
        if not v:
            return None
        try:
            return model.objects.get(pk=v)
        except model.DoesNotExist:
            return None

    recv_amount_raw = request.POST.get('received_amount', '').strip()

    payment.amount              = amount_val
    payment.payment_date        = payment_date
    payment.payment_mode        = _fk_or_none(PaymentMode, 'payment_mode_id')
    payment.collection_currency = _fk_or_none(Currency, 'collection_currency_id')
    payment.transfer_date       = _date_or_none('transfer_date')
    payment.received_date       = _date_or_none('received_date')
    payment.received_currency   = _fk_or_none(Currency, 'received_currency_id')
    payment.received_amount     = float(recv_amount_raw) if recv_amount_raw else None
    payment.confirmation_date   = _date_or_none('confirmation_date')
    payment.notes               = request.POST.get('notes', '').strip()
    payment.save()

    case = payment.case
    _recalc_case_received(case)

    _log_case(request, case, f'Case Payment Updated ({payment.payment_id})')

    return JsonResponse({
        'success': True,
        'message': f'Payment "{payment.payment_id}" updated successfully.',
    })


def payment_receipt(request, pk):
    from django.http import Http404
    try:
        payment = Payment.objects.select_related(
            'case__client', 'case__debtor', 'payment_mode',
            'collection_currency', 'received_currency', 'created_by',
        ).get(pk=pk)
    except Payment.DoesNotExist:
        raise Http404('Payment not found')

    if not payment.can_download_receipt:
        return HttpResponse(
            'Receipts are only available for Tawazon payment modes '
            f'({", ".join(Payment.RECEIPT_MODES)}).', status=403)

    from .receipt import build_payment_receipt, receipt_verify_token
    # Pin the QR to the canonical public domain when configured — otherwise a
    # receipt downloaded via an internal IP / temporary tunnel would embed a
    # URL that outsiders can never reach.
    verify_path = reverse('receipt_verify', args=[payment.pk, receipt_verify_token(payment)])
    base = getattr(settings, 'RECEIPT_VERIFY_BASE_URL', '').rstrip('/')
    verify_url = (base + verify_path) if base else request.build_absolute_uri(verify_path)
    pdf = build_payment_receipt(payment, verify_url=verify_url)

    resp = HttpResponse(pdf, content_type='application/pdf')
    fname = (payment.receipt_no or f'payment-{payment.pk}').replace('/', '-')
    resp['Content-Disposition'] = f'attachment; filename="receipt_{fname}.pdf"'
    return resp


def receipt_verify_lookup(request):
    """Manual fallback when the QR cannot be scanned: enter the receipt number
    and the printed CODE, get sent to the same verification page."""
    from .receipt import receipt_verify_token
    import hmac as _hmac
    receipt_no = request.GET.get('receipt_no', '').strip().upper()
    code = request.GET.get('code', '').replace('-', '').replace(' ', '').strip().upper()
    error = ''
    if receipt_no or code:
        payment_id = receipt_no.replace('/RPT/', '/PAY/')
        payment = Payment.objects.filter(payment_id__iexact=payment_id).first()
        if payment and _hmac.compare_digest(receipt_verify_token(payment), code):
            return redirect('receipt_verify', pk=payment.pk, token=code)
        error = 'No authentic receipt matches that number and code. Check both and try again.'
    return render(request, 'receipt_verify_lookup.html', {'error': error, 'receipt_no': receipt_no})


def receipt_verify(request, pk, token):
    """Public page behind the receipt's verification QR: shows the authentic
    payment figures from the database so anyone can compare them against a
    printed/PDF receipt and spot tampering. The token is an HMAC over the
    server secret, so a valid URL cannot be fabricated for fake data."""
    from .receipt import receipt_verify_token
    import hmac as _hmac
    payment = Payment.objects.select_related(
        'case__client', 'case__debtor', 'payment_mode', 'collection_currency'
    ).filter(pk=pk).first()
    valid = bool(payment) and _hmac.compare_digest(receipt_verify_token(payment), token)
    amount_omr = None
    if valid:
        cur = payment.collection_currency
        rate = float(cur.value) if cur and cur.value else 1
        amount_omr = float(payment.amount or 0) / rate if rate else float(payment.amount or 0)
    return render(request, 'receipt_verify.html', {
        'valid': valid,
        'payment': payment if valid else None,
        'amount_omr': amount_omr,
        'cancelled': valid and payment.status == 'bounced',
    })


@require_POST
def installment_bulk_create(request):
    case_id = request.POST.get('case_id', '').strip()
    amounts = request.POST.getlist('amounts')
    dates   = request.POST.getlist('dates')
    checks  = request.POST.getlist('checks')
    methods = request.POST.getlist('methods')

    if not case_id or not amounts or not dates or len(amounts) != len(dates):
        return JsonResponse({'success': False, 'message': 'Case, amounts, and dates are required.'})

    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Case not found.'})

    valid_methods = dict(Payment.INSTALLMENT_METHOD_CHOICES)
    created = []
    for i, (amt, dt) in enumerate(zip(amounts, dates)):
        try:
            amount_val = float(amt)
            if amount_val <= 0:
                raise ValueError
        except ValueError:
            return JsonResponse({'success': False, 'message': f'Invalid amount: {amt}'})
        if not dt:
            return JsonResponse({'success': False, 'message': 'All installment dates are required.'})
        method = methods[i].strip() if i < len(methods) else 'direct'
        if method not in valid_methods:
            method = 'direct'
        p = Payment(
            case=case,
            amount=amount_val,
            payment_date=dt,
            cheque_number=checks[i].strip() if i < len(checks) else '',
            payment_method=method,
            status='pending',
            is_installment=True,
        )
        if request.user.is_authenticated:
            p.created_by = request.user
        p.save()
        created.append(p)

    n = len(created)
    _log_case(request, case, f'{n} Installment{"s" if n != 1 else ""} Added')
    return JsonResponse({'success': True, 'message': f'{n} installment{"s" if n != 1 else ""} created successfully.'})


@require_POST
def installment_update(request):
    pk = request.POST.get('payment_pk', '').strip()
    amount = request.POST.get('amount', '').strip()
    payment_date = request.POST.get('payment_date', '').strip()

    if not pk:
        return JsonResponse({'success': False, 'message': 'Installment not specified.'})
    if not amount or not payment_date:
        return JsonResponse({'success': False, 'message': 'Amount and date are required.'})

    try:
        payment = Payment.objects.get(pk=pk, is_installment=True)
    except Payment.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Installment not found.'})

    try:
        amount_val = float(amount)
        if amount_val <= 0:
            raise ValueError
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Amount must be a positive number.'})

    method = request.POST.get('payment_method', '').strip()
    status = request.POST.get('status', '').strip()
    payment.amount = amount_val
    payment.payment_date = payment_date
    payment.cheque_number = request.POST.get('cheque_number', '').strip()
    if method in dict(Payment.INSTALLMENT_METHOD_CHOICES):
        payment.payment_method = method
    if status in dict(Payment.STATUS_CHOICES):
        payment.status = status
    payment.save()
    _log_case(request, payment.case, f'Installment Updated ({payment.payment_id})')
    return JsonResponse({'success': True, 'message': f'Installment "{payment.payment_id}" updated successfully.'})


@perm_required('payments', 'delete')
@require_POST
def payment_delete(request):
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    if not ids:
        return JsonResponse({'success': False, 'message': 'No payments selected.'})
    qs = Payment.objects.filter(id__in=ids)
    case_ids = list(qs.values_list('case_id', flat=True).distinct())
    count = qs.count()
    qs.delete()
    for cid in case_ids:
        _recalc_case_received(Case.objects.get(pk=cid))
    return JsonResponse({'success': True, 'message': f'{count} payment(s) deleted successfully.'})


@require_POST
def payment_confirm(request):
    """Approve or reject a pending payment from Collection Confirmation (admin only)."""
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'message': 'Only an admin can approve or reject payments.'})
    pk = request.POST.get('payment_pk', '').strip()
    action = request.POST.get('action', '').strip()
    if action not in ('approve', 'reject'):
        return JsonResponse({'success': False, 'message': 'Invalid action.'})
    payment = Payment.objects.filter(pk=pk).select_related('case').first()
    if not payment:
        return JsonResponse({'success': False, 'message': 'Payment not found.'})
    if payment.status != 'pending':
        return JsonResponse({'success': False, 'message': 'This payment has already been actioned.'})
    payment.status = 'cleared' if action == 'approve' else 'bounced'
    payment.completed_at = timezone.now()
    update_fields = ['status', 'completed_at']
    if action == 'approve' and not payment.confirmation_date:
        payment.confirmation_date = timezone.localdate()
        update_fields.append('confirmation_date')
    payment.save(update_fields=update_fields)
    # Approving/rejecting changes what counts as received — refresh the total.
    _recalc_case_received(payment.case)
    label = 'Approved' if action == 'approve' else 'Rejected'
    _log_case(request, payment.case, f'Payment {label} ({payment.payment_id})')
    return JsonResponse({'success': True, 'message': f'Payment {payment.payment_id} {label.lower()}.'})


def payment_export(request, format):
    qs = Payment.objects.select_related('case__client', 'case__debtor', 'created_by').order_by('-payment_date')
    headers = ['Payment ID', 'Case ID', 'Client', 'Debtor', 'Amount (OMR)', 'Payment Date',
               'Method', 'Reference No.', 'Cheque No.', 'Bank', 'Status', 'Notes', 'Created By']
    rows = [
        [
            p.payment_id, p.case.case_id, p.case.client.name, p.case.debtor.name,
            p.amount, p.payment_date.strftime('%Y-%m-%d'),
            p.get_payment_method_display(), p.reference_number, p.cheque_number, p.bank_name,
            p.get_status_display(), p.notes,
            p.created_by.get_full_name() or p.created_by.username if p.created_by else '—',
        ]
        for p in qs
    ]
    if format == 'csv':
        return _export_csv('payments', headers, rows)
    if format == 'excel':
        return _export_excel('Payments', headers, rows)
    if format == 'pdf':
        return _export_pdf('Payments Report', headers, rows)
    return redirect('payments')


# ---------- EXPORT HELPERS ----------
#
# Every export in the app funnels through these three functions. The row cap
# below is the single guard that stops one huge "export everything" click from
# tying up a gunicorn worker (and its RAM) for many seconds while it serializes
# a spreadsheet/PDF — which is what would make the dashboard feel slow for
# everyone else. Over the cap we refuse with a clear message instead of
# silently truncating (a partial export the user thinks is complete is worse
# than no export). Raise EXPORT_MAX_ROWS via env var if a bigger box can
# afford it; better still, filter the list before exporting.
_EXPORT_MAX_ROWS = int(os.environ.get('EXPORT_MAX_ROWS', '25000'))
# PDF layout is much heavier per row than CSV/Excel, so it gets a tighter cap.
_EXPORT_PDF_MAX_ROWS = int(os.environ.get('EXPORT_PDF_MAX_ROWS', '5000'))


def _export_too_big(rows, limit):
    """Return an HttpResponse to send back if `rows` is over `limit`, else None."""
    n = len(rows)
    if n <= limit:
        return None
    resp = HttpResponse(
        f"This export has {n:,} rows, over the {limit:,}-row limit.\n\n"
        f"Filter the list first (by status, client, date, collector, …) and "
        f"export the smaller result. This keeps the dashboard fast for everyone "
        f"while a big file is being built.",
        content_type='text/plain',
        status=413,
    )
    return resp


class _Echo:
    """A file-like object that just returns what's written — lets csv.writer
    feed StreamingHttpResponse row by row instead of buffering the whole file."""
    def write(self, value):
        return value


def _export_csv(filename, headers, rows):
    too_big = _export_too_big(rows, _EXPORT_MAX_ROWS)
    if too_big:
        return too_big
    writer = csv.writer(_Echo())

    def _stream():
        yield writer.writerow(headers)
        for row in rows:
            yield writer.writerow(row)

    response = StreamingHttpResponse(_stream(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    return response


def _export_excel(sheet_name, headers, rows):
    too_big = _export_too_big(rows, _EXPORT_MAX_ROWS)
    if too_big:
        return too_big
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    header_font = Font(bold=True, color='FFFFFF', size=12)
    header_fill = PatternFill(start_color='2E7D32', end_color='2E7D32', fill_type='solid')
    center = Alignment(horizontal='center', vertical='center')

    ws.append(headers)
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center

    for row in rows:
        ws.append(row)

    for col_idx, _ in enumerate(headers, 1):
        max_len = max(
            [len(str(headers[col_idx-1]))] +
            [len(str(r[col_idx-1])) for r in rows if col_idx-1 < len(r)]
        )
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max_len + 4

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{sheet_name.lower().replace(" ", "_")}.xlsx"'
    return response


def _export_pdf(title, headers, rows, col_widths=None):
    too_big = _export_too_big(rows, _EXPORT_PDF_MAX_ROWS)
    if too_big:
        return too_big
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buffer = io.BytesIO()
    # usable width on landscape A4 with 20pt margins each side ≈ 802pt
    left_margin = right_margin = 20
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=30, bottomMargin=30,
        leftMargin=left_margin, rightMargin=right_margin,
    )
    page_width = landscape(A4)[0] - left_margin - right_margin  # ~802pt

    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle(
        'cell', fontName='Helvetica', fontSize=7,
        leading=9, wordWrap='CJK', spaceAfter=0, spaceBefore=0,
    )
    hdr_style = ParagraphStyle(
        'hdr', fontName='Helvetica-Bold', fontSize=8,
        leading=10, textColor=colors.whitesmoke,
        wordWrap='CJK', spaceAfter=0, spaceBefore=0,
    )

    elements = []
    elements.append(Paragraph(f"<b>{title}</b>", styles['Title']))
    elements.append(Spacer(1, 10))

    # Build data with Paragraph objects for text wrapping
    header_row = [Paragraph(str(h), hdr_style) for h in headers]
    data_rows  = [
        [Paragraph(str(cell) if str(cell) != 'None' else '—', cell_style) for cell in row]
        for row in rows
    ]
    data = [header_row] + data_rows

    # Auto-distribute widths if not provided
    if col_widths is None:
        col_w = page_width / len(headers)
        col_widths = [col_w] * len(headers)

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E7D32')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('LEFTPADDING',  (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING',   (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{title.lower().replace(" ", "_")}.pdf"'
    return response


# ---------- REPORTS ----------
def case_status_report(request):
    # New filter params (matching live screenshot)
    collector_id  = request.GET.get('collector', '')
    client_id     = request.GET.get('client', '')
    debtor_id     = request.GET.get('debtor', '')
    date_from     = request.GET.get('date_from', '')
    date_to       = request.GET.get('date_to', '')
    agency_id     = request.GET.get('agency', '')
    lawyer_name   = request.GET.get('lawyer', '')
    case_status   = request.GET.get('case_status', '')
    # legacy compat
    statuses = [case_status] if case_status else request.GET.getlist('status')
    amount_from = request.GET.get('amount_from', '')
    filter_country = request.GET.get('country', '')
    debtor_name_q = request.GET.get('debtor_name', '')

    date_range = ''
    if date_from and date_to:
        date_range = f'{date_from} to {date_to}'
    elif date_from:
        date_range = date_from

    qs = _scope_cases_to_staff(request, Case.objects.select_related('client', 'debtor', 'collector'))

    if statuses:
        qs = qs.filter(status__in=statuses)
    if collector_id:
        qs = qs.filter(collector_id=collector_id)
    if client_id:
        qs = qs.filter(client_id=client_id)
    if debtor_id:
        qs = qs.filter(debtor_id=debtor_id)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if agency_id:
        qs = qs.filter(agency_id=agency_id)
    if lawyer_name:
        qs = qs.filter(legal_case__isnull=False).filter(
            Q(legal_case__lawyer__name=lawyer_name) | Q(legal_case__lawyer_name=lawyer_name)
        )
    if amount_from:
        try:
            qs = qs.filter(approved_amount__gte=Decimal(amount_from))
        except InvalidOperation:
            pass
    if filter_country:
        qs = qs.filter(debtor__country__icontains=filter_country)
    if debtor_name_q:
        qs = qs.filter(debtor__first_name__icontains=debtor_name_q)

    def build_stats(sub_qs):
        agg = sub_qs.aggregate(
            count=Count('id'),
            approved=Sum('approved_amount'),
            received=Sum('received_amount'),
        )
        count = agg['count'] or 0
        approved = float(agg['approved'] or 0)
        received = float(agg['received'] or 0)
        open_count = sub_qs.exclude(status__in=['closed', 'closed_by_client']).count()
        return {
            'count': count,
            'open': open_count,
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        }

    def make_chart(rows, label_key='label'):
        labels = [r[label_key] for r in rows if r['count'] > 0]
        values = [r['count'] for r in rows if r['count'] > 0]
        return json.dumps({'labels': labels, 'values': values})

    # Overall
    overall = build_stats(qs)
    status_labels_map = dict(Case.all_status_choices())
    status_breakdown = []
    for sv, sl in Case.all_status_choices():
        c = qs.filter(status=sv).count()
        status_breakdown.append({'label': sl, 'count': c})
    overall_chart = json.dumps({
        'labels': [r['label'] for r in status_breakdown if r['count'] > 0],
        'values': [r['count'] for r in status_breakdown if r['count'] > 0],
    })

    # By Client Type
    client_type_rows = []
    for ct_val, ct_label in Client.CLIENT_TYPE_CHOICES:
        s = build_stats(qs.filter(client__client_type=ct_val))
        if s['count'] > 0:
            client_type_rows.append({'label': ct_label, **s})

    # By Client Status
    client_status_rows = []
    for cs_val, cs_label in Client.STATUS_CHOICES:
        s = build_stats(qs.filter(client__status=cs_val))
        if s['count'] > 0:
            client_status_rows.append({'label': cs_label, **s})

    # By Client (individual client name — how much of the portfolio each one owns)
    client_agg = (
        qs.values('client__id', 'client__name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    client_rows = []
    for row in client_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        client_rows.append({
            'label': row['client__name'] or 'Unknown',
            'count': row['count'],
            'open': 0,
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # By Country
    country_agg = (
        qs.values('debtor__country')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    country_rows = []
    for row in country_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        country_rows.append({
            'label': row['debtor__country'] or 'Unknown',
            'count': row['count'],
            'open': 0,
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # By Agency (the case's linked collection agency, not the client)
    agency_agg = (
        qs.values('agency__name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    agency_rows = []
    for row in agency_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        agency_rows.append({
            'label': row['agency__name'] or 'No Agency',
            'count': row['count'],
            'open': 0,
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # By Collector
    collector_agg = (
        qs.values('collector__id', 'collector__username', 'collector__first_name', 'collector__last_name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    collector_rows = []
    for row in collector_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        first = row['collector__first_name'] or ''
        last = row['collector__last_name'] or ''
        name = f"{first} {last}".strip() or row['collector__username'] or 'Unassigned'
        collector_rows.append({
            'label': name,
            'count': row['count'],
            'open': 0,
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # Lawyer Wise Portfolio (from LegalCase linked to filtered cases).
    # Group by the FK lawyer's name when set, else the legacy free-text name,
    # merging the two sources under one label. legal_status stores the status
    # NAME (e.g. "Closed-Payment Done"), so closed is matched by name.
    lawyer_agg = (
        qs.filter(legal_case__isnull=False)
        .values('legal_case__lawyer__name', 'legal_case__lawyer_name')
        .annotate(
            case_count=Count('id'),
            closed_count=Count('id', filter=Q(legal_case__legal_status__icontains='closed')),
            approved=Sum('approved_amount'),
            received=Sum('received_amount'),
        )
    )
    lawyer_merged = {}
    for row in lawyer_agg:
        label = row['legal_case__lawyer__name'] or row['legal_case__lawyer_name'] or '—'
        m = lawyer_merged.setdefault(label, {'label': label, 'count': 0, 'closed': 0, 'approved': 0.0, 'received': 0.0})
        m['count'] += row['case_count']
        m['closed'] += row['closed_count']
        m['approved'] += float(row['approved'] or 0)
        m['received'] += float(row['received'] or 0)
    lawyer_rows = sorted(lawyer_merged.values(), key=lambda r: r['label'].lower())
    for r in lawyer_rows:
        r['remaining'] = r['approved'] - r['received']
    lawyer_total = {
        'count': sum(r['count'] for r in lawyer_rows),
        'closed': sum(r['closed'] for r in lawyer_rows),
        'approved': sum(r['approved'] for r in lawyer_rows),
        'received': sum(r['received'] for r in lawyer_rows),
    }
    lawyer_total['remaining'] = lawyer_total['approved'] - lawyer_total['received']

    # Group counts for section stat bar 1
    n_clients = qs.values('client').distinct().count()
    n_client_types = len(client_type_rows)
    n_client_statuses = len(client_status_rows)
    n_countries = len(country_rows)
    n_agencies = len(agency_rows)
    n_collectors = len(collector_rows)
    n_lawyers = len(lawyer_rows)

    # Serialize row lists for JavaScript consumption
    overall_num_rows = []
    for sv, sl in Case.all_status_choices():
        sub = qs.filter(status=sv)
        agg2 = sub.aggregate(approved=Sum('approved_amount'), received=Sum('received_amount'))
        app2 = float(agg2['approved'] or 0)
        rec2 = float(agg2['received'] or 0)
        cnt2 = sub.count()
        if cnt2 > 0:
            overall_num_rows.append({'label': sl, 'count': cnt2, 'approved': app2, 'received': rec2, 'remaining': app2 - rec2})

    return render(request, 'reports_case_status.html', {
        'active_page': 'reports',
        'active_sub': 'report_cases',
        'overall': overall,
        'overall_chart': overall_chart,
        'overall_num_rows': json.dumps(overall_num_rows),
        'n_clients': n_clients,
        'n_client_types': n_client_types,
        'n_client_statuses': n_client_statuses,
        'n_countries': n_countries,
        'n_agencies': n_agencies,
        'n_collectors': n_collectors,
        'n_lawyers': n_lawyers,
        'client_chart': make_chart(client_rows),
        'client_rows_json': json.dumps(client_rows),
        'client_type_chart': make_chart(client_type_rows),
        'client_type_rows_json': json.dumps(client_type_rows),
        'client_status_chart': make_chart(client_status_rows),
        'client_status_rows_json': json.dumps(client_status_rows),
        'country_chart': make_chart(country_rows),
        'country_rows_json': json.dumps(country_rows),
        'agency_chart': make_chart(agency_rows),
        'agency_rows_json': json.dumps(agency_rows),
        'collector_chart': make_chart(collector_rows),
        'collector_rows_json': json.dumps(collector_rows),
        'lawyer_rows': lawyer_rows,
        'lawyer_rows_json': json.dumps(lawyer_rows),
        'lawyer_total': lawyer_total,
        'lawyer_chart': make_chart(lawyer_rows),
        # filter values
        'filter_collector':  collector_id,
        'filter_client':     client_id,
        'filter_debtor':     debtor_id,
        'filter_date_from':  date_from,
        'filter_date_to':    date_to,
        'filter_date_range': date_range,
        'filter_agency':     agency_id,
        'filter_lawyer':     lawyer_name,
        'filter_case_status': case_status,
        'filter_statuses':   statuses,
        'all_statuses':      Case.all_status_choices(),
        # dropdown data
        'all_collectors': User.objects.filter(cases_collected__isnull=False).distinct().order_by('first_name', 'username'),
        'all_clients':    Client.objects.filter(status='active').order_by('name'),
        'all_debtors':    Debtor.objects.order_by('first_name', 'last_name'),
        'all_agencies':   Agency.objects.order_by('name'),
        'all_lawyers':    Lawyer.objects.order_by('name'),
    })


def collector_report(request):
    # The Collector report compares all collectors — admin only.
    if not request.user.is_superuser:
        messages.error(request, 'The Collector report is available to administrators only.')
        return redirect('dashboard')
    collector_id = request.GET.get('collector', '')

    # Everything below is scoped to this queryset — picking a collector drills
    # the whole page into just their book of business, the same way the Cases
    # report's filters scope every one of its sections.
    qs = Case.objects.select_related('client', 'debtor', 'collector')
    if collector_id:
        try:
            qs = qs.filter(collector_id=int(collector_id))
        except (ValueError, TypeError):
            pass

    agg = qs.aggregate(total_approved=Sum('approved_amount'), total_received=Sum('received_amount'))
    total_cases = qs.count()
    total_debtors = qs.values('debtor').distinct().count()
    total_clients = qs.values('client').distinct().count()
    total_approved = float(agg['total_approved'] or 0)
    total_received = float(agg['total_received'] or 0)
    total_remaining = total_approved - total_received

    def build_stats(sub_qs):
        agg2 = sub_qs.aggregate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        approved = float(agg2['approved'] or 0)
        received = float(agg2['received'] or 0)
        return {'count': agg2['count'] or 0, 'approved': approved, 'received': received, 'remaining': approved - received}

    def make_chart(rows, label_key='label'):
        labels = [r[label_key] for r in rows if r['count'] > 0]
        values = [r['count'] for r in rows if r['count'] > 0]
        return json.dumps({'labels': labels, 'values': values})

    # Case Status Overview — within the (optionally collector-scoped) portfolio
    overall_rows = []
    for sv, sl in Case.all_status_choices():
        s = build_stats(qs.filter(status=sv))
        if s['count'] > 0:
            overall_rows.append({'label': sl, **s})

    # Collector Wise Portfolio — deliberately NOT scoped by the page's own
    # collector filter, so it always shows every collector side by side for
    # comparison (the same way the Cases report's Agency section isn't scoped
    # by an agency filter it doesn't have).
    collector_agg = (
        Case.objects.select_related('collector')
        .values('collector__id', 'collector__username', 'collector__first_name', 'collector__last_name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    collector_rows = []
    for row in collector_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        first = row['collector__first_name'] or ''
        last = row['collector__last_name'] or ''
        name = f"{first} {last}".strip() or row['collector__username'] or 'Unassigned'
        collector_rows.append({
            'label': name,
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    all_collectors = User.objects.filter(
        id__in=Case.objects.values('collector').exclude(collector__isnull=True)
    ).order_by('first_name', 'last_name', 'username')

    # Client Wise Portfolio
    client_agg = (
        qs.values('client__id', 'client__name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    client_rows = []
    for row in client_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        client_rows.append({
            'label': row['client__name'] or 'Unknown',
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # Client Type
    client_type_rows = []
    for ct_val, ct_label in Client.CLIENT_TYPE_CHOICES:
        s = build_stats(qs.filter(client__client_type=ct_val))
        if s['count'] > 0:
            client_type_rows.append({'label': ct_label, **s})

    # Client Status
    client_status_rows = []
    for cs_val, cs_label in Client.STATUS_CHOICES:
        s = build_stats(qs.filter(client__status=cs_val))
        if s['count'] > 0:
            client_status_rows.append({'label': cs_label, **s})

    # Country Distribution
    country_agg = (
        qs.values('debtor__country')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    country_rows = []
    for row in country_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        country_rows.append({
            'label': row['debtor__country'] or 'Unknown',
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    return render(request, 'reports_collector.html', {
        'active_page': 'reports',
        'active_sub': 'report_collector',
        'total_cases': total_cases,
        'total_debtors': total_debtors,
        'total_clients': total_clients,
        'total_approved': total_approved,
        'total_received': total_received,
        'total_remaining': total_remaining,
        'overall_rows_json': json.dumps(overall_rows),
        'collector_rows_json': json.dumps(collector_rows),
        'client_rows_json': json.dumps(client_rows),
        'client_type_rows_json': json.dumps(client_type_rows),
        'client_status_rows_json': json.dumps(client_status_rows),
        'country_rows_json': json.dumps(country_rows),
        'all_collectors': all_collectors,
        'filter_collector': collector_id,
    })

@admin_required
def users_list(request):
    search = request.GET.get('q', '').strip()
    page_size = int(request.GET.get('show', 10))

    qs = User.objects.select_related('profile').order_by('first_name', 'last_name', 'username')
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(username__icontains=search) |
            Q(email__icontains=search)
        )

    from django.core.paginator import Paginator
    paginator = Paginator(qs, page_size)
    page_num = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_num)

    return render(request, 'settings_users.html', {
        'active_page': 'settings_users',
        'active_sub': 'settings_all_users',
        'page_obj': page_obj,
        'search': search,
        'page_size': page_size,
        'page_size_options': [10, 25, 50, 100],
        'group_choices': UserGroup.objects.filter(is_enabled=True).order_by('name'),
        'total_count': qs.count(),
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
        'permission_modules': PERMISSION_MODULES,
        'permission_actions': PERMISSION_ACTIONS,
    })


@admin_required
@require_POST
def user_create(request):
    first_name  = request.POST.get('first_name', '').strip()
    last_name   = request.POST.get('last_name', '').strip()
    username    = request.POST.get('username', '').strip()
    email       = request.POST.get('email', '').strip()
    phone       = request.POST.get('phone', '').strip()
    user_group_id = request.POST.get('user_group', '').strip()
    password    = request.POST.get('password', '').strip()
    is_enabled  = request.POST.get('is_enabled', '1') == '1'
    allowed_ips = request.POST.get('allowed_ips', '').strip()
    personal_email = request.POST.get('personal_email', '').strip()
    personal_phone = request.POST.get('personal_phone', '').strip()

    if not username or not password:
        return JsonResponse({'ok': False, 'error': 'Username and password are required.'})
    if User.objects.filter(username=username).exists():
        return JsonResponse({'ok': False, 'error': 'Username already taken.'})
    if not _valid_phone(phone) or not _valid_phone(personal_phone):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid phone number (country code + number).'})
    if not _valid_email(email) or not _valid_email(personal_email):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid email address.'})
    if not _valid_ip_list(allowed_ips):
        return JsonResponse({'ok': False, 'error': 'Please enter valid, comma-separated IP addresses.'})

    u = User.objects.create_user(
        username=username, email=email,
        first_name=first_name, last_name=last_name, password=password
    )
    u.is_active = is_enabled
    group = UserGroup.objects.filter(pk=user_group_id).first() if user_group_id else None
    if group and group.is_admin:
        u.is_superuser = True
        u.is_staff = True
    u.save()
    profile, _ = UserProfile.objects.get_or_create(user=u)
    profile.phone = phone
    profile.user_group = group
    profile.is_enabled = is_enabled
    profile.allowed_ips = allowed_ips
    profile.personal_email = personal_email
    profile.personal_phone = personal_phone
    profile.id_number = request.POST.get('id_number', '').strip()
    profile.address = request.POST.get('address', '').strip()
    profile.notes = request.POST.get('notes', '').strip()
    profile.save()
    return JsonResponse({'ok': True})


@admin_required
@require_POST
def user_update(request):
    u = get_object_or_404(User, pk=request.POST.get('id'))
    username    = request.POST.get('username', '').strip()
    email       = request.POST.get('email', '').strip()
    phone       = request.POST.get('phone', '').strip()
    password    = request.POST.get('password', '').strip()
    allowed_ips = request.POST.get('allowed_ips', '').strip()
    user_group_id = request.POST.get('user_group', '').strip()
    is_enabled  = request.POST.get('is_enabled', '1') == '1'
    personal_email = request.POST.get('personal_email', '').strip()
    personal_phone = request.POST.get('personal_phone', '').strip()

    if not username:
        return JsonResponse({'ok': False, 'error': 'Username is required.'})
    if User.objects.filter(username__iexact=username).exclude(pk=u.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Username already taken.'})
    if not _valid_phone(phone) or not _valid_phone(personal_phone):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid phone number (country code + number).'})
    if not _valid_email(email) or not _valid_email(personal_email):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid email address.'})
    if not _valid_ip_list(allowed_ips):
        return JsonResponse({'ok': False, 'error': 'Please enter valid, comma-separated IP addresses.'})

    u.first_name = request.POST.get('first_name', '').strip()
    u.last_name  = request.POST.get('last_name', '').strip()
    u.username   = username
    u.email      = email
    u.is_active  = is_enabled
    if password:
        u.set_password(password)
    u.save()

    profile, _ = UserProfile.objects.get_or_create(user=u)
    new_group = UserGroup.objects.filter(pk=user_group_id).first() if user_group_id else None
    if new_group != profile.user_group:
        # Moving groups resets personal grant/revoke overrides — the user
        # starts clean on the new group's baseline.
        profile.perm_grants = {}
        profile.perm_revokes = {}
        # Admin status follows the group. Standalone superusers (no previous
        # group, e.g. the built-in System Admin) are never demoted here.
        if new_group and new_group.is_admin:
            u.is_superuser = True
            u.is_staff = True
        elif profile.user_group and profile.user_group.is_admin:
            u.is_superuser = False
            u.is_staff = False
        u.save(update_fields=['is_superuser', 'is_staff'])
        ActivityLog.objects.create(
            user=request.user,
            log_type='security',
            action=f'User "{u.username}" moved to group "{new_group.name if new_group else "—"}" by {request.user.username}; permission overrides reset.',
            ip_address=_secure_client_ip(request) or None,
        )
    profile.user_group = new_group
    profile.phone = phone
    profile.is_enabled = is_enabled
    profile.allowed_ips = allowed_ips
    profile.personal_email = personal_email
    profile.personal_phone = personal_phone
    profile.id_number = request.POST.get('id_number', '').strip()
    profile.address = request.POST.get('address', '').strip()
    profile.notes = request.POST.get('notes', '').strip()
    profile.save()
    return JsonResponse({'ok': True})


@admin_required
@require_POST
def user_set_allowed_ips(request):
    uid = request.POST.get('id')
    allowed_ips = request.POST.get('allowed_ips', '').strip()
    if not _valid_ip_list(allowed_ips):
        return JsonResponse({'ok': False, 'error': 'Please enter valid, comma-separated IP addresses.'})
    u = get_object_or_404(User, pk=uid)
    profile, _ = UserProfile.objects.get_or_create(user=u)
    old_ips = profile.allowed_ips
    profile.allowed_ips = allowed_ips
    profile.save()
    ActivityLog.objects.create(
        user=request.user,
        log_type='security',
        action=f'Allowed IP(s) for "{u.username}" changed from "{old_ips or "any"}" to "{allowed_ips or "any"}" by {request.user.username}.',
        ip_address=_secure_client_ip(request) or None,
    )
    return JsonResponse({'ok': True})


@admin_required
@require_POST
def user_toggle(request):
    uid = request.POST.get('id')
    u = get_object_or_404(User, pk=uid)
    u.is_active = not u.is_active
    u.save()
    profile, _ = UserProfile.objects.get_or_create(user=u)
    profile.is_enabled = u.is_active
    profile.save()
    return JsonResponse({'ok': True, 'enabled': u.is_active})


@admin_required
@require_POST
def user_delete(request):
    """Delete one user (id) or several (ids[]); you can never delete yourself."""
    ids = request.POST.getlist('ids[]') or ([request.POST.get('id')] if request.POST.get('id') else [])
    if not ids:
        return JsonResponse({'ok': False, 'error': 'No users selected.'})
    qs = User.objects.filter(pk__in=ids).exclude(pk=request.user.pk)
    skipped_self = len(ids) != qs.count() and str(request.user.pk) in [str(i) for i in ids]
    count = qs.count()
    if not count:
        return JsonResponse({'ok': False, 'error': 'Cannot delete yourself.'})
    qs.delete()
    msg = f'{count} user(s) deleted.'
    if skipped_self:
        msg += ' Your own account was skipped.'
    return JsonResponse({'ok': True, 'message': msg})


def user_groups_list(request):
    groups = UserGroup.objects.order_by('name')
    return render(request, 'settings_user_groups.html', {
        'active_page': 'settings_users',
        'active_sub': 'settings_user_groups',
        'groups': groups,
        'permission_modules': PERMISSION_MODULES,
        'permission_actions': PERMISSION_ACTIONS,
        'group_perms_json': json.dumps({g.pk: g.permissions for g in groups}),
        'group_admin_json': json.dumps({g.pk: g.is_admin for g in groups}),
    })


def _parse_perm_map(request):
    try:
        return _clean_perm_map(json.loads(request.POST.get('permissions', '{}') or '{}'))
    except (ValueError, TypeError):
        return {}


@require_POST
def user_group_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if UserGroup.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Group already exists.'})
    g = UserGroup.objects.create(
        name=name,
        permissions=_parse_perm_map(request),
        is_admin=request.POST.get('is_admin', '0') == '1',
    )
    return JsonResponse({'ok': True, 'id': g.pk, 'name': g.name})


def _sync_group_admin_members(group):
    """Members of an admin group are Django superusers; members of a non-admin
    group are not (the app's admin checks read is_superuser)."""
    member_ids = list(group.members.values_list('user_id', flat=True))
    if member_ids:
        User.objects.filter(pk__in=member_ids).update(
            is_superuser=group.is_admin, is_staff=group.is_admin)


@require_POST
def user_group_update(request):
    """Rename a group and/or replace its permission matrix. Member users keep
    their personal grants/revokes, which re-apply on top of the new baseline."""
    g = get_object_or_404(UserGroup, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if name:
        if UserGroup.objects.filter(name__iexact=name).exclude(pk=g.pk).exists():
            return JsonResponse({'ok': False, 'error': 'A group with that name already exists.'})
        g.name = name
    g.permissions = _parse_perm_map(request)
    was_admin = g.is_admin
    g.is_admin = request.POST.get('is_admin', '0') == '1'
    g.save(update_fields=['name', 'permissions', 'is_admin'])
    if g.is_admin != was_admin:
        _sync_group_admin_members(g)
    return JsonResponse({'ok': True})


@admin_required
def user_permissions_get(request):
    """Data for the per-user Permissions modal: the group baseline and the
    user's current effective matrix."""
    u = get_object_or_404(User, pk=request.GET.get('id'))
    profile, _ = UserProfile.objects.get_or_create(user=u)
    return JsonResponse({
        'ok': True,
        'group': profile.user_group.name if profile.user_group else None,
        'group_perms': profile.group_permissions(),
        'effective': profile.effective_permissions(),
        'is_superuser': u.is_superuser,
    })


@admin_required
@require_POST
def user_permissions_set(request):
    """Save a user's desired effective matrix; only the diff vs the group is
    stored, so later group edits still flow through to the user."""
    u = get_object_or_404(User, pk=request.POST.get('id'))
    profile, _ = UserProfile.objects.get_or_create(user=u)
    try:
        desired = json.loads(request.POST.get('permissions', '{}') or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Invalid permissions payload.'})
    profile.set_effective_permissions(desired)
    profile.save(update_fields=['perm_grants', 'perm_revokes'])
    ActivityLog.objects.create(
        user=request.user,
        log_type='security',
        action=f'Permissions for "{u.username}" updated by {request.user.username}.',
        ip_address=_secure_client_ip(request) or None,
    )
    return JsonResponse({'ok': True})


@require_POST
def user_group_toggle(request):
    gid = request.POST.get('id')
    g = get_object_or_404(UserGroup, pk=gid)
    g.is_enabled = not g.is_enabled
    g.save()
    return JsonResponse({'ok': True, 'enabled': g.is_enabled})


@require_POST
def user_group_delete(request):
    ids = request.POST.getlist('ids[]')
    if not ids:
        ids = [request.POST.get('id')]
    UserGroup.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def countries_list(request):
    # Small fixed reference list (~200 rows) — load all of them and let the
    # template filter/sort client-side, so the filter box works instantly on
    # every column (name, code, dial code, status) without a page reload.
    countries = Country.objects.all().order_by('name')
    return render(request, 'settings_countries.html', {
        'active_page': 'settings_localisation',
        'active_sub':  'settings_countries',
        'countries':   countries,
        'total_count': countries.count(),
    })


@require_POST
def country_create(request):
    name = request.POST.get('name', '').strip()
    code = request.POST.get('code', '').strip().upper()
    dial = request.POST.get('country_code', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if Country.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Country already exists.'})
    c = Country.objects.create(name=name, code=code, country_code=dial, is_enabled=True)
    return JsonResponse({'ok': True, 'id': c.pk, 'name': c.name, 'code': c.code, 'country_code': c.country_code})


@require_POST
def country_update(request):
    c = get_object_or_404(Country, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if Country.objects.filter(name__iexact=name).exclude(pk=c.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another country already has that name.'})
    c.name = name
    c.code = request.POST.get('code', '').strip().upper()
    c.country_code = request.POST.get('country_code', '').strip()
    c.save()
    return JsonResponse({'ok': True, 'id': c.pk, 'name': c.name, 'code': c.code, 'country_code': c.country_code})


@require_POST
def country_toggle(request):
    c = get_object_or_404(Country, pk=request.POST.get('id'))
    c.is_enabled = not c.is_enabled
    c.save()
    return JsonResponse({'ok': True, 'enabled': c.is_enabled})


@require_POST
def country_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    Country.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def states_list(request):
    # States only exist for countries still in the system; load them all and
    # let the template filter/sort/paginate client-side.
    states = State.objects.select_related('country').order_by('country__name', 'name')
    return render(request, 'settings_states.html', {
        'active_page': 'settings_localisation',
        'active_sub':  'settings_states',
        'states':      states,
        'total_count': states.count(),
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
    })


def _country_from_post(request):
    cid = request.POST.get('country', '').strip()
    return Country.objects.filter(pk=cid).first() if cid.isdigit() else None


@require_POST
def state_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    country = _country_from_post(request)
    if State.objects.filter(name__iexact=name, country=country).exists():
        return JsonResponse({'ok': False, 'error': 'State already exists for this country.'})
    s = State.objects.create(name=name, country=country, is_enabled=True)
    return JsonResponse({'ok': True, 'id': s.pk, 'name': s.name,
                         'country': s.country.name if s.country else '—'})


@require_POST
def state_update(request):
    s = get_object_or_404(State, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    country = _country_from_post(request)
    if State.objects.filter(name__iexact=name, country=country).exclude(pk=s.pk).exists():
        return JsonResponse({'ok': False, 'error': 'That state already exists for this country.'})
    s.name = name
    s.country = country
    s.save()
    return JsonResponse({'ok': True, 'id': s.pk, 'name': s.name,
                         'country': s.country.name if s.country else '—'})


@require_POST
def state_toggle(request):
    s = get_object_or_404(State, pk=request.POST.get('id'))
    s.is_enabled = not s.is_enabled
    s.save()
    return JsonResponse({'ok': True, 'enabled': s.is_enabled})


@require_POST
def state_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    State.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def currencies_list(request):
    currencies = Currency.objects.all().order_by('name')
    return render(request, 'settings_currencies.html', {
        'active_page': 'settings_localisation',
        'active_sub':  'settings_currencies',
        'currencies':  currencies,
        'total_count': currencies.count(),
    })


@require_POST
def currency_create(request):
    name   = request.POST.get('name', '').strip()
    code   = request.POST.get('code', '').strip().upper()
    sym_l  = request.POST.get('symbol_left', '').strip()
    sym_r  = request.POST.get('symbol_right', '').strip()
    value  = request.POST.get('value', '1').strip()
    if not name or not code:
        return JsonResponse({'ok': False, 'error': 'Name and code are required.'})
    if Currency.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Currency already exists.'})
    try:
        value = float(value)
    except ValueError:
        value = 1.0
    c = Currency.objects.create(name=name, code=code, symbol_left=sym_l,
                                symbol_right=sym_r, value=value, is_enabled=True)
    return JsonResponse({'ok': True, 'id': c.pk})


@require_POST
def currency_update(request):
    c = get_object_or_404(Currency, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    code = request.POST.get('code', '').strip().upper()
    if not name or not code:
        return JsonResponse({'ok': False, 'error': 'Name and code are required.'})
    if Currency.objects.filter(name__iexact=name).exclude(pk=c.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another currency already has that name.'})
    try:
        value = float(request.POST.get('value', '1').strip())
    except ValueError:
        value = 1.0
    c.name = name
    c.code = code
    c.symbol_left = request.POST.get('symbol_left', '').strip()
    c.symbol_right = request.POST.get('symbol_right', '').strip()
    c.value = value
    c.save()
    return JsonResponse({'ok': True, 'id': c.pk})


@require_POST
def currency_toggle(request):
    c = get_object_or_404(Currency, pk=request.POST.get('id'))
    c.is_enabled = not c.is_enabled
    c.save()
    return JsonResponse({'ok': True, 'enabled': c.is_enabled})


@require_POST
def currency_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    Currency.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def case_types_list(request):
    return render(request, 'settings_case_types.html', {
        'active_page': 'settings_case',
        'active_sub':  'settings_case_types',
        'case_types':  CaseType.objects.all(),
    })


@require_POST
def case_type_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if CaseType.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Case type already exists.'})
    ct = CaseType.objects.create(name=name)
    return JsonResponse({'ok': True, 'id': ct.pk, 'name': ct.name})


@require_POST
def case_type_toggle(request):
    ct = get_object_or_404(CaseType, pk=request.POST.get('id'))
    ct.is_enabled = not ct.is_enabled
    ct.save()
    return JsonResponse({'ok': True, 'enabled': ct.is_enabled})


@require_POST
def case_type_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    CaseType.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def case_status_list(request):
    from django.core.paginator import Paginator
    search    = request.GET.get('q', '').strip()
    page_size = int(request.GET.get('show', 10))

    qs = CaseStatus.objects.all()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(color__icontains=search))

    paginator = Paginator(qs, page_size)
    page_obj  = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'settings_case_status.html', {
        'active_page': 'settings_case',
        'active_sub':  'settings_case_status',
        'page_obj':    page_obj,
        'search':      search,
        'page_size':   page_size,
        'page_size_options': [10, 25, 50, 100],
        'total_count': qs.count(),
    })


@require_POST
def case_status_create(request):
    name  = request.POST.get('name', '').strip()
    color = request.POST.get('color', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if CaseStatus.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Status already exists.'})
    cs = CaseStatus.objects.create(name=name, color=color, is_enabled=True)
    return JsonResponse({'ok': True, 'id': cs.pk, 'name': cs.name, 'color': cs.color})


@require_POST
def case_status_update(request):
    cs = get_object_or_404(CaseStatus, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if CaseStatus.objects.filter(name__iexact=name).exclude(pk=cs.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another status already has that name.'})
    cs.name = name
    cs.color = request.POST.get('color', '').strip()
    cs.save()
    return JsonResponse({'ok': True, 'id': cs.pk, 'name': cs.name, 'color': cs.color})


@require_POST
def case_status_toggle(request):
    cs = get_object_or_404(CaseStatus, pk=request.POST.get('id'))
    cs.is_enabled = not cs.is_enabled
    cs.save()
    return JsonResponse({'ok': True, 'enabled': cs.is_enabled})


@require_POST
def case_status_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    CaseStatus.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def legal_case_status_list(request):
    # Small fixed reference list — load all rows; the template does the
    # filtering, sorting and "Show N" client-side.
    statuses = LegalCaseStatus.objects.all().order_by('name')
    return render(request, 'settings_legal_case_status.html', {
        'active_page': 'settings_case',
        'active_sub':  'settings_legal_case_status',
        'statuses':    statuses,
        'total_count': statuses.count(),
    })


@require_POST
def legal_case_status_create(request):
    name  = request.POST.get('name', '').strip()
    color = request.POST.get('color', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if LegalCaseStatus.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Status already exists.'})
    s = LegalCaseStatus.objects.create(name=name, color=color, is_enabled=True)
    return JsonResponse({'ok': True, 'id': s.pk, 'name': s.name, 'color': s.color})


@require_POST
def legal_case_status_update(request):
    s = get_object_or_404(LegalCaseStatus, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if LegalCaseStatus.objects.filter(name__iexact=name).exclude(pk=s.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another status already has that name.'})
    s.name = name
    s.color = request.POST.get('color', '').strip()
    s.save()
    return JsonResponse({'ok': True, 'id': s.pk, 'name': s.name, 'color': s.color})


@require_POST
def legal_case_status_toggle(request):
    s = get_object_or_404(LegalCaseStatus, pk=request.POST.get('id'))
    s.is_enabled = not s.is_enabled
    s.save()
    return JsonResponse({'ok': True, 'enabled': s.is_enabled})


@require_POST
def legal_case_status_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    LegalCaseStatus.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def legal_fee_types_list(request):
    return render(request, 'settings_legal_fee_types.html', {
        'active_page': 'settings_case',
        'active_sub':  'settings_legal_fee_types',
        'fee_types':   LegalFeeType.objects.all(),
    })


@require_POST
def legal_fee_type_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if LegalFeeType.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Fee type already exists.'})
    ft = LegalFeeType.objects.create(name=name)
    return JsonResponse({'ok': True, 'id': ft.pk, 'name': ft.name})


@require_POST
def legal_fee_type_toggle(request):
    ft = get_object_or_404(LegalFeeType, pk=request.POST.get('id'))
    ft.is_enabled = not ft.is_enabled
    ft.save()
    return JsonResponse({'ok': True, 'enabled': ft.is_enabled})


@require_POST
def legal_fee_type_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    LegalFeeType.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def followup_types_list(request):
    return render(request, 'settings_followup_types.html', {
        'active_page':  'settings_case',
        'active_sub':   'settings_followup_types',
        'followup_types': FollowupType.objects.all(),
    })


@require_POST
def followup_type_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if FollowupType.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Type already exists.'})
    ft = FollowupType.objects.create(name=name)
    return JsonResponse({'ok': True, 'id': ft.pk, 'name': ft.name})


@require_POST
def followup_type_toggle(request):
    ft = get_object_or_404(FollowupType, pk=request.POST.get('id'))
    ft.is_enabled = not ft.is_enabled
    ft.save()
    return JsonResponse({'ok': True, 'enabled': ft.is_enabled})


@require_POST
def followup_type_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    FollowupType.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def payment_modes_list(request):
    return render(request, 'settings_payment_modes.html', {
        'active_page':  'settings_payment_modes',
        'active_sub':   'settings_payment_modes',
        'payment_modes': PaymentMode.objects.all(),
    })


@require_POST
def payment_mode_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if PaymentMode.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Mode already exists.'})
    pm = PaymentMode.objects.create(name=name)
    return JsonResponse({'ok': True, 'id': pm.pk, 'name': pm.name})


@require_POST
def payment_mode_update(request):
    pm = get_object_or_404(PaymentMode, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if PaymentMode.objects.filter(name__iexact=name).exclude(pk=pm.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another mode already has that name.'})
    pm.name = name
    pm.save()
    return JsonResponse({'ok': True, 'id': pm.pk, 'name': pm.name})


@require_POST
def payment_mode_toggle(request):
    pm = get_object_or_404(PaymentMode, pk=request.POST.get('id'))
    pm.is_enabled = not pm.is_enabled
    pm.save()
    return JsonResponse({'ok': True, 'enabled': pm.is_enabled})


@require_POST
def payment_mode_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    PaymentMode.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def client_types_list(request):
    return render(request, 'settings_client_types.html', {
        'active_page':  'settings_client_types',
        'active_sub':   'settings_client_types',
        'client_types': ClientType.objects.all(),
    })


@require_POST
def client_type_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if ClientType.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Type already exists.'})
    ct = ClientType.objects.create(name=name)
    return JsonResponse({'ok': True, 'id': ct.pk, 'name': ct.name})


@require_POST
def client_type_update(request):
    ct = get_object_or_404(ClientType, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if ClientType.objects.filter(name__iexact=name).exclude(pk=ct.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another type already has that name.'})
    ct.name = name
    ct.save()
    return JsonResponse({'ok': True, 'id': ct.pk, 'name': ct.name})


@require_POST
def client_type_toggle(request):
    ct = get_object_or_404(ClientType, pk=request.POST.get('id'))
    ct.is_enabled = not ct.is_enabled
    ct.save()
    return JsonResponse({'ok': True, 'enabled': ct.is_enabled})


@require_POST
def client_type_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    ClientType.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


# ---------- CONTRACT TYPES ----------
def contract_types_list(request):
    return render(request, 'settings_contract_types.html', {
        'active_page':     'settings_contract_types',
        'active_sub':      'settings_contract_types',
        'contract_types':  ContractType.objects.all(),
    })

@require_POST
def contract_type_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if ContractType.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Type already exists.'})
    ct = ContractType.objects.create(name=name)
    return JsonResponse({'ok': True, 'id': ct.pk, 'name': ct.name})

@require_POST
def contract_type_update(request):
    ct = get_object_or_404(ContractType, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if ContractType.objects.filter(name__iexact=name).exclude(pk=ct.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another type already has that name.'})
    ct.name = name
    ct.save()
    return JsonResponse({'ok': True, 'id': ct.pk, 'name': ct.name})


@require_POST
def contract_type_toggle(request):
    ct = get_object_or_404(ContractType, pk=request.POST.get('id'))
    ct.is_enabled = not ct.is_enabled
    ct.save()
    return JsonResponse({'ok': True, 'enabled': ct.is_enabled})

@require_POST
def contract_type_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    ContractType.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


# ---------- CONTACT TYPES ----------
def contact_types_list(request):
    # Group same-name rows (one per Client/Debtor type) into a single line,
    # e.g. "Accountant" shown once with both the Client and Debtor badges.
    groups = {}
    for ct in ContactType.objects.all().order_by('name', 'type'):
        key = ct.name.strip().lower()
        g = groups.setdefault(key, {'name': ct.name, 'types': [], 'ids': [], 'enabled_flags': []})
        g['types'].append(ct.type)
        g['ids'].append(ct.pk)
        g['enabled_flags'].append(ct.is_enabled)
    contact_type_groups = sorted(
        ({'name': g['name'], 'types': g['types'], 'ids': g['ids'],
          'is_enabled': all(g['enabled_flags'])} for g in groups.values()),
        key=lambda g: g['name'].lower()
    )
    return render(request, 'settings_contact_types.html', {
        'active_page':  'settings_contact_types',
        'active_sub':   'settings_contact_types',
        'contact_type_groups': contact_type_groups,
        'type_choices': ContactType.TYPE_CHOICES,
    })

def _split_valid_types(raw):
    """Parse a 'client,debtor'-style POST value into the subset that are
    real ContactType.TYPE_CHOICES keys, in the order given, de-duplicated."""
    valid = dict(ContactType.TYPE_CHOICES)
    seen, out = set(), []
    for t in raw.split(','):
        t = t.strip()
        if t in valid and t not in seen:
            seen.add(t)
            out.append(t)
    return out


@require_POST
def contact_type_create(request):
    name = request.POST.get('name', '').strip()
    types = _split_valid_types(request.POST.get('types', request.POST.get('type', 'client')))
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if not types:
        return JsonResponse({'ok': False, 'error': 'Select at least one type (Client and/or Debtor).'})
    created = []
    for t in types:
        if ContactType.objects.filter(name__iexact=name, type=t).exists():
            continue
        created.append(ContactType.objects.create(name=name, type=t))
    if not created:
        return JsonResponse({'ok': False, 'error': 'That name already exists for the selected type(s).'})
    return JsonResponse({'ok': True, 'id': created[0].pk, 'name': created[0].name,
                         'created': len(created)})

@require_POST
def contact_type_update(request):
    """Edits a whole name-group at once. `ids` is the comma-separated pks of
    the group's existing rows (one per type it currently has); `types` is the
    comma-separated set of types it should have after saving. A type that's
    unchecked gets its row deleted; a newly-checked type gets a new row
    (reusing one that already exists under the new name, if any)."""
    raw_ids = request.POST.get('ids', request.POST.get('id', ''))
    id_list = [i for i in str(raw_ids).split(',') if i.strip()]
    rows = list(ContactType.objects.filter(pk__in=id_list))
    if not rows:
        return JsonResponse({'ok': False, 'error': 'Not found.'})
    name = request.POST.get('name', '').strip()
    types = _split_valid_types(request.POST.get('types', request.POST.get('type', '')))
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if not types:
        return JsonResponse({'ok': False, 'error': 'Select at least one type (Client and/or Debtor).'})

    by_type = {r.type: r for r in rows}
    type_labels = dict(ContactType.TYPE_CHOICES)
    for t, row in by_type.items():
        if t in types and ContactType.objects.filter(name__iexact=name, type=t).exclude(pk=row.pk).exists():
            return JsonResponse({'ok': False, 'error': f'Another "{type_labels.get(t, t)}" contact type already has that name.'})
    for t, row in by_type.items():
        if t in types:
            row.name = name
            row.save()
        else:
            row.delete()
    for t in types:
        if t not in by_type and not ContactType.objects.filter(name__iexact=name, type=t).exists():
            ContactType.objects.create(name=name, type=t)
    return JsonResponse({'ok': True})

@require_POST
def contact_type_toggle(request):
    """Toggles a whole name-group (comma-separated `ids`) together: if any
    row in the group is currently disabled, enable all of them; otherwise
    disable all of them."""
    raw_ids = request.POST.get('ids', request.POST.get('id', ''))
    id_list = [i for i in str(raw_ids).split(',') if i.strip()]
    rows = list(ContactType.objects.filter(pk__in=id_list))
    if not rows:
        return JsonResponse({'ok': False, 'error': 'Not found.'})
    new_state = not all(r.is_enabled for r in rows)
    ContactType.objects.filter(pk__in=id_list).update(is_enabled=new_state)
    return JsonResponse({'ok': True, 'enabled': new_state})

@require_POST
def contact_type_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    ContactType.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


def attachment_types_list(request):
    return render(request, 'settings_attachment_types.html', {
        'active_page':  'settings_attachment_types',
        'active_sub':   'settings_attachment_types',
        'attachment_types': AttachmentType.objects.all(),
        'type_choices': AttachmentType.TYPE_CHOICES,
    })


@require_POST
def attachment_type_create(request):
    name = request.POST.get('name', '').strip()
    t    = request.POST.get('type', 'case')
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if AttachmentType.objects.filter(name__iexact=name).exists():
        return JsonResponse({'ok': False, 'error': 'Type already exists.'})
    at = AttachmentType.objects.create(name=name, type=t)
    return JsonResponse({'ok': True, 'id': at.pk, 'name': at.name, 'type': at.get_type_display()})


@require_POST
def attachment_type_update(request):
    at = get_object_or_404(AttachmentType, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    t    = request.POST.get('type', 'case')
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if AttachmentType.objects.filter(name__iexact=name).exclude(pk=at.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another type already has that name.'})
    at.name = name
    at.type = t
    at.save()
    return JsonResponse({'ok': True, 'id': at.pk, 'name': at.name, 'type': at.get_type_display()})


@require_POST
def attachment_type_toggle(request):
    at = get_object_or_404(AttachmentType, pk=request.POST.get('id'))
    at.is_enabled = not at.is_enabled
    at.save()
    return JsonResponse({'ok': True, 'enabled': at.is_enabled})


@require_POST
def attachment_type_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    AttachmentType.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


# ---------- AGENCIES ----------
def agencies_list(request):
    return render(request, 'settings_agencies.html', {
        'active_page': 'settings_agencies', 'active_sub': 'settings_agencies',
        'agencies': Agency.objects.all(),
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
    })

@require_POST
def agency_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    phone = request.POST.get('phone', '').strip()
    email = request.POST.get('email', '').strip()
    if not _valid_phone(phone):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid phone number (country code + number).'})
    if not _valid_email(email):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid email address.'})
    a = Agency.objects.create(name=name, organisation=request.POST.get('organisation','').strip(),
                              phone=phone, email=email)
    return JsonResponse({'ok': True, 'id': a.pk, 'name': a.name, 'organisation': a.organisation,
                         'phone': a.phone, 'email': a.email})

@require_POST
def agency_update(request):
    a = get_object_or_404(Agency, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    phone = request.POST.get('phone', '').strip()
    email = request.POST.get('email', '').strip()
    if phone and not _valid_phone(phone):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid phone number (country code + number).'})
    if email and not _valid_email(email):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid email address.'})
    a.name = name
    a.organisation = request.POST.get('organisation', '').strip()
    a.phone = phone
    a.email = email
    a.save()
    return JsonResponse({'ok': True, 'id': a.pk, 'name': a.name, 'organisation': a.organisation,
                         'phone': a.phone, 'email': a.email})

@require_POST
def agency_toggle(request):
    a = get_object_or_404(Agency, pk=request.POST.get('id'))
    a.status = 'inactive' if a.status == 'active' else 'active'
    a.save()
    return JsonResponse({'ok': True, 'status': a.status})

@require_POST
def agency_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    Agency.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


# ---------- LAWYERS ----------
def lawyers_list(request):
    return render(request, 'settings_lawyers.html', {
        'active_page': 'settings_lawyers', 'active_sub': 'settings_lawyers',
        'lawyers': Lawyer.objects.all(),
        'all_countries': Country.objects.filter(is_enabled=True).order_by('name'),
    })

@require_POST
def lawyer_create(request):
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    phone = request.POST.get('phone', '').strip()
    email = request.POST.get('email', '').strip()
    if not _valid_phone(phone):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid phone number (country code + number).'})
    if not _valid_email(email):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid email address.'})
    l = Lawyer.objects.create(name=name, phone=phone, email=email)
    return JsonResponse({'ok': True, 'id': l.pk, 'name': l.name, 'phone': l.phone, 'email': l.email})

@require_POST
def lawyer_update(request):
    l = get_object_or_404(Lawyer, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    phone = request.POST.get('phone', '').strip()
    email = request.POST.get('email', '').strip()
    if phone and not _valid_phone(phone):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid phone number (country code + number).'})
    if email and not _valid_email(email):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid email address.'})
    l.name = name
    l.phone = phone
    l.email = email
    l.save()
    return JsonResponse({'ok': True, 'id': l.pk, 'name': l.name, 'phone': l.phone, 'email': l.email})

@require_POST
def lawyer_toggle(request):
    l = get_object_or_404(Lawyer, pk=request.POST.get('id'))
    l.status = 'inactive' if l.status == 'active' else 'active'
    l.save()
    return JsonResponse({'ok': True, 'status': l.status})

@require_POST
def lawyer_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    Lawyer.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


# ---------- CONTACT DIRECTORY ----------
def contact_directory(request):
    msg = None
    if request.method == 'POST' and request.FILES.get('file'):
        import csv, io
        f = request.FILES['file']
        decoded = f.read().decode('utf-8-sig', errors='replace')
        reader  = csv.DictReader(io.StringIO(decoded))
        count = 0
        for row in reader:
            ContactDirectory.objects.create(
                contact_name=row.get('Contact Name', row.get('contact_name', '')).strip(),
                contact_type=row.get('Contact Type', row.get('contact_type', '')).strip(),
                email=row.get('Email', row.get('email', '')).strip(),
                phone_number1=row.get('Phone Number 1', row.get('phone_number1', '')).strip(),
                phone_number2=row.get('Phone Number 2', row.get('phone_number2', '')).strip(),
                id_number=row.get('ID Number', row.get('id_number', '')).strip(),
                passport_number=row.get('Passport Number', row.get('passport_number', '')).strip(),
                nationality=row.get('Nationality', row.get('nationality', '')).strip(),
            )
            count += 1
        msg = f'{count} contact(s) imported.'
    return render(request, 'settings_contact_directory.html', {
        'active_page': 'settings_contact_dir', 'active_sub': 'settings_contact_dir',
        'contacts': ContactDirectory.objects.all().order_by('contact_name'),
        'msg': msg,
    })


@require_POST
def contact_directory_update(request):
    c = get_object_or_404(ContactDirectory, pk=request.POST.get('id'))
    name = request.POST.get('contact_name', '').strip()
    if not name:
        return JsonResponse({'ok': False, 'error': 'Contact name is required.'})
    email = request.POST.get('email', '').strip()
    if not _valid_email(email):
        return JsonResponse({'ok': False, 'error': 'Please enter a valid email address.'})
    c.contact_name = name
    c.contact_type = request.POST.get('contact_type', '').strip()
    c.email = email
    c.phone_number1 = request.POST.get('phone_number1', '').strip()
    c.phone_number2 = request.POST.get('phone_number2', '').strip()
    c.id_number = request.POST.get('id_number', '').strip()
    c.passport_number = request.POST.get('passport_number', '').strip()
    c.nationality = request.POST.get('nationality', '').strip()
    c.save()
    return JsonResponse({'ok': True, 'id': c.pk})


@require_POST
def contact_directory_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    ContactDirectory.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})


# ---------- SETTINGS EXPORTS ----------
def agency_export(request, format):
    qs = Agency.objects.all().order_by('name')
    headers = ['Name', 'Organisation', 'Phone', 'Email', 'Status', 'Created At']
    rows = [[a.name, a.organisation, a.phone, a.email, a.get_status_display(), a.created_at.strftime('%d-%b-%Y')] for a in qs]
    if format == 'excel':
        return _export_excel('Agencies', headers, rows)
    if format == 'pdf':
        return _export_pdf('Agencies Report', headers, rows)
    return redirect('agencies_list')


def lawyer_export(request, format):
    qs = Lawyer.objects.all().order_by('name')
    headers = ['Name', 'Phone', 'Email', 'Status', 'Created At']
    rows = [[l.name, l.phone, l.email, l.get_status_display(), l.created_at.strftime('%d-%b-%Y')] for l in qs]
    if format == 'excel':
        return _export_excel('Lawyers', headers, rows)
    if format == 'pdf':
        return _export_pdf('Lawyers Report', headers, rows)
    return redirect('lawyers_list')


def contact_directory_export(request, format):
    qs = ContactDirectory.objects.all().order_by('contact_name')
    headers = ['Name', 'Type', 'Email', 'Phone 1', 'Phone 2', 'ID Number', 'Passport', 'Nationality', 'Created At']
    rows = [[c.contact_name, c.contact_type, c.email, c.phone_number1, c.phone_number2, c.id_number, c.passport_number, c.nationality, c.created_at.strftime('%d-%b-%Y')] for c in qs]
    if format == 'excel':
        return _export_excel('Contact Directory', headers, rows)
    if format == 'pdf':
        return _export_pdf('Contact Directory Report', headers, rows)
    return redirect('contact_directory')


# ---------- IMPORT ----------
def import_view(request):
    msg = None
    if request.method == 'POST' and request.FILES.get('file'):
        msg = 'File received. Import processing is handled by the mapping step.'
    return render(request, 'settings_import.html', {
        'active_page': 'settings_import', 'active_sub': 'settings_import', 'msg': msg,
    })


# ---------- IMPORT NEW (bulk Case + Debtor import from Excel) ----------
# Columns mirror the client's reference export (debtorcase.xlsx). A file is
# accepted only when every required header is present (exact names, any order).
# "Debtor" is the lookup/creation key (matched case-insensitively against an
# existing Debtor, or used to create one); "Name" is a second required column
# that sets the new debtor's display name when one is created. The optional
# debtor-profile columns (Is Company .. Phone Number) only apply when a new
# debtor is being created — they never edit an existing one.
CASE_IMPORT_REQUIRED = ['Client', 'Debtor', 'Name', 'Creditor Name', 'Received On', 'Case Type',
                        'Account Number', 'Case Status', 'Collector', 'Case Country', 'Currency',
                        'Outstanding Amount', 'Approved Amount']
CASE_IMPORT_OPTIONAL = ['Is Company', 'Gender', 'Nationality', 'ID Number/CR Number', 'State',
                        'Country', 'Due Date', 'Relationship Number', 'Shadow Account', 'CIF Number',
                        'Agency Name', 'Phone Number', 'Notes', 'Principal Amount', 'Promise Date']


def _parse_import_date(value):
    """Accept real Excel dates or 'YYYY-MM-DD' / 'DD/MM/YYYY' / 'DD-MM-YYYY' text."""
    import datetime as _dt
    if value is None or value == '':
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    s = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d-%b-%Y'):
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _import_cases_from_workbook(request, file):
    """Validate headers, then create one case per row (auto-creating unknown
    debtors). Each row succeeds or fails independently; returns
    (header_error, results, created_count)."""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(file, data_only=True)
    except Exception:
        return 'Could not read the file — upload a valid .xlsx Excel file.', [], 0
    ws = wb.active

    headers = {}
    for idx, cell in enumerate(ws[1]):
        if cell.value is not None and str(cell.value).strip():
            headers[str(cell.value).strip().lower()] = idx
    missing = [h for h in CASE_IMPORT_REQUIRED if h.lower() not in headers]
    if missing:
        return ('File rejected — missing mandatory column(s): ' + ', '.join(missing) +
                '. Download the sample sheet and keep its headers exactly.'), [], 0

    def cell(row, header):
        i = headers.get(header.lower())
        if i is None or i >= len(row):
            return ''
        v = row[i]
        return v if v is not None else ''

    status_by_label = {label.strip().lower(): key for key, label in Case.all_status_choices()}
    status_keys = {key for key, _ in Case.all_status_choices()}
    gender_by_label = {label.strip().lower(): key for key, label in Debtor.GENDER_CHOICES}
    gender_keys = {key for key, _ in Debtor.GENDER_CHOICES}
    truthy = {'yes', 'y', 'true', '1', 'company', 'organization', 'organisation'}

    results, created = [], 0
    for rownum, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not any(v not in (None, '') for v in row):
            continue    # fully empty row

        def err(message):
            results.append({'row': rownum, 'ok': False, 'message': message})

        client_name    = str(cell(row, 'Client')).strip()
        debtor_name    = str(cell(row, 'Debtor')).strip()
        debtor_display = str(cell(row, 'Name')).strip()
        account_no     = str(cell(row, 'Account Number')).strip()
        creditor_name  = str(cell(row, 'Creditor Name')).strip()
        if not client_name or not debtor_name or not debtor_display or not account_no:
            err('Client, Debtor, Name and Account Number are required.'); continue
        if not creditor_name:
            err('Creditor Name is required.'); continue

        client = Client.objects.filter(name__iexact=client_name).first()
        if not client:
            err(f'Client "{client_name}" not found — create the client first.'); continue

        case_type_name = str(cell(row, 'Case Type')).strip()
        case_type = CaseType.objects.filter(name__iexact=case_type_name, is_enabled=True).first()
        if not case_type:
            err(f'Case Type "{case_type_name}" not found in Settings → Case Types.'); continue

        raw_status = str(cell(row, 'Case Status')).strip()
        status = status_by_label.get(raw_status.lower()) or (raw_status.lower() if raw_status.lower() in status_keys else None)
        if not status:
            err(f'Unknown Case Status "{raw_status}".'); continue

        collector_raw = str(cell(row, 'Collector')).strip()
        collector = User.objects.filter(is_active=True).filter(
            Q(username__iexact=collector_raw) |
            Q(first_name__iexact=collector_raw.split(' ')[0], last_name__iexact=' '.join(collector_raw.split(' ')[1:]))
        ).first()
        if not collector:
            err(f'Collector "{collector_raw}" not found (use username or full name).'); continue

        received_date = _parse_import_date(cell(row, 'Received On'))
        if not received_date:
            err('Received On must be a date (YYYY-MM-DD).'); continue

        country = str(cell(row, 'Case Country')).strip()
        if not country:
            err('Case Country is required.'); continue

        currency_code = str(cell(row, 'Currency')).strip()
        currency = Currency.objects.filter(code__iexact=currency_code).first() if currency_code else None
        if not currency:
            err(f'Currency "{currency_code}" not found — it is required.'); continue

        try:
            outstanding = float(cell(row, 'Outstanding Amount') or 0)
            if outstanding <= 0:
                raise ValueError
        except (TypeError, ValueError):
            err('Outstanding Amount must be a positive number.'); continue

        try:
            approved = float(cell(row, 'Approved Amount'))
            if approved < 0:
                raise ValueError
        except (TypeError, ValueError):
            err('Approved Amount must be a number.'); continue

        def num(header):
            try:
                return float(cell(row, header) or 0)
            except (TypeError, ValueError):
                return 0.0
        principal = num('Principal Amount')

        promise_date = _parse_import_date(cell(row, 'Promise Date'))
        if status in Case.DATE_REQUIRED_STATUSES and not promise_date:
            err('This Case Status requires a Promise Date column value.'); continue

        if Case.objects.filter(client=client, account_no__iexact=account_no).exists():
            err(f'Account Number "{account_no}" already exists for client "{client.name}".'); continue

        agency_name = str(cell(row, 'Agency Name')).strip()
        agency = None
        if agency_name:
            agency = Agency.objects.filter(name__iexact=agency_name, status='active').first()
            if not agency:
                err(f'Agency "{agency_name}" not found in Settings → Agencies.'); continue

        debtor = Debtor.objects.filter(name__iexact=debtor_name).first()
        debtor_created = False
        if not debtor:
            is_company = str(cell(row, 'Is Company')).strip().lower() in truthy
            gender_raw = str(cell(row, 'Gender')).strip().lower()
            gender = gender_by_label.get(gender_raw) or (gender_raw if gender_raw in gender_keys else '')
            id_or_cr = str(cell(row, 'ID Number/CR Number')).strip()
            debtor = Debtor.objects.create(
                name=debtor_display,
                is_organization=is_company,
                gender=gender,
                nationality=str(cell(row, 'Nationality')).strip(),
                cr_no=id_or_cr if is_company else '',
                id_number=id_or_cr if not is_company else '',
                state=str(cell(row, 'State')).strip(),
                country=str(cell(row, 'Country')).strip(),
                phone=str(cell(row, 'Phone Number')).strip(),
                status='active',
                created_by=request.user if request.user.is_authenticated else None,
            )
            debtor_created = True

        case = Case(
            client=client,
            debtor=debtor,
            case_type=case_type,
            account_no=account_no,
            relationship_no=str(cell(row, 'Relationship Number')).strip(),
            shadow_account_no=str(cell(row, 'Shadow Account')).strip(),
            cif_no=str(cell(row, 'CIF Number')).strip(),
            status=status,
            collector=collector,
            received_date=received_date,
            due_date=_parse_import_date(cell(row, 'Due Date')),
            case_country=country,
            outstanding_amount=outstanding,
            principal_amount=principal,
            approved_amount=approved,
            received_amount=0,
            currency=currency,
            promise_to_pay_date=promise_date,
            creditor_name=creditor_name,
            is_agency=bool(agency),
            agency=agency,
            notes=str(cell(row, 'Notes')).strip(),
        )
        case.save()
        _log_case(request, case, 'Case Created via Excel Import')
        _grant_full_client_case_access(case)
        created += 1
        results.append({'row': rownum, 'ok': True,
                        'message': f'{case.case_id} created' + (' (new debtor)' if debtor_created else ''),
                        'case_id': case.case_id})
    return None, results, created


@admin_required
def import_new_view(request):
    header_error, results, created = None, [], 0
    if request.method == 'POST':
        if not request.FILES.get('file'):
            header_error = 'Choose an Excel (.xlsx) file to import.'
        else:
            header_error, results, created = _import_cases_from_workbook(request, request.FILES['file'])
            if not header_error:
                ActivityLog.objects.create(
                    user=request.user, log_type='general',
                    action=f'Bulk case import: {created} case(s) created, {sum(1 for r in results if not r["ok"])} row(s) rejected.',
                    ip_address=_secure_client_ip(request) or None,
                )
    return render(request, 'settings_import_new.html', {
        'active_page': 'settings_import_new', 'active_sub': 'settings_import_new',
        'header_error': header_error,
        'results': results,
        'created': created,
        'failed': sum(1 for r in results if not r['ok']),
        'required_cols': CASE_IMPORT_REQUIRED,
        'optional_cols': CASE_IMPORT_OPTIONAL,
    })


@admin_required
def import_case_sample(request):
    """Downloadable sample sheet with the exact headers the importer accepts
    (mandatory columns filled red, matching the reference layout), one
    example row, and a Valid Values reference sheet."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = 'Cases'
    headers = CASE_IMPORT_REQUIRED + CASE_IMPORT_OPTIONAL
    ws.append(headers)
    required_fill = PatternFill('solid', fgColor='C00000')
    optional_fill = PatternFill('solid', fgColor='808080')
    for i, c in enumerate(ws[1]):
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = required_fill if headers[i] in CASE_IMPORT_REQUIRED else optional_fill

    sample_client = Client.objects.filter(status='active').first()
    sample_collector = User.objects.filter(is_active=True).first()
    sample_case_type = CaseType.objects.filter(is_enabled=True).first()
    sample_values = {
        'Client': sample_client.name if sample_client else 'Client Name (must exist)',
        'Debtor': 'Ahmed Al Example',
        'Name': 'Ahmed Al Example',
        'Creditor Name': sample_client.name if sample_client else 'Creditor Name',
        'Received On': '2026-07-01',
        'Case Type': sample_case_type.name if sample_case_type else 'Case Type',
        'Account Number': 'ACC-1001',
        'Case Status': 'Active',
        'Collector': (sample_collector.get_full_name() or sample_collector.username) if sample_collector else 'collector username',
        'Case Country': 'Oman',
        'Currency': 'OMR',
        'Outstanding Amount': 1500.000,
        'Approved Amount': 1400.000,
        'Is Company': 'No',
        'Gender': 'Male',
        'Nationality': 'Omani',
        'ID Number/CR Number': '123456789',
        'State': 'Muscat',
        'Country': 'Oman',
        'Due Date': '',
        'Relationship Number': '',
        'Shadow Account': '',
        'CIF Number': '',
        'Agency Name': '',
        'Phone Number': '+968 91234567',
        'Notes': 'Imported case',
        'Principal Amount': 1500.000,
        'Promise Date': '',
    }
    ws.append([sample_values.get(h, '') for h in headers])
    for i, h in enumerate(headers, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(14, len(h) + 4)

    ref = wb.create_sheet('Valid Values')
    ref.append(['Case Statuses', 'Case Types', 'Collectors', 'Currencies', 'Agencies'])
    for c in ref[1]:
        c.font = Font(bold=True)
    statuses   = [label for _, label in Case.all_status_choices()]
    types      = list(CaseType.objects.filter(is_enabled=True).values_list('name', flat=True))
    collectors = [(u.get_full_name() or u.username) for u in User.objects.filter(is_active=True)]
    currencies = list(Currency.objects.values_list('code', flat=True))
    agencies   = list(Agency.objects.filter(status='active').values_list('name', flat=True))
    for i in range(max(len(statuses), len(types), len(collectors), len(currencies), len(agencies))):
        ref.append([
            statuses[i] if i < len(statuses) else '',
            types[i] if i < len(types) else '',
            collectors[i] if i < len(collectors) else '',
            currencies[i] if i < len(currencies) else '',
            agencies[i] if i < len(agencies) else '',
        ])
    for col, width in zip('ABCDE', (28, 24, 24, 12, 24)):
        ref.column_dimensions[col].width = width

    resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="case_import_sample.xlsx"'
    wb.save(resp)
    return resp


def receipt_report(request):
    date_from    = request.GET.get('date_from', '')
    date_to      = request.GET.get('date_to', '')
    rcpt_from    = request.GET.get('rcpt_from', '')
    rcpt_to      = request.GET.get('rcpt_to', '')
    mode         = request.GET.get('mode', '')
    collector_id = request.GET.get('collector', '')
    cancelled    = request.GET.get('cancelled', '')
    submitted    = request.GET.get('submitted', '')

    date_range = ''
    if date_from and date_to:
        date_range = f'{date_from} to {date_to}'
    elif date_from:
        date_range = date_from

    qs = _scope_payments_to_staff(request, Payment.objects.filter(is_installment=False).select_related(
        'case', 'case__client', 'case__debtor', 'case__collector', 'created_by', 'payment_mode'
    ).order_by('-payment_date', '-created_at'))

    if submitted:
        if date_from:
            qs = qs.filter(payment_date__gte=date_from)
        if date_to:
            qs = qs.filter(payment_date__lte=date_to)
        # payment_ids are zero-padded ("TWZ/PAY/2026/0001"), so string
        # comparison orders them correctly.
        if rcpt_from:
            qs = qs.filter(payment_id__gte=rcpt_from)
        if rcpt_to:
            qs = qs.filter(payment_id__lte=rcpt_to)
        if mode:
            qs = qs.filter(payment_mode_id=mode)
        if collector_id:
            qs = qs.filter(case__collector_id=collector_id)
        if cancelled:
            qs = qs.filter(status='bounced')
    else:
        qs = qs.none()

    # Dropdown options: value = the stored payment_id, label = receipt (RPT) form.
    all_payment_ids = [
        {'value': pid, 'label': pid.replace('/PAY/', '/RPT/')}
        for pid in Payment.objects.filter(is_installment=False)
                                  .values_list('payment_id', flat=True).order_by('payment_id')
    ]
    all_collectors  = User.objects.filter(cases_collected__isnull=False).distinct().order_by('first_name', 'username')

    # Mode dropdown in the canonical order (Tawazon receipt modes first).
    _order = {name: i for i, name in enumerate(
        ('Cash in Tawazon', 'Transfer to Tawazon', 'Cheque to Tawazon', 'Direct to Client', 'Cheque to Client'))}
    payment_modes = sorted(PaymentMode.objects.filter(is_enabled=True),
                           key=lambda m: _order.get(m.name, len(_order)))

    return render(request, 'reports_receipt.html', {
        'active_page':     'reports',
        'active_sub':      'report_receipt',
        'receipts':        qs,
        'all_payment_ids': all_payment_ids,
        'all_collectors':  all_collectors,
        'payment_modes':   payment_modes,
        'filter': {
            'date_from':  date_from,
            'date_to':    date_to,
            'date_range': date_range,
            'rcpt_from':  rcpt_from,
            'rcpt_to':    rcpt_to,
            'mode':       mode,
            'collector':  collector_id,
            'cancelled':  cancelled,
            'submitted':  submitted,
        },
    })


# ---------- ACTIVITY LOGS ----------
def activity_logs(request):
    date_from    = request.GET.get('date_from', '')
    date_to      = request.GET.get('date_to', '')
    user_id      = request.GET.get('user', '')
    log_type     = request.GET.get('log_type', '')
    filtered     = request.GET.get('filtered', '')

    date_range = ''
    if date_from and date_to:
        from datetime import datetime
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d')
            dt = datetime.strptime(date_to,   '%Y-%m-%d')
            date_range = f'{df:%m/%d/%Y} - {dt:%m/%d/%Y}'
        except ValueError:
            date_range = f'{date_from} - {date_to}'
    elif date_from:
        date_range = date_from

    qs = ActivityLog.objects.select_related('user').order_by('-created_at')
    # Staff only ever see their own activity; the user filter is admin-only.
    if not request.user.is_superuser:
        qs = qs.filter(user=request.user)
        user_id = ''

    if filtered:
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if log_type:
            qs = qs.filter(log_type=log_type)

    # Staff can only filter within themselves; admins see everyone.
    if request.user.is_superuser:
        all_users = User.objects.order_by('first_name', 'username')
    else:
        all_users = User.objects.filter(pk=request.user.pk)

    return render(request, 'settings_activity_logs.html', {
        'active_page':  'settings',
        'active_sub':   'activity_logs',
        'logs':         qs,
        'all_users':    all_users,
        'log_types':    ActivityLog.LOG_TYPE_CHOICES,
        'filter': {
            'date_from':  date_from,
            'date_to':    date_to,
            'date_range': date_range,
            'user':       user_id,
            'log_type':   log_type,
            'filtered':   filtered,
        },
    })


# ---------- NEW / ADDITIONAL ALLOCATION REPORT ----------
def new_allocation_report(request):
    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to', '')

    date_range = ''
    if date_from and date_to:
        date_range = f'{date_from} to {date_to}'
    elif date_from:
        date_range = date_from

    # Tracked by Received Date (when the case actually came in), not the
    # created_at row-insert timestamp. Shows everything by default, same as
    # the other rebuilt reports — a date range narrows it, it doesn't gate it.
    qs = _scope_cases_to_staff(request, Case.objects.select_related('client', 'debtor', 'collector').order_by('-received_date'))

    if date_from:
        qs = qs.filter(received_date__gte=date_from)
    if date_to:
        qs = qs.filter(received_date__lte=date_to)

    agg = qs.aggregate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
    total_cases     = agg['count'] or 0
    total_approved  = float(agg['approved'] or 0)
    total_received  = float(agg['received'] or 0)
    total_remaining = total_approved - total_received
    total_clients   = qs.values('client').distinct().count()

    return render(request, 'reports_new_allocation.html', {
        'active_page': 'reports',
        'active_sub':  'report_new_allocation',
        'cases':       qs,
        'total_clients':   total_clients,
        'total_cases':     total_cases,
        'total_approved':  total_approved,
        'total_received':  total_received,
        'total_remaining': total_remaining,
        'filter': {
            'date_from':  date_from,
            'date_to':    date_to,
            'date_range': date_range,
        },
    })


# ---------- COMMISSION REPORT ----------
def commission_report(request):
    import json as _json
    from django.db.models import Sum, Count

    collector_id = request.GET.get('collector', '')
    client_id    = request.GET.get('client', '')
    debtor_id    = request.GET.get('debtor', '')
    date_from    = request.GET.get('date_from', '')
    date_to      = request.GET.get('date_to', '')
    agency_id    = request.GET.get('agency', '')
    lawyer_id    = request.GET.get('lawyer', '')
    case_status  = request.GET.get('case_status', '')
    submitted    = request.GET.get('submitted', '')

    date_range = ''
    if date_from and date_to:
        date_range = f'{date_from} to {date_to}'
    elif date_from:
        date_range = date_from

    qs = _scope_payments_to_staff(request, Payment.objects.select_related(
        'case', 'case__client', 'case__debtor', 'case__collector', 'created_by'
    ).order_by('-payment_date'))

    if submitted:
        if date_from:
            qs = qs.filter(payment_date__gte=date_from)
        if date_to:
            qs = qs.filter(payment_date__lte=date_to)
        if collector_id:
            qs = qs.filter(case__collector_id=collector_id)
        if client_id:
            qs = qs.filter(case__client_id=client_id)
        if debtor_id:
            qs = qs.filter(case__debtor_id=debtor_id)
        if case_status:
            qs = qs.filter(case__status=case_status)

    # ---- Aggregations ----
    # 1. By client
    by_client = (
        qs.values('case__client__name')
        .annotate(count=Count('id'), total=Sum('amount'))
        .order_by('-total')
    )
    client_labels  = [r['case__client__name'] or '—' for r in by_client]
    client_totals  = [float(r['total'] or 0) for r in by_client]
    client_counts  = sum(r['count'] for r in by_client)
    client_sum     = sum(r['total'] or 0 for r in by_client)
    client_unique  = len(client_labels)

    # 2. By client type
    by_ctype = (
        qs.values('case__client__client_type')
        .annotate(count=Count('id'), total=Sum('amount'))
        .order_by('-total')
    )
    ctype_labels = [r['case__client__client_type'] or '—' for r in by_ctype]
    ctype_totals = [float(r['total'] or 0) for r in by_ctype]
    ctype_counts = sum(r['count'] for r in by_ctype)
    ctype_sum    = sum(r['total'] or 0 for r in by_ctype)
    ctype_unique = len(ctype_labels)

    # 3. By case status
    by_status = (
        qs.values('case__status')
        .annotate(count=Count('id'), total=Sum('amount'))
        .order_by('-total')
    )
    status_labels = [r['case__status'] or '—' for r in by_status]
    status_totals = [float(r['total'] or 0) for r in by_status]
    status_counts = sum(r['count'] for r in by_status)
    status_sum    = sum(r['total'] or 0 for r in by_status)
    status_unique = len(status_labels)

    # 4. By country (debtor nationality)
    by_country = (
        qs.values('case__debtor__nationality')
        .annotate(count=Count('id'), total=Sum('amount'))
        .order_by('-total')
    )
    country_labels = [r['case__debtor__nationality'] or 'Unknown' for r in by_country]
    country_totals = [float(r['total'] or 0) for r in by_country]
    country_counts = sum(r['count'] for r in by_country)
    country_sum    = sum(r['total'] or 0 for r in by_country)
    country_unique = len(country_labels)

    # 5. By collector
    by_collector = (
        qs.values('case__collector__first_name', 'case__collector__last_name', 'case__collector__username')
        .annotate(count=Count('id'), total=Sum('amount'))
        .order_by('-total')
    )
    def _cname(r):
        fn = (r['case__collector__first_name'] or '').strip()
        ln = (r['case__collector__last_name'] or '').strip()
        return (fn + ' ' + ln).strip() or r['case__collector__username'] or '—'
    collector_labels = [_cname(r) for r in by_collector]
    collector_totals = [float(r['total'] or 0) for r in by_collector]
    collector_counts = sum(r['count'] for r in by_collector)
    collector_sum    = sum(r['total'] or 0 for r in by_collector)
    collector_unique = len(collector_labels)

    # 6. Lawyer wise (using LegalCase.lawyer_name)
    lawyer_rows = []
    if submitted:
        from django.db.models import IntegerField
        lqs = LegalCase.objects.filter(case__in=qs.values('case')).values('lawyer_name').annotate(
            count=Count('id'), total=Sum('case__payments__amount')
        )
        lawyer_rows = list(lqs)

    # 7. Drop-down data
    all_collectors  = User.objects.filter(cases_collected__isnull=False).distinct().order_by('first_name', 'username')
    all_clients     = Client.objects.filter(status='active').order_by('name')
    all_debtors     = Debtor.objects.order_by('first_name', 'last_name')
    all_agencies    = Agency.objects.order_by('name')
    all_lawyers     = Lawyer.objects.order_by('name')
    case_statuses   = Case.all_status_choices()

    CHART_COLORS = ['#3b5fc0','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#f97316','#ec4899','#6366f1','#14b8a6']

    return render(request, 'reports_commission.html', {
        'active_page': 'reports',
        'active_sub':  'report_commission',
        'payments':    qs,
        'filter': {
            'collector':  collector_id, 'client':  client_id,
            'debtor':     debtor_id,    'date_from': date_from,
            'date_to':    date_to,      'date_range': date_range,
            'agency':     agency_id,    'lawyer': lawyer_id,
            'case_status': case_status, 'submitted': submitted,
        },
        'all_collectors': all_collectors,
        'all_clients':    all_clients,
        'all_debtors':    all_debtors,
        'all_agencies':   all_agencies,
        'all_lawyers':    all_lawyers,
        'case_statuses':  case_statuses,
        # by-client
        'client_labels':  _json.dumps(client_labels),
        'client_totals':  _json.dumps(client_totals),
        'client_unique':  client_unique,
        'client_counts':  client_counts,
        'client_sum':     float(client_sum),
        # by-client-type
        'ctype_labels':   _json.dumps(ctype_labels),
        'ctype_totals':   _json.dumps(ctype_totals),
        'ctype_unique':   ctype_unique,
        'ctype_counts':   ctype_counts,
        'ctype_sum':      float(ctype_sum),
        # by-status
        'status_labels':  _json.dumps(status_labels),
        'status_totals':  _json.dumps(status_totals),
        'status_unique':  status_unique,
        'status_counts':  status_counts,
        'status_sum':     float(status_sum),
        # by-country
        'country_labels': _json.dumps(country_labels),
        'country_totals': _json.dumps(country_totals),
        'country_unique': country_unique,
        'country_counts': country_counts,
        'country_sum':    float(country_sum),
        # by-collector
        'collector_labels': _json.dumps(collector_labels),
        'collector_totals': _json.dumps(collector_totals),
        'collector_unique': collector_unique,
        'collector_counts': collector_counts,
        'collector_sum':    float(collector_sum),
        # lawyer
        'lawyer_rows':    lawyer_rows,
        # chart colors
        'chart_colors':   _json.dumps(CHART_COLORS),
    })


# ---------- COLLECTION REPORT ----------
def collection_report(request):
    collector_id = request.GET.get('collector', '')
    client_id    = request.GET.get('client', '')
    debtor_id    = request.GET.get('debtor', '')
    date_from    = request.GET.get('date_from', '')
    date_to      = request.GET.get('date_to', '')
    agency_id    = request.GET.get('agency', '')
    lawyer_id    = request.GET.get('lawyer', '')
    case_status  = request.GET.get('case_status', '')

    date_range = ''
    if date_from and date_to:
        date_range = f'{date_from} to {date_to}'
    elif date_from:
        date_range = date_from

    # Everything below is scoped to this queryset of actual collected payments
    # (not cases) — filters apply directly, matching the other reports.
    # Agency and Lawyer used to be collected here but never applied — both are
    # wired up now.
    qs = _scope_payments_to_staff(request, Payment.objects.filter(is_installment=False).select_related(
        'case', 'case__client', 'case__debtor', 'case__collector', 'case__agency'
    ).order_by('-payment_date'))

    if date_from:
        qs = qs.filter(payment_date__gte=date_from)
    if date_to:
        qs = qs.filter(payment_date__lte=date_to)
    if collector_id:
        qs = qs.filter(case__collector_id=collector_id)
    if client_id:
        qs = qs.filter(case__client_id=client_id)
    if debtor_id:
        qs = qs.filter(case__debtor_id=debtor_id)
    if agency_id:
        qs = qs.filter(case__agency_id=agency_id)
    if lawyer_id:
        qs = qs.filter(case__legal_case__lawyer_id=lawyer_id)
    if case_status:
        qs = qs.filter(case__status=case_status)

    def build_stats(sub_qs):
        agg = sub_qs.aggregate(count=Count('id'), amount=Sum('amount'))
        return {'count': agg['count'] or 0, 'amount': float(agg['amount'] or 0)}

    # Client Wise Collection (leads — this is the Collections report)
    client_agg = qs.values('case__client__name').annotate(count=Count('id'), amount=Sum('amount')).order_by('-amount')
    client_rows = [{'label': r['case__client__name'] or 'Unknown', 'count': r['count'], 'amount': float(r['amount'] or 0)} for r in client_agg]

    # Client Type
    client_type_rows = []
    for ct_val, ct_label in Client.CLIENT_TYPE_CHOICES:
        s = build_stats(qs.filter(case__client__client_type=ct_val))
        if s['count'] > 0:
            client_type_rows.append({'label': ct_label, **s})

    # Payment Method
    method_agg = qs.values('payment_method').annotate(count=Count('id'), amount=Sum('amount')).order_by('-amount')
    method_display = dict(Payment.METHOD_CHOICES)
    method_rows = [{'label': method_display.get(r['payment_method'], r['payment_method'] or 'Unknown'), 'count': r['count'], 'amount': float(r['amount'] or 0)} for r in method_agg]

    # Country Distribution
    country_agg = qs.values('case__debtor__country').annotate(count=Count('id'), amount=Sum('amount')).order_by('-amount')
    country_rows = [{'label': r['case__debtor__country'] or 'Unknown', 'count': r['count'], 'amount': float(r['amount'] or 0)} for r in country_agg]

    # Agency Wise Collection — previously a hardcoded "No data" stub; now a
    # real breakdown since Case.agency exists.
    agency_agg = qs.values('case__agency__name').annotate(count=Count('id'), amount=Sum('amount')).order_by('-amount')
    agency_rows = [{'label': r['case__agency__name'] or 'No Agency', 'count': r['count'], 'amount': float(r['amount'] or 0)} for r in agency_agg]

    # Collector Wise Collection
    collector_agg = (
        qs.values('case__collector__id', 'case__collector__username', 'case__collector__first_name', 'case__collector__last_name')
        .annotate(count=Count('id'), amount=Sum('amount')).order_by('-amount')
    )
    collector_rows = []
    for r in collector_agg:
        first = r['case__collector__first_name'] or ''
        last = r['case__collector__last_name'] or ''
        name = f"{first} {last}".strip() or r['case__collector__username'] or 'Unassigned'
        collector_rows.append({'label': name, 'count': r['count'], 'amount': float(r['amount'] or 0)})

    # Lawyer Wise Collection — previously only computed when a "submitted"
    # flag was present and in a raw, differently-shaped dict; normalized here.
    lawyer_agg = (
        qs.filter(case__legal_case__isnull=False)
        .values('case__legal_case__lawyer__name', 'case__legal_case__lawyer_name')
        .annotate(count=Count('id'), amount=Sum('amount'))
    )
    lawyer_merged = {}
    for r in lawyer_agg:
        label = r['case__legal_case__lawyer__name'] or r['case__legal_case__lawyer_name'] or 'Unknown'
        m = lawyer_merged.setdefault(label, {'label': label, 'count': 0, 'amount': 0.0})
        m['count'] += r['count']
        m['amount'] += float(r['amount'] or 0)
    lawyer_rows = sorted(lawyer_merged.values(), key=lambda r: r['label'].lower())

    # Collections Over Time — monthly / quarterly / yearly groupings within
    # the current filters (pick a date range, then flip the period client-side).
    from django.db.models.functions import TruncMonth, TruncQuarter, TruncYear

    def _period_rows(trunc, label_fn):
        agg = (qs.annotate(p=trunc('payment_date')).values('p')
               .annotate(count=Count('id'), amount=Sum('amount')).order_by('p'))
        return [{'label': label_fn(r['p']), 'count': r['count'], 'amount': float(r['amount'] or 0)}
                for r in agg if r['p']]

    period_rows = {
        'monthly':   _period_rows(TruncMonth,   lambda d: d.strftime('%b %Y')),
        'quarterly': _period_rows(TruncQuarter, lambda d: f'Q{(d.month - 1) // 3 + 1} {d.year}'),
        'yearly':    _period_rows(TruncYear,    lambda d: str(d.year)),
    }

    total_count  = qs.count()
    total_amount = float(qs.aggregate(s=Sum('amount'))['s'] or 0)
    total_clients = qs.values('case__client').distinct().count()

    all_collectors = User.objects.filter(cases_collected__isnull=False).distinct().order_by('first_name', 'username')
    all_clients    = Client.objects.filter(status='active').order_by('name')
    all_debtors    = Debtor.objects.order_by('first_name', 'last_name')
    all_agencies   = Agency.objects.order_by('name')
    all_lawyers    = Lawyer.objects.order_by('name')
    case_statuses  = Case.all_status_choices()

    return render(request, 'reports_collection.html', {
        'active_page': 'reports',
        'active_sub':  'report_collection',
        'payments':    qs,
        'total_count':   total_count,
        'total_amount':  total_amount,
        'total_clients': total_clients,
        'filter': {
            'collector': collector_id, 'client':  client_id,
            'debtor':    debtor_id,    'date_from': date_from,
            'date_to':   date_to,     'date_range': date_range,
            'agency':    agency_id,   'lawyer': lawyer_id,
            'case_status': case_status,
        },
        'all_collectors': all_collectors,
        'all_clients':    all_clients,
        'all_debtors':    all_debtors,
        'all_agencies':   all_agencies,
        'all_lawyers':    all_lawyers,
        'case_statuses':  case_statuses,
        'client_rows_json':      json.dumps(client_rows),
        'client_type_rows_json': json.dumps(client_type_rows),
        'method_rows_json':      json.dumps(method_rows),
        'period_rows_json':      json.dumps(period_rows),
        'country_rows_json':     json.dumps(country_rows),
        'agency_rows_json':      json.dumps(agency_rows),
        'collector_rows_json':   json.dumps(collector_rows),
        'lawyer_rows_json':      json.dumps(lawyer_rows),
    })


# ---------- CLIENT REPORT ----------
def client_report(request):
    client_ids = [c for c in request.GET.getlist('clients') if c.strip()]

    # Everything below is scoped to this queryset — picking client(s) drills
    # the whole page into just their cases, the same way the Cases/Collector
    # reports' filters scope every one of their sections.
    qs = _scope_cases_to_staff(request, Case.objects.select_related('client', 'debtor', 'collector'))
    if client_ids:
        qs = qs.filter(client_id__in=client_ids)

    agg = qs.aggregate(total_approved=Sum('approved_amount'), total_received=Sum('received_amount'))
    total_cases = qs.count()
    total_clients = qs.values('client').distinct().count()
    total_approved = float(agg['total_approved'] or 0)
    total_received = float(agg['total_received'] or 0)
    total_remaining = total_approved - total_received

    def build_stats(sub_qs):
        agg2 = sub_qs.aggregate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        approved = float(agg2['approved'] or 0)
        received = float(agg2['received'] or 0)
        return {'count': agg2['count'] or 0, 'approved': approved, 'received': received, 'remaining': approved - received}

    # Client Wise Portfolio (leads — this is the Client report)
    client_agg = (
        qs.values('client__id', 'client__name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    client_rows = []
    for row in client_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        client_rows.append({
            'label': row['client__name'] or 'Unknown',
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # Case Status Overview
    overall_rows = []
    for sv, sl in Case.all_status_choices():
        s = build_stats(qs.filter(status=sv))
        if s['count'] > 0:
            overall_rows.append({'label': sl, **s})

    # Client Type
    client_type_rows = []
    for ct_val, ct_label in Client.CLIENT_TYPE_CHOICES:
        s = build_stats(qs.filter(client__client_type=ct_val))
        if s['count'] > 0:
            client_type_rows.append({'label': ct_label, **s})

    # Client Status
    client_status_rows = []
    for cs_val, cs_label in Client.STATUS_CHOICES:
        s = build_stats(qs.filter(client__status=cs_val))
        if s['count'] > 0:
            client_status_rows.append({'label': cs_label, **s})

    # Country Distribution
    country_agg = (
        qs.values('debtor__country')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    country_rows = []
    for row in country_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        country_rows.append({
            'label': row['debtor__country'] or 'Unknown',
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # Collector Wise Portfolio (how the selected client(s)' cases are spread
    # across collectors)
    collector_agg = (
        qs.values('collector__id', 'collector__username', 'collector__first_name', 'collector__last_name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    collector_rows = []
    for row in collector_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        first = row['collector__first_name'] or ''
        last = row['collector__last_name'] or ''
        name = f"{first} {last}".strip() or row['collector__username'] or 'Unassigned'
        collector_rows.append({
            'label': name,
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    all_clients = Client.objects.order_by('name')

    return render(request, 'reports_client.html', {
        'active_page':     'reports',
        'active_sub':      'report_client',
        'cases':           qs.order_by('-created_at'),
        'total_cases':     total_cases,
        'total_clients':   total_clients,
        'total_approved':  total_approved,
        'total_received':  total_received,
        'total_remaining': total_remaining,
        'all_clients':     all_clients,
        'selected_clients': client_ids,
        'client_rows_json': json.dumps(client_rows),
        'overall_rows_json': json.dumps(overall_rows),
        'client_type_rows_json': json.dumps(client_type_rows),
        'client_status_rows_json': json.dumps(client_status_rows),
        'country_rows_json': json.dumps(country_rows),
        'collector_rows_json': json.dumps(collector_rows),
    })


# ---------- AGENCY REPORT ----------
def agency_report(request):
    agency_ids = request.GET.getlist('agencies')

    # Everything below is scoped to this queryset — picking agencies drills
    # the whole page into just their cases, matching the Cases/Collector/
    # Client reports. (Previously this filter was a UI placeholder that never
    # actually filtered anything — Case.agency exists, so it's wired up now.)
    qs = _scope_cases_to_staff(request, Case.objects.select_related('client', 'debtor', 'collector', 'agency'))
    if agency_ids:
        qs = qs.filter(agency_id__in=agency_ids)

    agg = qs.aggregate(total_approved=Sum('approved_amount'), total_received=Sum('received_amount'))
    total_cases = qs.count()
    total_agencies = qs.values('agency').exclude(agency__isnull=True).distinct().count()
    total_approved = float(agg['total_approved'] or 0)
    total_received = float(agg['total_received'] or 0)
    total_remaining = total_approved - total_received

    def build_stats(sub_qs):
        agg2 = sub_qs.aggregate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        approved = float(agg2['approved'] or 0)
        received = float(agg2['received'] or 0)
        return {'count': agg2['count'] or 0, 'approved': approved, 'received': received, 'remaining': approved - received}

    # Agency Wise Portfolio (leads — this is the Agency report)
    agency_agg = (
        qs.values('agency__id', 'agency__name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    agency_rows = []
    for row in agency_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        agency_rows.append({
            'label': row['agency__name'] or 'No Agency',
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # Case Status Overview
    overall_rows = []
    for sv, sl in Case.all_status_choices():
        s = build_stats(qs.filter(status=sv))
        if s['count'] > 0:
            overall_rows.append({'label': sl, **s})

    # Client Wise Portfolio
    client_agg = (
        qs.values('client__id', 'client__name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    client_rows = []
    for row in client_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        client_rows.append({
            'label': row['client__name'] or 'Unknown',
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # Country Distribution
    country_agg = (
        qs.values('debtor__country')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    country_rows = []
    for row in country_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        country_rows.append({
            'label': row['debtor__country'] or 'Unknown',
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    # Collector Wise Portfolio (how the selected agency/agencies' cases are
    # spread across collectors)
    collector_agg = (
        qs.values('collector__id', 'collector__username', 'collector__first_name', 'collector__last_name')
        .annotate(count=Count('id'), approved=Sum('approved_amount'), received=Sum('received_amount'))
        .order_by('-count')
    )
    collector_rows = []
    for row in collector_agg:
        approved = float(row['approved'] or 0)
        received = float(row['received'] or 0)
        first = row['collector__first_name'] or ''
        last = row['collector__last_name'] or ''
        name = f"{first} {last}".strip() or row['collector__username'] or 'Unassigned'
        collector_rows.append({
            'label': name,
            'count': row['count'],
            'approved': approved,
            'received': received,
            'remaining': approved - received,
        })

    all_agencies = Agency.objects.order_by('name')

    return render(request, 'reports_agency.html', {
        'active_page':     'reports',
        'active_sub':      'report_agency',
        'cases':           qs.order_by('-created_at'),
        'total_cases':     total_cases,
        'total_agencies':  total_agencies,
        'total_approved':  total_approved,
        'total_received':  total_received,
        'total_remaining': total_remaining,
        'all_agencies':    all_agencies,
        'selected_agencies': agency_ids,
        'agency_rows_json': json.dumps(agency_rows),
        'overall_rows_json': json.dumps(overall_rows),
        'client_rows_json': json.dumps(client_rows),
        'country_rows_json': json.dumps(country_rows),
        'collector_rows_json': json.dumps(collector_rows),
    })


# ---------- DEBTOR REPORT ----------
def debtor_report(request):
    from django.db.models import Sum, Count

    submitted  = request.GET.get('submitted', '')
    debtor_ids = request.GET.getlist('debtors')

    qs = _scope_cases_to_staff(request, Case.objects.select_related('debtor', 'client', 'collector').order_by('debtor__first_name', 'debtor__last_name'))

    if submitted and debtor_ids:
        qs = qs.filter(debtor_id__in=debtor_ids)

    # Grand totals
    agg = qs.aggregate(
        total_approved=Sum('approved_amount'),
        total_received=Sum('received_amount'),
    )
    total_cases     = qs.count()
    total_debtors   = qs.values('debtor').distinct().count()
    total_approved  = float(agg['total_approved'] or 0)
    total_received  = float(agg['total_received'] or 0)
    total_remaining = total_approved - total_received

    # Debtor-wise aggregation
    by_debtor = (
        qs.values(
            'debtor__id', 'debtor__first_name', 'debtor__middle_name', 'debtor__last_name',
            'debtor__is_organization',
        )
        .annotate(
            case_count=Count('id'),
            approved=Sum('approved_amount'),
            received=Sum('received_amount'),
        )
        .order_by('debtor__first_name', 'debtor__last_name')
    )

    # Build rows
    debtor_rows = []
    for r in by_debtor:
        fn  = (r['debtor__first_name'] or '').strip()
        mn  = (r['debtor__middle_name'] or '').strip()
        ln  = (r['debtor__last_name'] or '').strip()
        name = ' '.join(filter(None, [fn, mn, ln])) or '—'
        approved  = float(r['approved']  or 0)
        received  = float(r['received']  or 0)
        remaining = approved - received
        debtor_rows.append({
            'name':      name,
            'case_count': r['case_count'],
            'approved':  approved,
            'received':  received,
            'remaining': remaining,
        })

    all_debtors = Debtor.objects.order_by('first_name', 'last_name')

    return render(request, 'reports_debtor.html', {
        'active_page':      'reports',
        'active_sub':       'report_debtor',
        'total_cases':      total_cases,
        'total_debtors':    total_debtors,
        'total_approved':   total_approved,
        'total_received':   total_received,
        'total_remaining':  total_remaining,
        'debtor_rows':      debtor_rows,
        'all_debtors':      all_debtors,
        'selected_debtors': debtor_ids,
        'submitted':        submitted,
    })


# ---------- CLIENT LOGIN ACCESS (admin only) ----------
@admin_required
def client_login_access_list(request):
    accesses    = ClientLoginAccess.objects.select_related('client').order_by('-created_at')
    all_clients = Client.objects.filter(status='active').order_by('name')
    return render(request, 'settings_client_login_access.html', {
        'active_page': 'settings_cam',
        'active_sub':  'settings_client_access',
        'accesses':    accesses,
        'all_clients': all_clients,
    })


@admin_required
@require_POST
def client_login_access_create(request):
    from django.contrib.auth.hashers import make_password as _make_password
    client_id  = request.POST.get('client')
    email      = request.POST.get('email', '').strip()
    password   = request.POST.get('password', '').strip()
    vis_date   = request.POST.get('visible_date_from') or None
    is_enabled = request.POST.get('is_enabled') == '1'

    # Password is not required: clients log in with email + OTP, never a password.
    if not client_id or not email:
        return JsonResponse({'success': False, 'error': 'Client and email are required.'})
    if not _valid_email(email):
        return JsonResponse({'success': False, 'error': 'Please enter a valid email address.'})

    try:
        client = Client.objects.get(pk=client_id)
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid client.'})

    acc = ClientLoginAccess.objects.create(
        client=client,
        email=email,
        # store a hashed password only if one was supplied, else an unusable one
        password=_make_password(password) if password else _make_password(None),
        visible_date_from=vis_date,
        expires_on=_compute_expiry(request),
        is_enabled=is_enabled,
    )
    # A new login sees every case its client already has, same as a new case
    # is immediately visible to every login the client already has.
    for case in Case.objects.filter(client=client):
        ClientCaseAccess.objects.update_or_create(access=acc, case=case, defaults=_CLIENT_ACCESS_FULL_GRANT)
    return JsonResponse({'success': True, 'id': acc.pk})


@admin_required
@require_POST
def client_login_access_toggle(request):
    pk  = request.POST.get('id')
    acc = get_object_or_404(ClientLoginAccess, pk=pk)
    acc.is_enabled = not acc.is_enabled
    acc.save()
    return JsonResponse({'success': True, 'is_enabled': acc.is_enabled})


@admin_required
@require_POST
def client_login_access_update(request):
    from django.contrib.auth.hashers import make_password as _make_password
    pk         = request.POST.get('id')
    acc        = get_object_or_404(ClientLoginAccess, pk=pk)
    client_id  = request.POST.get('client')
    email      = request.POST.get('email', '').strip()
    password   = request.POST.get('password', '').strip()
    vis_date   = request.POST.get('visible_date_from') or None
    is_enabled = request.POST.get('is_enabled') == '1'

    if not client_id or not email:
        return JsonResponse({'success': False, 'error': 'Client and email are required.'})
    if not _valid_email(email):
        return JsonResponse({'success': False, 'error': 'Please enter a valid email address.'})

    try:
        client = Client.objects.get(pk=client_id)
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid client.'})

    acc.client = client
    acc.email = email
    acc.visible_date_from = vis_date
    acc.is_enabled = is_enabled
    if password:                       # only change the password if a new one was typed
        acc.password = _make_password(password)
    acc.save()
    return JsonResponse({'success': True})


@admin_required
def client_login_access_edit(request, pk):
    acc = get_object_or_404(ClientLoginAccess.objects.select_related('client'), pk=pk)

    PERM_FIELDS = ['status', 'financial', 'collector', 'followup', 'history', 'payment_history', 'attachments']

    if request.method == 'POST':
        client_id  = request.POST.get('client')
        email      = request.POST.get('email', '').strip()
        vis_date   = request.POST.get('visible_date_from') or None
        is_enabled = request.POST.get('is_enabled') == '1'

        if not client_id or not email:
            messages.error(request, 'Client and email are required.')
            return redirect('client_login_access_edit', pk=acc.pk)
        if not _valid_email(email):
            messages.error(request, 'Please enter a valid email address.')
            return redirect('client_login_access_edit', pk=acc.pk)

        try:
            acc.client = Client.objects.get(pk=client_id)
        except Client.DoesNotExist:
            messages.error(request, 'Invalid client.')
            return redirect('client_login_access_edit', pk=acc.pk)

        acc.email = email
        acc.visible_date_from = vis_date
        acc.expires_on = _compute_expiry(request)
        acc.is_enabled = is_enabled
        acc.save()

        # Per-case permissions
        for cid in request.POST.getlist('case_ids'):
            flags = {f'can_{f}': request.POST.get(f'perm_{cid}_{f}') == '1' for f in PERM_FIELDS}
            if any(flags.values()):
                ClientCaseAccess.objects.update_or_create(access=acc, case_id=cid, defaults=flags)
            else:
                ClientCaseAccess.objects.filter(access=acc, case_id=cid).delete()

        messages.success(request, 'Client login access updated.')
        return redirect('client_login_access_list')

    # GET — build the permission grid for the linked client's cases
    cases = (Case.objects.filter(client=acc.client)
             .select_related('debtor').order_by('case_id'))
    perms = {ca.case_id: ca for ca in acc.case_accesses.all()}
    rows = [{'case': c, 'perm': perms.get(c.pk)} for c in cases]

    return render(request, 'settings_client_login_edit.html', {
        'active_page': 'settings_cam',
        'active_sub':  'settings_client_access',
        'access':      acc,
        'all_clients': Client.objects.filter(status='active').order_by('name'),
        'rows':        rows,
    })


@admin_required
def client_login_access_logs(request, pk):
    acc  = get_object_or_404(ClientLoginAccess.objects.select_related('client'), pk=pk)
    logs = acc.login_logs.all()
    return render(request, 'settings_client_login_logs.html', {
        'active_page': 'settings_cam',
        'active_sub':  'settings_client_access',
        'access':      acc,
        'logs':        logs,
    })


@admin_required
@require_POST
def client_login_access_delete(request):
    pk  = request.POST.get('id')
    acc = get_object_or_404(ClientLoginAccess, pk=pk)
    acc.delete()
    return JsonResponse({'success': True})


# ---------- REMINDERS ----------
def _purge_completed_reminders():
    """Marking a reminder Done keeps it (status 'completed') for 14 days so it
    doesn't vanish suddenly; only after that is it actually deleted. Called
    opportunistically whenever a reminders list is loaded."""
    import datetime
    cutoff = timezone.now() - datetime.timedelta(days=14)
    Reminder.objects.filter(status='completed', completed_at__lt=cutoff).delete()


def _reminder_json(r):
    return {
        'id':          r.pk,
        'case_id':     r.case.case_id if r.case else '—',
        'case_pk':     r.case.pk if r.case else None,
        'client':      r.case.client.name if r.case else '—',
        'debtor':      r.case.debtor.name if r.case else '—',
        'title':       r.title,
        'date':        str(r.reminder_date),
        'other_users': ', '.join(u.get_full_name() or u.username for u in r.other_users.all()),
        'description': r.description,
        'status':      r.status,
    }


def reminders_today(request):
    from django.utils import timezone
    _purge_completed_reminders()
    today = timezone.localdate()
    qs = Reminder.objects.filter(reminder_date=today).select_related('case', 'case__client', 'case__debtor').prefetch_related('other_users')
    return JsonResponse({'reminders': [_reminder_json(r) for r in qs]})


def reminders_tomorrow(request):
    from django.utils import timezone
    import datetime
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)
    qs = Reminder.objects.filter(reminder_date=tomorrow).select_related('case', 'case__client', 'case__debtor').prefetch_related('other_users')
    return JsonResponse({'reminders': [_reminder_json(r) for r in qs]})


def reminders_pending(request):
    from django.utils import timezone
    _purge_completed_reminders()
    today = timezone.localdate()
    # Overdue pending reminders, plus recently-completed ones — a Done row
    # stays visible (as Completed) until the 14-day purge removes it.
    qs = Reminder.objects.filter(reminder_date__lt=today).filter(
        Q(status='pending') | Q(status='completed', completed_at__isnull=False)
    ).select_related('case', 'case__client', 'case__debtor').prefetch_related('other_users')
    return JsonResponse({'reminders': [_reminder_json(r) for r in qs]})


def reminders_payments(request):
    """Payments due as reminders, date-wise — combines two forward-looking
    sources: scheduled installments still pending, and cases whose status is
    "Promise to Pay", by their promised date. Recorded-but-unconfirmed real
    payments are intentionally excluded here — those already have their own
    dedicated Pending Payments page, so listing them here too would just be
    duplicate coverage.

    Marking one "Done" doesn't erase it immediately: it keeps showing here as
    "Completed" for 14 days (matching how Reminder completion already works)
    so a tab switch or reload doesn't make it vanish out from under you, then
    it quietly drops off this list on its own. Nothing is ever deleted from
    the database — real payment history and the case's promise date both stay
    intact either way.
    """
    cutoff = timezone.now() - timedelta(days=14)
    inst_qs = Payment.objects.filter(is_installment=True).filter(
        Q(status='pending') | Q(status='cleared', completed_at__gte=cutoff)
    ).select_related('case', 'case__client', 'case__debtor', 'case__collector')
    promise_qs = Case.objects.filter(
        status='promise_to_pay', promise_to_pay_date__isnull=False
    ).filter(
        Q(promise_completed_at__isnull=True) | Q(promise_completed_at__gte=cutoff)
    ).select_related('client', 'debtor', 'collector')

    data = []
    for p in inst_qs:
        data.append({
            'id': p.pk, 'kind': 'installment',
            'case_id': p.case.case_id, 'case_pk': p.case.pk,
            'client': p.case.client.name, 'debtor': p.case.debtor.name,
            'title': f'Installment Due — {p.payment_id}',
            'date': str(p.payment_date),
            'other_users': p.case.collector.get_full_name() if p.case.collector else '—',
            'description': f'{p.get_payment_method_display()} — {p.amount}',
            'status': 'completed' if p.status == 'cleared' else p.status,
        })
    for c in promise_qs:
        data.append({
            'id': c.pk, 'kind': 'promise',
            'case_id': c.case_id, 'case_pk': c.pk,
            'client': c.client.name, 'debtor': c.debtor.name,
            'title': f'Promise to Pay — {c.case_id}',
            'date': str(c.promise_to_pay_date),
            'other_users': c.collector.get_full_name() if c.collector else '—',
            'description': f'{c.remaining_amount_omr:.3f} OMR',
            'status': 'completed' if c.promise_completed_at else 'promised',
        })
    data.sort(key=lambda r: r['date'])
    return JsonResponse({'reminders': data[:100]})


@require_POST
def case_attachment_upload(request):
    case_id = request.POST.get('case_id', '').strip()
    f = request.FILES.get('file')
    if not case_id or not f:
        return JsonResponse({'success': False, 'message': 'Case and file are required.'})
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Case not found.'})
    att_type_id = request.POST.get('attachment_type_id', '').strip()
    attachment = CaseAttachment.objects.create(
        case=case,
        file=f,
        filename=f.name,
        attachment_type_id=int(att_type_id) if att_type_id else None,
        description=request.POST.get('description', '').strip(),
        uploaded_by=request.user,
    )
    _log_case(request, case, f'Case Attachment Added ({attachment.filename})')
    return JsonResponse({'success': True, 'message': f'File "{attachment.filename}" uploaded.', 'id': attachment.id})


@require_POST
def case_attachment_delete(request):
    att_id = request.POST.get('id', '').strip()
    if not att_id:
        return JsonResponse({'success': False, 'message': 'Attachment ID required.'})
    try:
        att = CaseAttachment.objects.get(pk=att_id)
        att.file.delete(save=False)
        att.delete()
        return JsonResponse({'success': True, 'message': 'Attachment deleted.'})
    except CaseAttachment.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Attachment not found.'})


@require_POST
def reminder_create(request):
    case_id       = request.POST.get('case_id', '').strip()
    title         = request.POST.get('title', '').strip()
    reminder_date = request.POST.get('reminder_date', '').strip()
    description   = request.POST.get('description', '').strip()
    other_user_id = request.POST.get('other_user_id', '').strip()
    if not case_id or not title or not reminder_date:
        return JsonResponse({'success': False, 'message': 'Title and date are required.'})
    try:
        case = Case.objects.get(pk=case_id)
    except Case.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Case not found.'})
    reminder = Reminder.objects.create(
        case=case,
        title=title,
        reminder_date=reminder_date,
        description=description,
        created_by=request.user,
    )
    if other_user_id:
        try:
            other_user = User.objects.get(pk=other_user_id)
            reminder.other_users.add(other_user)
        except User.DoesNotExist:
            pass
    _log_case(request, case, f'Case Reminder Added ({title})')
    return JsonResponse({'success': True, 'message': 'Reminder added.', 'id': reminder.id})


def _reminder_ids(request):
    """Accept either a single id or a list (ids[]) so the same endpoints serve
    the row 'Done' button and the multi-select bulk action."""
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')
    single = request.POST.get('id')
    if single:
        ids.append(single)
    return [i for i in ids if str(i).strip()]


@require_POST
def reminder_complete(request):
    ids = _reminder_ids(request)
    if not ids:
        return JsonResponse({'success': False, 'message': 'No reminders selected.'})
    Reminder.objects.filter(pk__in=ids).update(status='completed', completed_at=timezone.now())
    return JsonResponse({'success': True, 'ids': ids})


@require_POST
def reminder_payment_complete(request):
    """'Done' action for the Payments tab of the Reminders modal — the row's id
    there is a Payment pk, not a Reminder pk, so it needs its own endpoint.
    Stamps completed_at so the row stays visible (as "Completed") for 14 days
    on reload/tab-switch before quietly dropping off — see reminders_payments()."""
    ids = _reminder_ids(request)
    if not ids:
        return JsonResponse({'success': False, 'message': 'No payments selected.'})
    Payment.objects.filter(pk__in=ids).update(status='cleared', completed_at=timezone.now())
    return JsonResponse({'success': True, 'ids': ids})


@require_POST
def reminder_promise_complete(request):
    """'Done' action for a "Promise to Pay" row in the Payments tab — the row's
    id there is a Case pk. Stamps promise_completed_at rather than clearing the
    date outright, so the row stays visible (as "Completed") for 14 days on
    reload/tab-switch before quietly dropping off — see reminders_payments().
    The case's status and promise date are otherwise untouched; staff can still
    update the case's status separately from the case page."""
    ids = _reminder_ids(request)
    if not ids:
        return JsonResponse({'success': False, 'message': 'No cases selected.'})
    cases = Case.objects.filter(pk__in=ids, status='promise_to_pay')
    for case in cases:
        _log_case(request, case, 'Promise to Pay marked done from Reminders')
    cases.update(promise_completed_at=timezone.now())
    return JsonResponse({'success': True, 'ids': ids})


# ---------- TODOS ----------
def todo_list_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        todo = Todo.objects.create(
            title=data.get('title', ''),
            remarks=data.get('remarks', ''),
            date=data.get('date') or None,
            user=request.user,
        )
        return JsonResponse({'success': True, 'id': todo.pk})

    todos = Todo.objects.filter(user=request.user)
    return JsonResponse({'todos': [
        {'id': t.pk, 'title': t.title, 'remarks': t.remarks, 'date': str(t.date) if t.date else ''}
        for t in todos
    ]})


@require_POST
def todo_delete(request):
    pk = request.POST.get('id')
    Todo.objects.filter(pk=pk, user=request.user).delete()
    return JsonResponse({'success': True})


# ---------- CURRENCY CONVERTER ----------
def currency_convert(request):
    # Rates come from Settings -> Currencies (value = units of currency per
    # 1 OMR), limited to the currencies of enabled countries.
    rates = {c.code: float(c.value) for c in enabled_currencies() if c.value}
    amount_str  = request.GET.get('amount', '0')
    from_curr   = request.GET.get('from', 'OMR')
    to_curr     = request.GET.get('to', 'OMR')
    try:
        amount = float(amount_str)
        in_omr = amount / rates.get(from_curr, 1)
        result = in_omr * rates.get(to_curr, 1)
    except (ValueError, ZeroDivisionError):
        result = 0
    return JsonResponse({
        'result':    round(result, 4),
        'from':      from_curr,
        'to':        to_curr,
        'amount':    amount_str,
        'currencies': sorted(rates.keys()),
    })


# ---------- AUTH ----------
ATTENDANCE_SESSION_KEY = 'attendance_session_id'


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            client_ip = _secure_client_ip(request)
            profile = getattr(user, 'profile', None)
            allowed_ips = profile.allowed_ip_list() if profile else []
            if not user.is_superuser and allowed_ips and client_ip not in allowed_ips:
                ActivityLog.objects.create(
                    user=user,
                    log_type='security',
                    action=(
                        f'Blocked login for "{user.username}" from unrecognized IP '
                        f'{client_ip or "unknown"} (allowed: {", ".join(allowed_ips)}).'
                    ),
                    ip_address=client_ip or None,
                )
                error = 'Login blocked from this location. Contact your administrator.'
            else:
                login(request, user)
                ActivityLog.objects.create(
                    user=user,
                    log_type='login',
                    action=f'"{user.username}" logged in.',
                    ip_address=client_ip or None,
                )
                # Open a fresh attendance session (closing any dangling ones first).
                _close_open_sessions(user, AttendanceSession.LOGOUT_RELOGIN)
                now = timezone.now()
                sess = AttendanceSession.objects.create(
                    user=user, login_at=now, last_activity=now,
                    ip_address=_client_ip(request),
                )
                request.session[ATTENDANCE_SESSION_KEY] = sess.id
                return redirect(request.GET.get('next', 'dashboard'))
        else:
            error = 'Invalid username or password.'
    return render(request, 'login.html', {'error': error})


def logout_view(request):
    """End the session. `?auto=1` marks an idle auto-logout. Shows a summary
    page with today's worked hours and an appreciation message."""
    is_auto = request.GET.get('auto') == '1'
    user = request.user if request.user.is_authenticated else None
    summary = None

    if user:
        sess_id = request.session.get(ATTENDANCE_SESSION_KEY)
        sess = AttendanceSession.objects.filter(id=sess_id, user=user).first() if sess_id else None
        if sess is None:
            sess = AttendanceSession.objects.filter(user=user, logout_at__isnull=True).order_by('-login_at').first()
        if sess and sess.is_open:
            sess.close(logout_type=AttendanceSession.LOGOUT_IDLE if is_auto else AttendanceSession.LOGOUT_MANUAL)

        worked = _hours_today(user)
        summary = {
            'name': user.get_full_name() or user.username,
            'logout_time': timezone.localtime(timezone.now()),
            'worked_label': _format_hours(worked),
            'session_label': _format_hours(sess.duration) if sess else '0h 00m',
            'motivation': _motivation_for(worked),
            'auto': is_auto,
        }

    logout(request)
    return render(request, 'logout_summary.html', {'summary': summary})


@login_required
@require_POST
def attendance_heartbeat(request):
    """Called periodically by the browser while the tab is active. Bumps
    `last_activity` so worked-time tracking stays current, and tells the client
    the configured idle limit so the auto-logout countdown stays in sync."""
    sess_id = request.session.get(ATTENDANCE_SESSION_KEY)
    sess = AttendanceSession.objects.filter(id=sess_id, user=request.user).first() if sess_id else None
    if sess is None or not sess.is_open:
        # No session record (e.g. server restart), or the stored one was
        # already closed elsewhere (relogin/idle from another tab) — open a
        # fresh one rather than silently doing nothing for the rest of the visit.
        now = timezone.now()
        sess = AttendanceSession.objects.create(
            user=request.user, login_at=now, last_activity=now,
            ip_address=_client_ip(request),
        )
        request.session[ATTENDANCE_SESSION_KEY] = sess.id
    else:
        sess.last_activity = timezone.now()
        sess.save(update_fields=['last_activity'])
    return JsonResponse({
        'ok': True,
        'idle_limit_seconds': getattr(settings, 'IDLE_LOGOUT_MINUTES', 20) * 60,
        'warning_seconds': getattr(settings, 'IDLE_WARNING_SECONDS', 60),
    })


@login_required
def attendance_report(request):
    """Attendance / hours-worked report. Superusers see every staff member and
    can filter by user; ordinary staff only ever see their own hours."""
    is_admin = request.user.is_superuser

    # Date range (defaults to today). Inclusive of both ends, local time.
    today_local = timezone.localdate()
    try:
        from_date = datetime.strptime(request.GET.get('from', ''), '%Y-%m-%d').date()
    except ValueError:
        from_date = today_local
    try:
        to_date = datetime.strptime(request.GET.get('to', ''), '%Y-%m-%d').date()
    except ValueError:
        to_date = today_local
    if to_date < from_date:
        from_date, to_date = to_date, from_date

    # Build aware [start, end) bounds covering the inclusive local-date range.
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(from_date, dtime.min), tz)
    end = timezone.make_aware(datetime.combine(to_date + timedelta(days=1), dtime.min), tz)

    sessions = (AttendanceSession.objects
                .filter(login_at__gte=start, login_at__lt=end)
                .select_related('user'))

    filter_user = request.GET.get('user', '')
    if not is_admin:
        sessions = sessions.filter(user=request.user)
    elif filter_user:
        sessions = sessions.filter(user_id=filter_user)

    # Aggregate per user in Python (duration depends on last_activity/logout).
    agg = {}
    for s in sessions:
        row = agg.setdefault(s.user_id, {
            'user': s.user, 'total': timedelta(0), 'sessions': 0,
            'first_in': None, 'last_out': None, 'open': False,
        })
        row['total'] += s.duration
        row['sessions'] += 1
        if row['first_in'] is None or s.login_at < row['first_in']:
            row['first_in'] = s.login_at
        end_mark = s.effective_end
        if row['last_out'] is None or end_mark > row['last_out']:
            row['last_out'] = end_mark
        if s.is_open:
            row['open'] = True

    rows = []
    for r in agg.values():
        rows.append({
            'user': r['user'],
            'name': r['user'].get_full_name() or r['user'].username,
            'total_label': _format_hours(r['total']),
            'total_seconds': int(r['total'].total_seconds()),
            'sessions': r['sessions'],
            'first_in': timezone.localtime(r['first_in']) if r['first_in'] else None,
            'last_out': timezone.localtime(r['last_out']) if r['last_out'] else None,
            'open': r['open'],
        })
    rows.sort(key=lambda x: x['total_seconds'], reverse=True)

    grand_total = sum((r['total_seconds'] for r in rows), 0)

    # Recent individual sessions for the detail table.
    detail = []
    for s in sessions.order_by('-login_at')[:200]:
        detail.append({
            'name': s.user.get_full_name() or s.user.username,
            'login_at': timezone.localtime(s.login_at),
            'logout_at': timezone.localtime(s.logout_at) if s.logout_at else None,
            'duration_label': _format_hours(s.duration),
            'open': s.is_open,
            'logout_type': s.get_logout_type_display() if s.logout_type else '',
            'ip': s.ip_address,
        })

    staff = User.objects.filter(is_active=True).order_by('username') if is_admin else None

    return render(request, 'attendance.html', {
        'active_page': 'settings_attendance',
        'active_sub': 'settings_attendance',
        'is_admin': is_admin,
        'rows': rows,
        'detail': detail,
        'from_date': from_date.strftime('%Y-%m-%d'),
        'to_date': to_date.strftime('%Y-%m-%d'),
        'filter_user': filter_user,
        'staff': staff,
        'grand_total_label': _format_hours(timedelta(seconds=grand_total)),
        'today_hours_label': _format_hours(_hours_today(request.user)),
    })


# ---------- CLIENT OTP LOGIN ----------
import logging

logger = logging.getLogger('core.client_otp')

CLIENT_SESSION_KEY = 'client_access_id'


def _client_request_ip(request):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '') or request.META.get('REMOTE_ADDR', '')
    if ',' in ip:
        ip = ip.split(',')[0].strip()
    return ip[:50]


def _active_or_expire(acc):
    """Return the access if it is active. If it has passed its expiry date,
    lazily flip it to disabled (so the admin list reflects it) and return None."""
    if acc is None:
        return None
    if acc.is_expired:
        if acc.is_enabled:
            acc.is_enabled = False
            acc.save(update_fields=['is_enabled'])
        return None
    return acc


def _compute_expiry(request):
    """Read the auto-disable choice from a POST and return an expiry date or None.
    Modes: 'never' | 'date' (expiry_date) | 'days' (expiry_days from today)."""
    mode = request.POST.get('expiry_mode', 'never')
    if mode == 'date':
        return request.POST.get('expiry_date') or None
    if mode == 'days':
        from django.utils import timezone
        from datetime import timedelta
        try:
            days = int(request.POST.get('expiry_days') or 0)
        except ValueError:
            days = 0
        return (timezone.now().date() + timedelta(days=days)) if days > 0 else None
    return None


# Excludes 0/O, 1/I/L — characters that are easy to mistype or misread when a
# client is copying the code out of an email.
CLIENT_OTP_CHARSET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def generate_client_otp_code(length=6):
    import secrets
    return ''.join(secrets.choice(CLIENT_OTP_CHARSET) for _ in range(length))


@require_POST
def client_otp_request(request):
    """Step 1: a client submits their email; we email them a one-time code."""
    from datetime import timedelta
    from django.conf import settings
    from django.contrib.auth.hashers import make_password
    from django.core.mail import send_mail
    from django.utils import timezone

    email = request.POST.get('email', '').strip()
    if not email:
        return JsonResponse({'success': False, 'error': 'Please enter your email address.'})

    acc = (ClientLoginAccess.objects
           .filter(email__iexact=email, is_enabled=True)
           .select_related('client')
           .order_by('-created_at')
           .first())
    acc = _active_or_expire(acc)

    generic = {'success': True, 'message': 'If that email is registered, a code has been sent.'}

    if acc is None:
        logger.warning('OTP request for %r: no active ClientLoginAccess found.', email)
        # Explicitly tell the client this email isn't set up, rather than the
        # generic "code sent" message — trades email-enumeration privacy for a
        # clearer error when staff/testers hit this by mistake.
        return JsonResponse({'success': False, 'error': 'This email is not registered for client portal access. Contact your collection agency for access.'})

    # Invalidate any still-active codes, then issue a fresh one.
    acc.otps.filter(is_used=False).update(is_used=True)
    code = generate_client_otp_code()
    ttl = getattr(settings, 'CLIENT_OTP_TTL_MINUTES', 10)
    ClientLoginOTP.objects.create(
        access=acc,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=ttl),
    )

    subject = 'Your Tawazon login code'
    body = (
        f'Hello,\n\n'
        f'Your one-time login code for the Tawazon client portal is:\n\n'
        f'    {code}\n\n'
        f'This code expires in {ttl} minutes. If you did not request it, you can ignore this email.\n\n'
        f'— Tawazon Data Management System'
    )
    logger.info(
        'OTP request for %s (client %s): backend=%s host=%s user=%s',
        acc.email, acc.client_id, settings.EMAIL_BACKEND, settings.EMAIL_HOST, settings.EMAIL_HOST_USER,
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [acc.email], fail_silently=False)
    except Exception:
        logger.exception('OTP email failed to send for %s via %s.', acc.email, settings.EMAIL_HOST)
        return JsonResponse({'success': False, 'error': 'Could not send the code right now. Please try again later.'})

    logger.info('OTP email sent for %s.', acc.email)
    return JsonResponse(generic)


@require_POST
def client_otp_verify(request):
    """Step 2: the client submits the code; on success we start a portal session."""
    from django.contrib.auth.hashers import check_password
    from django.utils import timezone

    email = request.POST.get('email', '').strip()
    # Codes are generated uppercase; normalise the client's input the same way
    # so typing it in lowercase still matches.
    code  = request.POST.get('otp', '').strip().upper()
    if not email or not code:
        return JsonResponse({'success': False, 'error': 'Email and code are required.'})

    acc = (ClientLoginAccess.objects
           .filter(email__iexact=email, is_enabled=True)
           .order_by('-created_at')
           .first())
    acc = _active_or_expire(acc)
    if acc is None:
        return JsonResponse({'success': False, 'error': 'Invalid or expired code.'})

    otp = acc.otps.filter(is_used=False).order_by('-created_at').first()
    if otp is None or otp.is_expired:
        return JsonResponse({'success': False, 'error': 'Invalid or expired code.'})

    if otp.attempts >= 5:
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        return JsonResponse({'success': False, 'error': 'Too many attempts. Please request a new code.'})

    if not check_password(code, otp.code_hash):
        otp.attempts += 1
        otp.save(update_fields=['attempts'])
        return JsonResponse({'success': False, 'error': 'Invalid or expired code.'})

    # Success — consume the code and start a client portal session.
    otp.is_used = True
    otp.save(update_fields=['is_used'])

    acc.login_count += 1
    acc.last_login = timezone.now()
    acc.save(update_fields=['login_count', 'last_login'])

    request.session[CLIENT_SESSION_KEY] = acc.pk

    ip = _client_request_ip(request) or None
    ClientLoginLog.objects.create(access=acc, ip_address=ip)
    ActivityLog.objects.create(
        log_type='login',
        action=f'Client portal login: {acc.email} ({acc.client.name})',
        ip_address=ip,
    )

    return JsonResponse({'success': True, 'redirect': '/portal/'})


def _current_client_access(request):
    acc_id = request.session.get(CLIENT_SESSION_KEY)
    if not acc_id:
        return None
    acc = (ClientLoginAccess.objects
           .filter(pk=acc_id, is_enabled=True)
           .select_related('client')
           .first())
    return _active_or_expire(acc)


# Fill colors for the client-portal status bar — one saturated tone per status,
# matching the *text* color already used by the .badge classes in
# client_portal.html (so a status reads the same color in the bar and in the
# table below it). Two adjustments from the badge palette:
#  - closed/closed_by_client stays a deliberately muted gray: "closed" is an
#    inactive/terminal state and is meant to visually recede, the same
#    de-emphasis-gray pattern used for a context series elsewhere — not an
#    accidental low-saturation pick.
#  - legal_action_approved is #c2410c here (the badge CSS uses #92400e) —
#    that brown sat too close to refuse_to_pay's red for someone with a color
#    vision deficiency to tell the two apart when their bar segments land
#    next to each other; this is the smallest change that clears validation
#    (validated via dataviz skill's validate_palette.js, both CVD and
#    normal-vision adjacent-pair checks passing for all 8 in any order).
STATUS_BAR_COLORS = {
    'active':                 '#15803d',
    'closed':                 '#64748b',
    'closed_by_client':       '#64748b',
    'broken_promise':         '#b45309',
    'contactable':            '#1d4ed8',
    'promise_to_pay':         '#0d9488',
    'under_tracing':          '#6b21a8',
    'refuse_to_pay':          '#991b1b',
    'legal_action_approved':  '#c2410c',
}
STATUS_BAR_FALLBACK_COLOR = '#475569'  # any other/custom status (Settings → Case Status)


def _status_breakdown(rows):
    """Case count per status, for the client-portal status bar. Only counts
    rows the client is actually allowed to see the status of (mirrors the
    table's own can_status gate) — same reasoning as the financial totals
    only summing can_financial rows."""
    from collections import Counter
    counts = Counter()
    labels = {}
    for row in rows:
        if not row['perm'].can_status:
            continue
        status = row['case'].status
        counts[status] += 1
        labels[status] = row['case'].get_status_display()

    total = sum(counts.values())
    if not total:
        return []

    items = sorted(counts.items(), key=lambda kv: (-kv[1], labels[kv[0]].lower()))

    # Series-count ladder: past 7 slices, fold the smallest tail into "Other"
    # rather than seat an 8th+ distinct hue.
    MAX_SLICES = 7
    if len(items) > MAX_SLICES:
        head, tail = items[:MAX_SLICES - 1], items[MAX_SLICES - 1:]
        other_count = sum(c for _, c in tail)
        items = head + [('__other__', other_count)]
        labels['__other__'] = 'Other'

    breakdown = []
    for status, count in items:
        breakdown.append({
            'slug':  status,
            'label': labels[status],
            'count': count,
            'pct':   round(count / total * 100, 1),
            'color': STATUS_BAR_COLORS.get(status, STATUS_BAR_FALLBACK_COLOR),
        })
    return breakdown


def client_portal(request):
    acc = _current_client_access(request)
    if acc is None:
        request.session.pop(CLIENT_SESSION_KEY, None)
        return redirect('login')

    client = acc.client
    status_colors = case_status_color_map()

    # Only cases the admin has granted this client access to (any permission).
    grants = (acc.case_accesses
              .select_related('case', 'case__debtor', 'case__currency')
              .order_by('case__case_id'))

    rows = []
    total_approved = 0.0
    total_received = 0.0
    for ca in grants:
        if not ca.any_permission:
            continue
        # Same dot-color mechanism as the Legal Cases status badge
        # (case_status_color_map() → Settings → Case Status), so a status
        # reads the same color everywhere in the app, not just here.
        status_color = status_colors.get(ca.case.status, '#8b5cf6')
        rows.append({'case': ca.case, 'perm': ca, 'status_color': status_color})
        # only include amounts the client is actually allowed to see
        if ca.can_financial:
            total_approved += float(ca.case.approved_amount or 0)
            total_received += float(ca.case.received_amount or 0)

    chat_cases = [{'pk': r['case'].pk, 'ref': r['case'].case_id,
                   'debtor': r['case'].debtor.name if r['case'].debtor_id else ''} for r in rows]

    return render(request, 'client_portal.html', {
        'access':           acc,
        'client':           client,
        'rows':             rows,
        'status_breakdown': _status_breakdown(rows),
        'chat_cases':       chat_cases,
        'total_cases':      len(rows),
        'total_approved':   total_approved,
        'total_received':   total_received,
        'total_remaining':  total_approved - total_received,
    })


def client_portal_case(request, case_id):
    acc = _current_client_access(request)
    if acc is None:
        request.session.pop(CLIENT_SESSION_KEY, None)
        return redirect('login')

    ca = (ClientCaseAccess.objects
          .filter(access=acc, case_id=case_id)
          .select_related('case', 'case__debtor', 'case__currency', 'case__collector')
          .first())
    if ca is None or not ca.any_permission:
        return redirect('client_portal')

    case = ca.case
    ctx = {'access': acc, 'client': acc.client, 'case': case, 'perm': ca,
           'chat_cases': [{'pk': case.pk, 'ref': case.case_id,
                           'debtor': case.debtor.name if case.debtor_id else ''}]}

    if ca.can_followup:
        ctx['followups'] = case.follow_ups.select_related('followed_by').order_by('-follow_up_date')
    if ca.can_history:
        ctx['history'] = case.case_history.select_related('action_by').order_by('-created_at')
    if ca.can_payment_history:
        ctx['payments'] = (case.payments.select_related('payment_mode', 'received_currency')
                           .order_by('-payment_date'))
        ctx['payments_total'] = ctx['payments'].aggregate(t=Sum('amount'))['t'] or 0
    if ca.can_attachments:
        ctx['attachments'] = (case.attachments.select_related('attachment_type')
                              .order_by('-uploaded_at'))
    return render(request, 'client_portal_case.html', ctx)


# ---------- CHAT (client portal ↔ staff dashboard) ----------
def _chat_dict(m):
    return {
        'id': m.id,
        'sender': m.sender,
        'body': m.body,
        'time': timezone.localtime(m.created_at).strftime('%d %b, %I:%M %p'),
        'staff': (m.staff_user.get_full_name() or m.staff_user.username) if m.staff_user else '',
        'read': m.is_read,
        'edited': m.is_edited,
        'auto': m.is_auto,
    }


# Auto-acknowledgement sent to a client on their first message in a conversation.
CHAT_AUTO_REPLY = ("✅ Your message has been received. It will be forwarded to the staff "
                   "handling your case — they'll connect with you as soon as they're available. "
                   "Thank you for your patience.")


# --- Client side (portal, session-authenticated) ---
@require_POST
def client_chat_send(request):
    acc = _current_client_access(request)
    if acc is None:
        return JsonResponse({'success': False, 'message': 'Session expired.'}, status=403)
    case_id = request.POST.get('case_id', '').strip()
    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'success': False, 'message': 'Message is empty.'})
    ca = ClientCaseAccess.objects.filter(access=acc, case_id=case_id).first()
    if ca is None or not ca.any_permission:
        return JsonResponse({'success': False, 'message': 'No access to this case.'}, status=403)
    # First staff/system engagement? If none yet, send an automatic acknowledgement.
    send_ack = not ChatMessage.objects.filter(case_id=case_id, access=acc,
                                              sender=ChatMessage.SENDER_STAFF).exists()
    m = ChatMessage.objects.create(case_id=case_id, access=acc, sender=ChatMessage.SENDER_CLIENT, body=body)
    if send_ack:
        ChatMessage.objects.create(case_id=case_id, access=acc, sender=ChatMessage.SENDER_STAFF,
                                   body=CHAT_AUTO_REPLY, is_auto=True)
    return JsonResponse({'success': True, 'message': _chat_dict(m)})


def client_chat_thread(request):
    acc = _current_client_access(request)
    if acc is None:
        return JsonResponse({'success': False}, status=403)
    case_id = request.GET.get('case_id', '').strip()
    ca = ClientCaseAccess.objects.filter(access=acc, case_id=case_id).select_related('case__collector').first()
    if ca is None:
        return JsonResponse({'success': False}, status=403)
    msgs = ChatMessage.objects.filter(case_id=case_id, access=acc)
    # Client is now viewing → staff messages become read.
    msgs.filter(sender=ChatMessage.SENDER_STAFF, is_read=False).update(is_read=True)
    coll = ca.case.collector
    return JsonResponse({
        'success': True,
        'messages': [_chat_dict(m) for m in msgs],
        'staff_name': (coll.get_full_name() or coll.username) if coll else 'Support Team',
    })


def client_chat_poll(request):
    acc = _current_client_access(request)
    if acc is None:
        return JsonResponse({'success': False}, status=403)
    unread = ChatMessage.objects.filter(access=acc, sender=ChatMessage.SENDER_STAFF, is_read=False)
    per_case = {}
    for cid in unread.values_list('case_id', flat=True):
        per_case[cid] = per_case.get(cid, 0) + 1
    return JsonResponse({'success': True, 'total': sum(per_case.values()), 'per_case': per_case})


@require_POST
def client_chat_edit(request):
    acc = _current_client_access(request)
    if acc is None:
        return JsonResponse({'success': False}, status=403)
    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'success': False, 'message': 'Message is empty.'})
    m = ChatMessage.objects.filter(id=request.POST.get('id'), access=acc,
                                   sender=ChatMessage.SENDER_CLIENT).first()
    if m is None:
        return JsonResponse({'success': False, 'message': 'Not allowed.'}, status=403)
    m.body = body; m.is_edited = True
    m.save(update_fields=['body', 'is_edited'])
    return JsonResponse({'success': True})


@require_POST
def client_chat_delete(request):
    acc = _current_client_access(request)
    if acc is None:
        return JsonResponse({'success': False}, status=403)
    m = ChatMessage.objects.filter(id=request.POST.get('id'), access=acc,
                                   sender=ChatMessage.SENDER_CLIENT).first()
    if m is None:
        return JsonResponse({'success': False, 'message': 'Not allowed.'}, status=403)
    m.delete()
    return JsonResponse({'success': True})


# --- Staff side (dashboard, login-required) ---
def _staff_can_case(user, case):
    return user.is_superuser or case.collector_id == user.id


@login_required
def staff_chat_conversations(request):
    qs = (ChatMessage.objects
          .select_related('case', 'case__debtor', 'access', 'access__client', 'staff_user'))
    if not request.user.is_superuser:
        qs = qs.filter(case__collector=request.user)
    convos = {}
    for m in qs.order_by('-created_at'):
        if m.is_auto:
            continue  # auto-replies are client-side only; don't surface them to staff
        key = (m.case_id, m.access_id)
        c = convos.get(key)
        if c is None:
            c = convos[key] = {
                'case_pk': m.case_id,
                'case_ref': m.case.case_id,
                'access_id': m.access_id,
                'client_name': m.access.client.name,
                'client_email': m.access.email,
                'debtor': m.case.debtor.name if m.case.debtor_id else '',
                'last_body': (('You: ' if m.sender == ChatMessage.SENDER_STAFF and not m.is_auto else '') + m.body)[:70],
                'last_time': timezone.localtime(m.created_at).strftime('%d %b, %I:%M %p'),
                'unread': 0,
            }
        if m.sender == ChatMessage.SENDER_CLIENT and not m.is_read:
            c['unread'] += 1
    convos = sorted(convos.values(), key=lambda x: x['unread'], reverse=True)
    return JsonResponse({'success': True, 'conversations': convos})


@login_required
def staff_chat_thread(request):
    case_pk = request.GET.get('case_id', '').strip()
    access_id = request.GET.get('access_id', '').strip()
    case = get_object_or_404(Case, pk=case_pk)
    if not _staff_can_case(request.user, case):
        return JsonResponse({'success': False}, status=403)
    ChatMessage.objects.filter(case_id=case_pk, access_id=access_id,
                               sender=ChatMessage.SENDER_CLIENT, is_read=False).update(is_read=True)
    # Auto-acknowledgements are for the client only — hide them from staff.
    msgs = ChatMessage.objects.filter(case_id=case_pk, access_id=access_id).exclude(is_auto=True)
    return JsonResponse({'success': True, 'messages': [_chat_dict(m) for m in msgs]})


@login_required
@require_POST
def staff_chat_send(request):
    case_pk = request.POST.get('case_id', '').strip()
    access_id = request.POST.get('access_id', '').strip()
    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'success': False, 'message': 'Message is empty.'})
    case = get_object_or_404(Case, pk=case_pk)
    if not _staff_can_case(request.user, case):
        return JsonResponse({'success': False, 'message': 'Not your case.'}, status=403)
    m = ChatMessage.objects.create(
        case_id=case_pk, access_id=access_id, sender=ChatMessage.SENDER_STAFF,
        staff_user=request.user, body=body,
    )
    return JsonResponse({'success': True, 'message': _chat_dict(m)})


@login_required
def staff_chat_poll(request):
    qs = ChatMessage.objects.filter(sender=ChatMessage.SENDER_CLIENT, is_read=False)
    if not request.user.is_superuser:
        qs = qs.filter(case__collector=request.user)
    return JsonResponse({'success': True, 'total': qs.count()})


def _staff_own_msg(request, msg_id):
    """A staff message the current user may edit/delete (their own, or any for admins)."""
    m = ChatMessage.objects.filter(id=msg_id, sender=ChatMessage.SENDER_STAFF).first()
    if m is None:
        return None
    if request.user.is_superuser or m.staff_user_id == request.user.id:
        return m
    return None


@login_required
@require_POST
def staff_chat_edit(request):
    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'success': False, 'message': 'Message is empty.'})
    m = _staff_own_msg(request, request.POST.get('id'))
    if m is None:
        return JsonResponse({'success': False, 'message': 'Not allowed.'}, status=403)
    m.body = body; m.is_edited = True
    m.save(update_fields=['body', 'is_edited'])
    return JsonResponse({'success': True})


@login_required
@require_POST
def staff_chat_delete(request):
    m = _staff_own_msg(request, request.POST.get('id'))
    if m is None:
        return JsonResponse({'success': False, 'message': 'Not allowed.'}, status=403)
    m.delete()
    return JsonResponse({'success': True})


def client_portal_logout(request):
    request.session.pop(CLIENT_SESSION_KEY, None)
    return redirect('login')


@login_required
def profile_edit(request):
    user = request.user
    success = False
    error = None
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        email      = request.POST.get('email', '').strip()
        new_pass   = request.POST.get('new_password', '').strip()
        confirm    = request.POST.get('confirm_password', '').strip()

        user.first_name = first_name
        user.last_name  = last_name
        user.email      = email

        if new_pass:
            if new_pass != confirm:
                error = 'Passwords do not match.'
            elif len(new_pass) < 6:
                error = 'Password must be at least 6 characters.'
            else:
                user.set_password(new_pass)
                user.save()
                # re-login to avoid session invalidation
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, user)
                success = True
        if not error:
            user.save()
            success = True

    return render(request, 'profile_edit.html', {
        'active_page': 'profile',
        'success': success,
        'error': error,
    })


def debtor_statuses_list(request):
    return render(request, 'settings_debtor_statuses.html', {
        'active_page': 'settings',
        'active_sub': 'settings_debtor_statuses',
        'debtor_statuses': DebtorStatusOption.objects.all(),
        'type_choices': DebtorStatusOption.TYPE_CHOICES,
    })


def _split_valid_debtor_types(raw):
    """Parse an 'individual,organization'-style POST value into the subset
    that are real DebtorStatusOption.TYPE_CHOICES keys, in order, de-duplicated."""
    valid = dict(DebtorStatusOption.TYPE_CHOICES)
    seen, out = set(), []
    for t in raw.split(','):
        t = t.strip()
        if t in valid and t not in seen:
            seen.add(t)
            out.append(t)
    return out


@require_POST
def debtor_status_create(request):
    name = request.POST.get('name', '').strip()
    types = _split_valid_debtor_types(request.POST.get('types', request.POST.get('debtor_type', 'individual')))
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if not types:
        return JsonResponse({'ok': False, 'error': 'Select at least one type (Individual and/or Organization).'})
    created = []
    for t in types:
        if DebtorStatusOption.objects.filter(name__iexact=name, debtor_type=t).exists():
            continue
        created.append(DebtorStatusOption.objects.create(name=name, debtor_type=t))
    if not created:
        return JsonResponse({'ok': False, 'error': 'That name already exists for the selected type(s).'})
    return JsonResponse({'ok': True, 'id': created[0].pk, 'name': created[0].name,
                         'created': len(created)})


@require_POST
def debtor_status_update(request):
    obj = get_object_or_404(DebtorStatusOption, pk=request.POST.get('id'))
    name = request.POST.get('name', '').strip()
    types = _split_valid_debtor_types(request.POST.get('types', request.POST.get('debtor_type', 'individual')))
    if not name:
        return JsonResponse({'ok': False, 'error': 'Name is required.'})
    if not types:
        return JsonResponse({'ok': False, 'error': 'Select at least one type (Individual and/or Organization).'})
    # This row becomes the first checked type; any other checked type gets
    # its own row if one doesn't already exist for this name.
    primary, extra = types[0], types[1:]
    if DebtorStatusOption.objects.filter(name__iexact=name, debtor_type=primary).exclude(pk=obj.pk).exists():
        return JsonResponse({'ok': False, 'error': 'Another status already has that name for this type.'})
    obj.name = name
    obj.debtor_type = primary
    obj.save()
    for t in extra:
        if not DebtorStatusOption.objects.filter(name__iexact=name, debtor_type=t).exists():
            DebtorStatusOption.objects.create(name=name, debtor_type=t)
    return JsonResponse({'ok': True, 'id': obj.pk, 'name': obj.name, 'debtor_type': obj.get_debtor_type_display()})


@require_POST
def debtor_status_toggle(request):
    obj = get_object_or_404(DebtorStatusOption, pk=request.POST.get('id'))
    obj.is_enabled = not obj.is_enabled
    obj.save()
    return JsonResponse({'ok': True, 'enabled': obj.is_enabled})


@require_POST
def debtor_status_delete(request):
    ids = request.POST.getlist('ids[]') or [request.POST.get('id')]
    DebtorStatusOption.objects.filter(pk__in=ids).delete()
    return JsonResponse({'ok': True})
