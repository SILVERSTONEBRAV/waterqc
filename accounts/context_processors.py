# accounts/context_processors.py

from accounts.utils import get_user_landing_url

def navigation_context(request):

    if not request.user.is_authenticated:
        return {}

    return {
        "user_home_url": get_user_landing_url(
            request.user
        )
    }