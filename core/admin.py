from django.contrib import admin
from .models import Client, ClientContact, Debtor, Case


class ClientContactInline(admin.TabularInline):
    model = ClientContact
    extra = 1


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'name', 'client_type', 'country', 'status', 'created_at')
    list_filter = ('client_type', 'country', 'status')
    search_fields = ('name', 'email', 'client_id')
    inlines = [ClientContactInline]
    readonly_fields = ('client_id',)


@admin.register(ClientContact)
class ClientContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_type', 'client', 'email', 'phone', 'enabled')
    list_filter = ('contact_type', 'enabled')
    search_fields = ('name', 'email', 'client__name')


@admin.register(Debtor)
class DebtorAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'created_at')
    search_fields = ('name', 'email')


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('client', 'debtor', 'approved_amount', 'received_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('client__name', 'debtor__name')