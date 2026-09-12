from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Attendance / idle auto-logout
    path('attendance/heartbeat/', views.attendance_heartbeat, name='attendance_heartbeat'),
    path('settings/attendance/', views.attendance_report, name='attendance_report'),

    # Client OTP login + portal
    path('client-login/request-otp/', views.client_otp_request, name='client_otp_request'),
    path('client-login/verify-otp/', views.client_otp_verify, name='client_otp_verify'),
    path('portal/', views.client_portal, name='client_portal'),
    path('portal/case/<int:case_id>/', views.client_portal_case, name='client_portal_case'),
    path('portal/logout/', views.client_portal_logout, name='client_portal_logout'),

    # Chat (client portal ↔ staff dashboard)
    path('portal/chat/send/', views.client_chat_send, name='client_chat_send'),
    path('portal/chat/thread/', views.client_chat_thread, name='client_chat_thread'),
    path('portal/chat/poll/', views.client_chat_poll, name='client_chat_poll'),
    path('portal/chat/edit/', views.client_chat_edit, name='client_chat_edit'),
    path('portal/chat/delete/', views.client_chat_delete, name='client_chat_delete'),
    path('chat/conversations/', views.staff_chat_conversations, name='staff_chat_conversations'),
    path('chat/thread/', views.staff_chat_thread, name='staff_chat_thread'),
    path('chat/send/', views.staff_chat_send, name='staff_chat_send'),
    path('chat/poll/', views.staff_chat_poll, name='staff_chat_poll'),
    path('chat/edit/', views.staff_chat_edit, name='staff_chat_edit'),
    path('chat/delete/', views.staff_chat_delete, name='staff_chat_delete'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),

    # Clients
    path('clients/', views.clients, name='clients'),
    path('clients/add/', views.client_add, name='client_add'),
    path('clients/create/', views.client_create_modal, name='client_create_modal'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/json/', views.client_detail_json, name='client_detail_json'),
    path('clients/<int:pk>/update-ajax/', views.client_update_ajax, name='client_update_ajax'),
    path('clients/delete/', views.client_delete, name='client_delete'),
    path('clients/toggle-status/', views.client_toggle_status, name='client_toggle_status'),
    path('clients/merge/', views.client_merge, name='client_merge'),
    path('clients/export/<str:format>/', views.client_export, name='client_export'),

    # Client Contacts
    path('clients/contacts/', views.client_contacts, name='client_contacts'),
    path('clients/contacts/add/', views.contact_add, name='contact_add'),
    path('clients/contacts/create/', views.contact_create_modal, name='contact_create_modal'),
    path('clients/contacts/<int:pk>/edit/', views.contact_edit, name='contact_edit'),
    path('clients/contacts/delete/', views.contact_delete, name='contact_delete'),
    path('clients/contacts/export/<str:format>/', views.contact_export, name='contact_export'),

    # Debtors & Cases
    path('debtors/', views.debtors, name='debtors'),
    path('debtors/<int:pk>/', views.debtor_detail, name='debtor_detail'),
    path('debtors/<int:pk>/update/', views.debtor_update, name='debtor_update'),
    path('debtors/<int:pk>/json/', views.debtor_detail_json, name='debtor_detail_json'),
    path('debtors/create/', views.debtor_create_modal, name='debtor_create_modal'),
    path('debtors/name-suggest/', views.debtor_name_suggest, name='debtor_name_suggest'),
    path('debtors/delete/', views.debtor_delete, name='debtor_delete'),
    path('debtors/merge/compare/', views.debtor_merge_compare, name='debtor_merge_compare'),
    path('debtors/merge/', views.debtor_merge, name='debtor_merge'),
    path('debtors/export/<str:format>/', views.debtor_export, name='debtor_export'),
    path('debtors/contacts/', views.debtor_contacts, name='debtor_contacts'),
    path('debtors/contacts/create/', views.debtor_contact_create, name='debtor_contact_create'),
    path('debtors/contacts/delete/', views.debtor_contact_delete, name='debtor_contact_delete'),
    path('debtors/contacts/export/<str:format>/', views.debtor_contact_export, name='debtor_contact_export'),
    path('debtors/duplicates/', views.debtor_duplicates, name='debtor_duplicates'),
    path('debtors/duplicates/merge/', views.debtor_duplicates_merge, name='debtor_duplicates_merge'),
    path('cases/<int:pk>/', views.case_detail, name='case_detail'),
    path('cases/<int:pk>/update/', views.case_detail_update, name='case_detail_update'),
    path('cases/<int:pk>/change-status/', views.case_change_status, name='case_change_status'),
    path('cases/<int:pk>/change-collector/', views.case_change_collector, name='case_change_collector'),
    path('cases/<int:pk>/legal-status/', views.case_change_legal_status, name='case_change_legal_status'),
    path('cases/<int:pk>/legal-info/update/', views.case_legal_info_update, name='case_legal_info_update'),
    path('cases/<int:pk>/legal-fees/add/', views.legal_fee_add, name='legal_fee_add'),
    path('legal-fees/delete/', views.legal_fee_delete, name='legal_fee_delete'),
    path('cases/<int:pk>/financials/update/', views.case_financials_update, name='case_financials_update'),
    path('cases/', views.cases, name='cases'),
    path('cases/create/', views.case_create_modal, name='case_create_modal'),
    path('cases/delete/', views.case_delete, name='case_delete'),
    path('cases/bulk-change-status/', views.case_bulk_change_status, name='case_bulk_change_status'),
    path('cases/bulk-change-collector/', views.case_bulk_change_collector, name='case_bulk_change_collector'),
    path('cases/bulk-add-user/', views.case_bulk_add_user, name='case_bulk_add_user'),
    path('cases/bulk-remove-user/', views.case_bulk_remove_user, name='case_bulk_remove_user'),
    path('cases/bulk-group/', views.case_bulk_group, name='case_bulk_group'),
    path('cases/export/<str:format>/', views.case_export, name='case_export'),
    path('cases/follow-ups/', views.follow_ups, name='follow_ups'),
    path('cases/follow-ups/create/', views.follow_up_create, name='follow_up_create'),
    path('cases/follow-ups/export/<str:format>/', views.follow_up_export, name='follow_up_export'),
    path('cases/follow-ups/merge/', views.follow_ups_merge, name='follow_ups_merge'),
    path('cases/bulk-follow-ups/', views.bulk_follow_ups, name='bulk_follow_ups'),
    path('cases/case-groups/', views.case_groups, name='case_groups'),
    path('cases/case-groups/<int:pk>/', views.case_group_detail, name='case_group_detail'),
    path('cases/case-groups/create/', views.case_group_create, name='case_group_create'),
    path('cases/case-groups/payment/', views.group_payment_create, name='group_payment_create'),
    path('cases/case-groups/remove-case/', views.case_group_remove_case, name='case_group_remove_case'),
    path('cases/case-groups/add-case/', views.case_group_add_case, name='case_group_add_case'),
    path('cases/pending-payments/', views.pending_payments, name='pending_payments'),

    # Legal Cases
    path('legal-cases/', views.legal_cases, name='legal_cases'),
    path('legal-cases/create/', views.legal_case_create, name='legal_case_create'),
    path('legal-cases/update/', views.legal_case_update, name='legal_case_update'),
    path('legal-cases/delete/', views.legal_case_delete, name='legal_case_delete'),

    # Payments
    path('payments/', views.payments, name='payments'),
    path('payments/create/', views.payment_create_modal, name='payment_create_modal'),
    path('payments/update/', views.payment_update, name='payment_update'),
    path('payments/<int:pk>/receipt/', views.payment_receipt, name='payment_receipt'),
    path('receipt/verify/', views.receipt_verify_lookup, name='receipt_verify_lookup'),
    path('receipt/verify/<int:pk>/<str:token>/', views.receipt_verify, name='receipt_verify'),
    path('payments/installments/bulk-create/', views.installment_bulk_create, name='installment_bulk_create'),
    path('payments/installments/update/', views.installment_update, name='installment_update'),
    path('payments/delete/', views.payment_delete, name='payment_delete'),
    path('payments/confirm/', views.payment_confirm, name='payment_confirm'),
    path('payments/export/<str:format>/', views.payment_export, name='payment_export'),

    # Reports
    path('reports/cases/', views.case_status_report, name='case_status_report'),
    path('reports/collector/', views.collector_report, name='collector_report'),

    # Settings – Users
    path('settings/users/', views.users_list, name='users_list'),
    path('settings/users/create/', views.user_create, name='user_create'),
    path('settings/users/update/', views.user_update, name='user_update'),
    path('settings/users/toggle/', views.user_toggle, name='user_toggle'),
    path('settings/users/delete/', views.user_delete, name='user_delete'),
    path('settings/users/set-allowed-ips/', views.user_set_allowed_ips, name='user_set_allowed_ips'),

    # Settings – User Groups
    path('settings/user-groups/', views.user_groups_list, name='user_groups_list'),
    path('settings/user-groups/create/', views.user_group_create, name='user_group_create'),
    path('settings/user-groups/update/', views.user_group_update, name='user_group_update'),
    path('settings/users/permissions/', views.user_permissions_get, name='user_permissions_get'),
    path('settings/users/permissions/set/', views.user_permissions_set, name='user_permissions_set'),
    path('settings/user-groups/toggle/', views.user_group_toggle, name='user_group_toggle'),
    path('settings/user-groups/delete/', views.user_group_delete, name='user_group_delete'),

    # Settings – Localisation: Countries
    path('settings/localisation/countries/', views.countries_list, name='countries_list'),
    path('settings/localisation/countries/create/', views.country_create, name='country_create'),
    path('settings/localisation/countries/update/', views.country_update, name='country_update'),
    path('settings/localisation/countries/toggle/', views.country_toggle, name='country_toggle'),
    path('settings/localisation/countries/delete/', views.country_delete, name='country_delete'),

    # Settings – Localisation: States
    path('settings/localisation/states/', views.states_list, name='states_list'),
    path('settings/localisation/states/create/', views.state_create, name='state_create'),
    path('settings/localisation/states/update/', views.state_update, name='state_update'),
    path('settings/localisation/states/toggle/', views.state_toggle, name='state_toggle'),
    path('settings/localisation/states/delete/', views.state_delete, name='state_delete'),

    # Settings – Localisation: Currencies
    path('settings/localisation/currencies/', views.currencies_list, name='currencies_list'),
    path('settings/localisation/currencies/create/', views.currency_create, name='currency_create'),
    path('settings/localisation/currencies/update/', views.currency_update, name='currency_update'),
    path('settings/localisation/currencies/toggle/', views.currency_toggle, name='currency_toggle'),
    path('settings/localisation/currencies/delete/', views.currency_delete, name='currency_delete'),

    # Settings – Case
    path('settings/case/case-types/', views.case_types_list, name='case_types_list'),
    path('settings/case/case-types/create/', views.case_type_create, name='case_type_create'),
    path('settings/case/case-types/toggle/', views.case_type_toggle, name='case_type_toggle'),
    path('settings/case/case-types/delete/', views.case_type_delete, name='case_type_delete'),

    # Settings – Case Status
    path('settings/case/case-status/', views.case_status_list, name='case_status_list'),
    path('settings/case/case-status/create/', views.case_status_create, name='case_status_create'),
    path('settings/case/case-status/toggle/', views.case_status_toggle, name='case_status_toggle'),
    path('settings/case/case-status/delete/', views.case_status_delete, name='case_status_delete'),

    # Settings – Legal Case Status
    path('settings/case/legal-case-status/', views.legal_case_status_list, name='legal_case_status_list'),
    path('settings/case/legal-case-status/create/', views.legal_case_status_create, name='legal_case_status_create'),
    path('settings/case/legal-case-status/update/', views.legal_case_status_update, name='legal_case_status_update'),
    path('settings/case/legal-case-status/toggle/', views.legal_case_status_toggle, name='legal_case_status_toggle'),
    path('settings/case/legal-case-status/delete/', views.legal_case_status_delete, name='legal_case_status_delete'),

    # Settings – Legal Fee Types
    path('settings/case/legal-fee-types/', views.legal_fee_types_list, name='legal_fee_types_list'),
    path('settings/case/legal-fee-types/create/', views.legal_fee_type_create, name='legal_fee_type_create'),
    path('settings/case/legal-fee-types/toggle/', views.legal_fee_type_toggle, name='legal_fee_type_toggle'),
    path('settings/case/legal-fee-types/delete/', views.legal_fee_type_delete, name='legal_fee_type_delete'),

    # Settings – Followup Types
    path('settings/case/followup-types/', views.followup_types_list, name='followup_types_list'),
    path('settings/case/followup-types/create/', views.followup_type_create, name='followup_type_create'),
    path('settings/case/followup-types/toggle/', views.followup_type_toggle, name='followup_type_toggle'),
    path('settings/case/followup-types/delete/', views.followup_type_delete, name='followup_type_delete'),

    # Settings – Payment Modes
    path('settings/payment-modes/', views.payment_modes_list, name='payment_modes_list'),
    path('settings/payment-modes/create/', views.payment_mode_create, name='payment_mode_create'),
    path('settings/payment-modes/update/', views.payment_mode_update, name='payment_mode_update'),
    path('settings/payment-modes/toggle/', views.payment_mode_toggle, name='payment_mode_toggle'),
    path('settings/payment-modes/delete/', views.payment_mode_delete, name='payment_mode_delete'),

    # Settings – Client Types
    path('settings/client-types/', views.client_types_list, name='client_types_list'),
    path('settings/client-types/create/', views.client_type_create, name='client_type_create'),
    path('settings/client-types/update/', views.client_type_update, name='client_type_update'),
    path('settings/client-types/toggle/', views.client_type_toggle, name='client_type_toggle'),
    path('settings/client-types/delete/', views.client_type_delete, name='client_type_delete'),

    # Settings – Contract Types
    path('settings/contract-types/', views.contract_types_list, name='contract_types_list'),
    path('settings/contract-types/create/', views.contract_type_create, name='contract_type_create'),
    path('settings/contract-types/update/', views.contract_type_update, name='contract_type_update'),
    path('settings/contract-types/toggle/', views.contract_type_toggle, name='contract_type_toggle'),
    path('settings/contract-types/delete/', views.contract_type_delete, name='contract_type_delete'),

    # Settings – Contact Types
    path('settings/contact-types/', views.contact_types_list, name='contact_types_list'),
    path('settings/contact-types/create/', views.contact_type_create, name='contact_type_create'),
    path('settings/contact-types/update/', views.contact_type_update, name='contact_type_update'),
    path('settings/contact-types/toggle/', views.contact_type_toggle, name='contact_type_toggle'),
    path('settings/contact-types/delete/', views.contact_type_delete, name='contact_type_delete'),

    path('settings/debtor-statuses/', views.debtor_statuses_list, name='debtor_statuses_list'),
    path('settings/debtor-statuses/create/', views.debtor_status_create, name='debtor_status_create'),
    path('settings/debtor-statuses/update/', views.debtor_status_update, name='debtor_status_update'),
    path('settings/debtor-statuses/toggle/', views.debtor_status_toggle, name='debtor_status_toggle'),
    path('settings/debtor-statuses/delete/', views.debtor_status_delete, name='debtor_status_delete'),

    # Settings – Attachment Types
    path('settings/attachment-types/', views.attachment_types_list, name='attachment_types_list'),
    path('settings/attachment-types/create/', views.attachment_type_create, name='attachment_type_create'),
    path('settings/attachment-types/update/', views.attachment_type_update, name='attachment_type_update'),
    path('settings/attachment-types/toggle/', views.attachment_type_toggle, name='attachment_type_toggle'),
    path('settings/attachment-types/delete/', views.attachment_type_delete, name='attachment_type_delete'),

    # Settings – Agencies
    path('settings/agencies/', views.agencies_list, name='agencies_list'),
    path('settings/agencies/create/', views.agency_create, name='agency_create'),
    path('settings/agencies/update/', views.agency_update, name='agency_update'),
    path('settings/agencies/toggle/', views.agency_toggle, name='agency_toggle'),
    path('settings/agencies/delete/', views.agency_delete, name='agency_delete'),
    path('settings/agencies/export/<str:format>/', views.agency_export, name='agency_export'),

    # Settings – Lawyers
    path('settings/lawyers/', views.lawyers_list, name='lawyers_list'),
    path('settings/lawyers/create/', views.lawyer_create, name='lawyer_create'),
    path('settings/lawyers/update/', views.lawyer_update, name='lawyer_update'),
    path('settings/lawyers/toggle/', views.lawyer_toggle, name='lawyer_toggle'),
    path('settings/lawyers/delete/', views.lawyer_delete, name='lawyer_delete'),
    path('settings/lawyers/export/<str:format>/', views.lawyer_export, name='lawyer_export'),

    # Settings – Contact Directory
    path('settings/contact-directory/', views.contact_directory, name='contact_directory'),
    path('settings/contact-directory/update/', views.contact_directory_update, name='contact_directory_update'),
    path('settings/contact-directory/delete/', views.contact_directory_delete, name='contact_directory_delete'),
    path('settings/contact-directory/export/<str:format>/', views.contact_directory_export, name='contact_directory_export'),

    # Settings – Import
    path('settings/import/', views.import_view, name='import_view'),
    path('settings/import-new/', views.import_new_view, name='import_new_view'),
    path('settings/import-new/sample/', views.import_case_sample, name='import_case_sample'),

    # Reports – Receipt
    path('reports/receipt/', views.receipt_report, name='receipt_report'),

    # Activity Logs
    path('settings/activity/', views.activity_logs, name='activity_logs'),

    # Reports – New/Additional Allocation
    path('reports/new-allocation/', views.new_allocation_report, name='new_allocation_report'),

    # Reports – Commission
    path('reports/commission/', views.commission_report, name='commission_report'),

    # Reports – Collections
    path('reports/collection/', views.collection_report, name='collection_report'),

    # Reports – Agency
    path('reports/agency/', views.agency_report, name='agency_report'),

    # Reports – Client
    path('reports/client/', views.client_report, name='client_report'),

    # Reports – Debtor
    path('reports/debtor/', views.debtor_report, name='debtor_report'),

    # Settings – Client Login Access
    path('settings/client-access/', views.client_login_access_list, name='client_login_access_list'),
    path('settings/client-access/create/', views.client_login_access_create, name='client_login_access_create'),
    path('settings/client-access/update/', views.client_login_access_update, name='client_login_access_update'),
    path('settings/client-access/<int:pk>/edit/', views.client_login_access_edit, name='client_login_access_edit'),
    path('settings/client-access/<int:pk>/logs/', views.client_login_access_logs, name='client_login_access_logs'),
    path('settings/client-access/toggle/', views.client_login_access_toggle, name='client_login_access_toggle'),
    path('settings/client-access/delete/', views.client_login_access_delete, name='client_login_access_delete'),

    # Currency converter
    path('currency/convert/', views.currency_convert, name='currency_convert'),

    # Todos
    path('todos/', views.todo_list_view, name='todo_list'),
    path('todos/delete/', views.todo_delete, name='todo_delete'),

    # Reminders
    path('reminders/today/', views.reminders_today, name='reminders_today'),
    path('reminders/tomorrow/', views.reminders_tomorrow, name='reminders_tomorrow'),
    path('reminders/pending/', views.reminders_pending, name='reminders_pending'),
    path('reminders/payments/', views.reminders_payments, name='reminders_payments'),
    path('reminders/complete/', views.reminder_complete, name='reminder_complete'),
    path('reminders/payment-complete/', views.reminder_payment_complete, name='reminder_payment_complete'),
    path('reminders/promise-complete/', views.reminder_promise_complete, name='reminder_promise_complete'),
    path('reminders/create/', views.reminder_create, name='reminder_create'),

    # Case Attachments
    path('cases/attachments/upload/', views.case_attachment_upload, name='case_attachment_upload'),
    path('cases/attachments/delete/', views.case_attachment_delete, name='case_attachment_delete'),
]