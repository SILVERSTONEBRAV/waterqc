# ca/middleware.py
import threading

_user = threading.local()

def get_current_user():
    return getattr(_user, "value", None)

class CurrentUserMiddleware:
    """
    Middleware that stores the authenticated user for auditing signals.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _user.value = getattr(request, "user", None)
        try:
            response = self.get_response(request)
        finally:
            _user.value = None
        return response
