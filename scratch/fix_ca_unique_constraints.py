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

-- 1. Fix ca_checklistforwatertreatmentchemicalanalysis
CREATE TABLE "ca_checklist_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "manufacturer_name_indicated" bool NOT NULL,
    "chemical_name_on_label" bool NOT NULL,
    "min_mass_indicated" bool NOT NULL,
    "grade" varchar(20) NOT NULL,
    "manufacture_date" date NOT NULL,
    "expiry_date" date NOT NULL,
    "storage_conditions" varchar(255) NOT NULL,
    "net_weight" real NOT NULL,
    "country_of_origin" varchar(2) NOT NULL,
    "handling_instructions" text NOT NULL,
    "is_oxidizing" bool NOT NULL,
    "is_corrosive" bool NOT NULL,
    "may_cause_fire" bool NOT NULL,
    "contact_with_acids_liberates_toxic_gas" bool NOT NULL,
    "causes_burns" bool NOT NULL,
    "keep_out_of_reach_of_children" bool NOT NULL,
    "contact_with_eyes_action" bool NOT NULL,
    "fire_action_requires_respiratory_equipment" bool NOT NULL,
    "created_at" datetime NOT NULL,
    "completed" bool NOT NULL,
    "requested_by_id" bigint NULL REFERENCES "accounts_customuser" ("id") DEFERRABLE INITIALLY DEFERRED,
    "sampled_by_id" bigint NULL REFERENCES "accounts_customuser" ("id") DEFERRABLE INITIALLY DEFERRED,
    "chemical_id" bigint NOT NULL REFERENCES "ca_chemical" ("id") DEFERRABLE INITIALLY DEFERRED,
    "chemical_analysis_request_id" bigint NOT NULL REFERENCES "ca_chemicalanalysisrequest" ("id") DEFERRABLE INITIALLY DEFERRED,
    updated_at DATETIME NULL,
    completed_at DATETIME NULL,
    completed_by_id TEXT NULL
);

INSERT INTO "ca_checklist_new" SELECT * FROM "ca_checklistforwatertreatmentchemicalanalysis";
DROP TABLE "ca_checklistforwatertreatmentchemicalanalysis";
ALTER TABLE "ca_checklist_new" RENAME TO "ca_checklistforwatertreatmentchemicalanalysis";

CREATE INDEX "ca_checklist_chem_req_idx" ON "ca_checklistforwatertreatmentchemicalanalysis" ("chemical_analysis_request_id");
CREATE INDEX "ca_checklist_chem_idx" ON "ca_checklistforwatertreatmentchemicalanalysis" ("chemical_id");

-- 2. Fix ca_chemicalcoa
CREATE TABLE "ca_chemicalcoa_new" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "title" varchar(255) NOT NULL,
    "coa_header" text NOT NULL,
    "coa_footer" text NOT NULL,
    "footer_image" varchar(100) NULL,
    "watermark" varchar(100) NULL,
    "qr_code" varchar(100) NULL,
    "pdf_file" varchar(100) NULL,
    "chemical_name" varchar(255) NOT NULL,
    "supplier_name" varchar(255) NOT NULL,
    "quantity" real NOT NULL,
    "delivered_to" varchar(255) NOT NULL,
    "delivery_date" date NOT NULL,
    "delivery_note_number" varchar(100) NOT NULL,
    "sampling_date" date NOT NULL,
    "analysis_date" date NOT NULL,
    "results_summary" text NOT NULL,
    "remarks" text NOT NULL,
    "approved_on" datetime NULL,
    "date_of_report" datetime NOT NULL,
    "verified_hash" varchar(64) NOT NULL,
    "approved_by_id" bigint NULL REFERENCES "accounts_customuser" ("id") DEFERRABLE INITIALLY DEFERRED,
    "batch_id" bigint NOT NULL UNIQUE REFERENCES "ca_chemicalbatch" ("id") DEFERRABLE INITIALLY DEFERRED,
    "packaging_status_id" bigint NULL REFERENCES "ca_packagingstatus" ("id") DEFERRABLE INITIALLY DEFERRED,
    updated_at DATETIME NULL
);

INSERT INTO "ca_chemicalcoa_new" SELECT * FROM "ca_chemicalcoa";
DROP TABLE "ca_chemicalcoa";
ALTER TABLE "ca_chemicalcoa_new" RENAME TO "ca_chemicalcoa";

CREATE INDEX "ca_chemicalcoa_pkg_idx" ON "ca_chemicalcoa" ("packaging_status_id");

COMMIT;

PRAGMA foreign_keys = ON;
"""

cursor = connection.cursor()
cursor.executescript(sql_fix)
print("Successfully removed erroneous UNIQUE constraints from checklist and coa tables.")
