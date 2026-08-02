from django.conf import settings

from .currencies import enabled_currencies


def idle_settings(request):
    """Expose the idle auto-logout configuration to every template so the
    global idle-timer script in base.html can read the limits."""
    return {
        'IDLE_LOGOUT_MINUTES': getattr(settings, 'IDLE_LOGOUT_MINUTES', 20),
        'IDLE_WARNING_SECONDS': getattr(settings, 'IDLE_WARNING_SECONDS', 60),
    }


def converter_currencies(request):
    """Currencies for the topbar converter modal in base.html, limited to
    the currencies of the countries enabled in Settings -> Countries."""
    if not request.user.is_authenticated:
        return {'converter_currencies': []}
    return {'converter_currencies': enabled_currencies()}
