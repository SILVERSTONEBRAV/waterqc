import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qad.settings")
import django
django.setup()

from django.db import connection

sql_fix = """
PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

CREATE TABLE "ca_batchtestresult_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "value" real NULL,
    "textual_result" varchar(100) NOT NULL,
    "status" varchar(10) NOT NULL,
    "tested_at" datetime NOT NULL,
    "auto_remark" text NOT NULL,
    "analyst_id" bigint NULL REFERENCES "accounts_customuser" ("id") DEFERRABLE INITIALLY DEFERRED,
    "batch_id" bigint NOT NULL REFERENCES "ca_chemicalbatch" ("id") DEFERRABLE INITIALLY DEFERRED,
    "parameter_id" bigint NULL REFERENCES "ca_chemicalspecification" ("id") DEFERRABLE INITIALLY DEFERRED
);

INSERT INTO "ca_batchtestresult_new" SELECT * FROM "ca_batchtestresult";

DROP TABLE "ca_batchtestresult";

ALTER TABLE "ca_batchtestresult_new" RENAME TO "ca_batchtestresult";

CREATE INDEX "ca_batchtestresult_parameter_id_43fb0a27" ON "ca_batchtestresult" ("parameter_id");
CREATE INDEX "ca_batchtestresult_batch_id_0355a8ff" ON "ca_batchtestresult" ("batch_id");
CREATE INDEX "ca_result_batch_status_idx" ON "ca_batchtestresult" ("batch_id", "status");
CREATE INDEX "ca_result_analyst_tested_idx" ON "ca_batchtestresult" ("analyst_id", "tested_at");
CREATE UNIQUE INDEX "ca_unique_batch_parameter_result" ON "ca_batchtestresult" ("batch_id", "parameter_id");

COMMIT;

PRAGMA foreign_keys = ON;
"""

cursor = connection.cursor()
cursor.executescript(sql_fix)
print("Table ca_batchtestresult successfully updated without UNIQUE on analyst_id.")
