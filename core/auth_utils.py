from functools import wraps

from django.conf import settings
from django.http import HttpResponseForbidden


EDITOR_SESSION_KEY = "editor_access_granted"


def request_can_edit(request):
    return bool(request.session.get(EDITOR_SESSION_KEY))


def editor_required(view_func):
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not request_can_edit(request):
            return HttpResponseForbidden("Read-only access is open. Editor changes require the admin password.")
        return view_func(request, *args, **kwargs)

    return wrapped_view


def password_matches(value):
    return value == settings.EDITOR_ACCESS_PASSWORD
