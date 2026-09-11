# t/apps.py
from django.apps import AppConfig
import importlib
import logging

logger = logging.getLogger(__name__)


class TConfig(AppConfig):
    name = "t"
