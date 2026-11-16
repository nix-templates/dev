import sys

from django.conf import settings

settings.configure(
    SECRET_KEY="fixture",
    INSTALLED_APPS=[],
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
)
from django.core.management import execute_from_command_line

execute_from_command_line(sys.argv)
