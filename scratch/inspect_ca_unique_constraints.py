import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qad.settings")
import django
django.setup()

from django.db import connection

cursor = connection.cursor()
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE 'ca_%';")
tables = cursor.fetchall()

print("Checking UNIQUE constraints across ca_* tables:")
for name, sql in tables:
    if not sql:
        continue
    # Check for UNIQUE in column definitions
    lines = sql.split("\n")
    unique_lines = [l.strip() for l in lines if "UNIQUE" in l.upper()]
    if unique_lines:
        print(f"\nTable: {name}")
        for l in unique_lines:
            print("  ", l)
