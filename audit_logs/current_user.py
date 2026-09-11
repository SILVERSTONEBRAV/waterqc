# audit_logs/current_user.py

from threading import local

_thread_locals = local()


def set_current_user(user):
    _thread_locals.user = user


def get_current_user():
    return getattr(_thread_locals, "user", None)


def clear_current_user():
    if hasattr(_thread_locals, "user"):
        del _thread_locals.user