"""
Seed realistic Chemical Analysis (CA) data for Ngethu Quality Assurance system.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, PARENT_DIR)
sys.path.insert(0, BASE_DIR)

import random
import django
from datetime import datetime, timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qad.settings")
django.setup()

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from t.models import TreatmentPlant
from ca.models import (
    Chemical,
    Supplier,
    ChemicalLocation,
    ChemicalSpecification,
    ChemicalBatch,
    ChemicalAnalysisRequest,
    ChecklistForWaterTreatmentChemicalAnalysis,
    ChemicalAnalysisProcess,
    BatchTestResult,
    ChemicalCoA,
)

User = get_user_model()

def run_seed():
    print("Seeding Chemical Analysis (CA) data...")

    # 1. Users
    admin_user, _ = User.objects.get_or_create(
        username="ADMIN",
        defaults={
            "email": "admin@nairobiwater.co.ke",
            "first_name": "Samuel",
            "last_name": "Wanjala",
            "is_staff": True,
            "is_superuser": True,
            "email_verified": True,
            "is_active": True,
        }
    )
    admin_user.set_password("Admin12345!")
    admin_user.save()

    analyst_group, _ = Group.objects.get_or_create(name="Laboratory Technician")

    analyst_user, _ = User.objects.get_or_create(
        username="ANALYST_JANE",
        defaults={
            "email": "jane.mutua@nairobiwater.co.ke",
            "first_name": "Jane",
            "last_name": "Mutua",
            "is_staff": True,
            "email_verified": True,
            "is_active": True,
        }
    )
    analyst_user.set_password("Analyst12345!")
    analyst_user.groups.add(analyst_group)
    analyst_user.save()

    qa_user, _ = User.objects.get_or_create(
        username="QA_KIPROP",
        defaults={
            "email": "kiprop.rono@nairobiwater.co.ke",
            "first_name": "David",
            "last_name": "Kiprop",
            "is_staff": True,
            "email_verified": True,
            "is_active": True,
        }
    )
    qa_user.set_password("Qa12345!")
    qa_user.save()

    # 2. Treatment Plants
    ngethu, _ = TreatmentPlant.objects.get_or_create(
        code="NGH",
        defaults={"name": "Ngethu Water Treatment Plant", "location": "Kiambu County"}
    )
    sasumua, _ = TreatmentPlant.objects.get_or_create(
        code="SAS",
        defaults={"name": "Sasumua Water Treatment Plant", "location": "Nyandarua County"}
    )

    admin_user.assigned_treatment_plant = ngethu
    admin_user.save()

    # 3. Suppliers
    suppliers_data = [
        ("Davis & Shirtliff Ltd", "DS-2026-001", "info@dayliff.com"),
        ("Desbro Kenya Ltd", "DES-2026-014", "sales@desbro.co.ke"),
        ("BASF East Africa Ltd", "BASF-2026-088", "chemicals@basf.com"),
        ("Chemchem Chemicals Ltd", "CCC-2026-003", "contact@chemchem.co.ke"),
    ]
    suppliers = []
    for name, contract, contact in suppliers_data:
        sup, _ = Supplier.objects.get_or_create(
            name=name,
            defaults={"contract_number": contract, "contact_info": contact}
        )
        suppliers.append(sup)

    # 4. Locations
    locations_data = [
        ("Main Warehouse Bay A", ngethu),
        ("Liquid Alum Dosing Tank 1", ngethu),
        ("Chlorine Drum Yard", ngethu),
        ("Lime Storage Silo 2", ngethu),
        ("Polymer Prep Room", ngethu),
    ]
    locations = []
    for loc_name, plant in locations_data:
        loc, _ = ChemicalLocation.objects.get_or_create(
            name=loc_name,
            treatment_plant=plant,
        )
        locations.append(loc)

    # 5. Chemicals & Specifications
    chemicals_data = [
        {
            "name": "Aluminum Sulphate (Alum)",
            "code": "ALUM",
            "grade": "Type A Granular",
            "specs": [
                ("Al2O3 Soluble Content", "%", 16.0, 18.5),
                ("Insoluble Matter", "%", 0.0, 0.5),
                ("Free Acidity as H2SO4", "%", 0.0, 0.2),
                ("Iron (Fe) Content", "%", 0.0, 0.05),
                ("pH (1% aqueous solution)", "pH", 3.0, 4.5),
            ]
        },
        {
            "name": "Chlorine Gas",
            "code": "CL2",
            "grade": "Liquefied Gas 99.5%",
            "specs": [
                ("Chlorine Purity", "%", 99.5, 100.0),
                ("Moisture by Mass", "%", 0.0, 0.015),
                ("Non-volatile Residue", "%", 0.0, 0.05),
            ]
        },
        {
            "name": "Hydrated Lime",
            "code": "LIME",
            "grade": "Technical Water Grade",
            "specs": [
                ("Available Ca(OH)2", "%", 85.0, 98.0),
                ("Free Moisture", "%", 0.0, 1.5),
                ("Fineness (Passing 90um)", "%", 95.0, 100.0),
            ]
        },
        {
            "name": "Poly-electrolyte (Coagulant Aid)",
            "code": "POLY",
            "grade": "Cationic Polymer",
            "specs": [
                ("Active Polymer Content", "%", 90.0, 99.0),
                ("Bulk Density", "g/cm3", 0.70, 0.90),
                ("Viscosity (0.5% sol)", "mPa.s", 800.0, 1500.0),
            ]
        },
        {
            "name": "Soda Ash (Sodium Carbonate)",
            "code": "SODA",
            "grade": "Dense Soda Ash",
            "specs": [
                ("Total Alkali as Na2CO3", "%", 99.0, 100.0),
                ("Chloride as NaCl", "%", 0.0, 0.5),
                ("Iron as Fe2O3", "%", 0.0, 0.005),
            ]
        },
    ]

    chemicals_dict = {}
    specs_dict = {}
    for chem_info in chemicals_data:
        chem, _ = Chemical.objects.get_or_create(
            name=chem_info["name"],
            defaults={
                "code": chem_info["code"],
                "grade": chem_info["grade"],
                "description": f"Standard water treatment chemical: {chem_info['name']}"
            }
        )
        chemicals_dict[chem.code] = chem
        specs_dict[chem.code] = []
        for p_name, unit, min_l, max_l in chem_info["specs"]:
            spec, _ = ChemicalSpecification.objects.get_or_create(
                chemical=chem,
                parameter_name=p_name,
                treatment_plant=ngethu,
                defaults={
                    "unit": unit,
                    "min_limit": min_l,
                    "max_limit": max_l,
                    "is_required": True,
                    "version": 1
                }
            )
            specs_dict[chem.code].append(spec)

    # 6. Seed Chemical Batches & Lifecycles spanning the last 30 days
    now = timezone.now()
    today = now.date()

    # Generate 28 batches across dates
    created_batches = 0
    created_processes = 0
    created_results = 0

    batch_configs = [
        # (days_ago, chem_code, supplier_idx, qty, status, process_status)
        (28, "ALUM", 0, 24000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (26, "CL2",  1, 4000,  ChemicalBatch.Status.UTILIZED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (24, "LIME", 2, 18000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (22, "POLY", 3, 2000,  ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (20, "SODA", 1, 15000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (18, "ALUM", 0, 30000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (17, "CL2",  2, 5000,  ChemicalBatch.Status.REJECTED, ChemicalAnalysisProcess.WorkflowStatus.REJECTED),
        (15, "LIME", 3, 20000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (14, "POLY", 0, 2500,  ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (12, "ALUM", 1, 28000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (10, "SODA", 2, 16000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (9,  "CL2",  3, 4500,  ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (8,  "LIME", 0, 22000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED),
        (7,  "ALUM", 1, 32000, ChemicalBatch.Status.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.APPROVED),
        (6,  "POLY", 2, 3000,  ChemicalBatch.Status.ANALYSED, ChemicalAnalysisProcess.WorkflowStatus.APPROVED),
        (5,  "SODA", 3, 14000, ChemicalBatch.Status.ANALYSED, ChemicalAnalysisProcess.WorkflowStatus.QA),
        (4,  "ALUM", 0, 25000, ChemicalBatch.Status.ANALYSED, ChemicalAnalysisProcess.WorkflowStatus.QA),
        (3,  "CL2",  1, 6000,  ChemicalBatch.Status.ANALYSED, ChemicalAnalysisProcess.WorkflowStatus.RETEST),
        (3,  "LIME", 2, 19000, ChemicalBatch.Status.ANALYSED, ChemicalAnalysisProcess.WorkflowStatus.ANALYSIS),
        (2,  "POLY", 0, 2200,  ChemicalBatch.Status.ANALYSED, ChemicalAnalysisProcess.WorkflowStatus.ANALYSIS),
        (2,  "ALUM", 3, 35000, ChemicalBatch.Status.RECEIVED, ChemicalAnalysisProcess.WorkflowStatus.ANALYSIS),
        (1,  "SODA", 1, 18000, ChemicalBatch.Status.RECEIVED, ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST),
        (1,  "CL2",  2, 5500,  ChemicalBatch.Status.RECEIVED, ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST),
        (0,  "ALUM", 0, 28000, ChemicalBatch.Status.RECEIVED, ChemicalAnalysisProcess.WorkflowStatus.REQUESTED),
        (0,  "LIME", 3, 15000, ChemicalBatch.Status.RECEIVED, ChemicalAnalysisProcess.WorkflowStatus.RECEIVED),
    ]

    for idx, (days_ago, chem_code, sup_idx, qty, b_status, p_status) in enumerate(batch_configs, 1):
        target_date = today - timedelta(days=days_ago)
        target_dt = now - timedelta(days=days_ago, hours=random.randint(1, 12))
        chem = chemicals_dict[chem_code]
        supplier = suppliers[sup_idx % len(suppliers)]
        loc = locations[(idx - 1) % len(locations)]

        batch_num = f"BTH-{chem.code}-2026-{idx:03d}"
        delivery_num = f"DEL-2026-{idx:04d}"

        # Create or update batch
        batch, created = ChemicalBatch.objects.get_or_create(
            batch_number=batch_num,
            defaults={
                "chemical": chem,
                "supplier": supplier,
                "treatment_plant": ngethu,
                "received_date": target_date,
                "quantity_received": qty,
                "delivery_note_number": delivery_num,
                "package_count": max(1, qty // 50),
                "received_by": admin_user,
                "status": b_status,
                "remarks": f"Sample delivery of {chem.name} from {supplier.name}.",
                "coa_generated": b_status in [ChemicalBatch.Status.APPROVED, ChemicalBatch.Status.UTILIZED],
            }
        )
        if not created:
            batch.status = b_status
            if not batch.delivery_note_number:
                batch.delivery_note_number = delivery_num
            batch.save()
        created_batches += 1

        # Request
        req, r_created = ChemicalAnalysisRequest.objects.get_or_create(
            batch=batch,
            defaults={
                "delivery_date": target_date,
                "location": loc,
                "requested_by": admin_user,
                "analysis_started_at": target_dt if p_status not in [ChemicalAnalysisProcess.WorkflowStatus.RECEIVED, ChemicalAnalysisProcess.WorkflowStatus.REQUESTED] else None,
                "analysis_deadline": target_dt + timedelta(hours=9),
                "completed_at": (target_dt + timedelta(hours=6)) if p_status in [ChemicalAnalysisProcess.WorkflowStatus.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED] else None,
            }
        )
        req.assigned_analysts.add(analyst_user)
        req.received_by = analyst_user
        req.save()

        # Checklist
        checklist, _ = ChecklistForWaterTreatmentChemicalAnalysis.objects.get_or_create(
            chemical_analysis_request=req,
            chemical=chem,
            defaults={
                "manufacturer_name_indicated": True,
                "chemical_name_on_label": True,
                "min_mass_indicated": True,
                "grade": ChecklistForWaterTreatmentChemicalAnalysis.Grade.STANDARD,
                "manufacture_date": target_date - timedelta(days=30),
                "expiry_date": target_date + timedelta(days=365),
                "storage_conditions": "Store in dry well-ventilated warehouse.",
                "net_weight": qty,
            }
        )

        # Process
        is_completed = (p_status == ChemicalAnalysisProcess.WorkflowStatus.COMPLETED)
        is_approved = p_status in [ChemicalAnalysisProcess.WorkflowStatus.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED]
        is_rejected = (p_status == ChemicalAnalysisProcess.WorkflowStatus.REJECTED)
        is_analyzed = p_status in [ChemicalAnalysisProcess.WorkflowStatus.QA, ChemicalAnalysisProcess.WorkflowStatus.RETEST, ChemicalAnalysisProcess.WorkflowStatus.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED, ChemicalAnalysisProcess.WorkflowStatus.REJECTED]

        process, p_created = ChemicalAnalysisProcess.objects.get_or_create(
            batch=batch,
            defaults={
                "analysis_request": req,
                "flow_class": "ca.chemical_flow.ChemicalAnalysisFlow",
                "initiated_by": admin_user,
                "assigned_analyst": analyst_user,
                "qa_officer": qa_user,
                "approver": admin_user,
                "status": p_status,
                "created": target_dt,
                "started_at": target_dt,
                "analysis_started_at": target_dt,
                "analysis_completed_at": (target_dt + timedelta(hours=4)) if is_analyzed else None,
                "approved_at": (target_dt + timedelta(hours=6)) if is_approved else None,
                "rejected_at": (target_dt + timedelta(hours=6)) if is_rejected else None,
                "completed_at": (target_dt + timedelta(hours=8)) if is_completed else None,
            }
        )
        if not p_created:
            process.status = p_status
            process.flow_class = "ca.chemical_flow.ChemicalAnalysisFlow"
            process.analysis_started_at = target_dt
            if is_analyzed:
                process.analysis_completed_at = target_dt + timedelta(hours=4)
            if is_approved:
                process.approved_at = target_dt + timedelta(hours=6)
            if is_rejected:
                process.rejected_at = target_dt + timedelta(hours=6)
            if is_completed:
                process.completed_at = target_dt + timedelta(hours=8)
            process.save()
        created_processes += 1

        # Test results for batches that reached analysis or beyond
        if p_status not in [ChemicalAnalysisProcess.WorkflowStatus.RECEIVED, ChemicalAnalysisProcess.WorkflowStatus.REQUESTED, ChemicalAnalysisProcess.WorkflowStatus.CHECKLIST]:
            chem_specs = specs_dict.get(chem.code, [])
            for spec in chem_specs:
                # Decide if pass or fail
                is_fail = (p_status == ChemicalAnalysisProcess.WorkflowStatus.REJECTED and random.random() < 0.6)
                if is_fail:
                    val = (spec.min_limit - 1.5) if spec.min_limit else (spec.max_limit + 2.0)
                    r_status = BatchTestResult.Status.FAIL
                elif p_status == ChemicalAnalysisProcess.WorkflowStatus.RETEST and random.random() < 0.5:
                    val = spec.min_limit or 1.0
                    r_status = BatchTestResult.Status.FAIL
                else:
                    min_v = spec.min_limit if spec.min_limit is not None else 0.1
                    max_v = spec.max_limit if spec.max_limit is not None else min_v + 5.0
                    val = round(random.uniform(min_v, max_v), 3)
                    r_status = BatchTestResult.Status.PASS

                result, _ = BatchTestResult.objects.get_or_create(
                    batch=batch,
                    parameter=spec,
                    defaults={
                        "value": val,
                        "status": r_status,
                        "tested_at": target_dt + timedelta(hours=random.randint(1, 5)),
                        "analyst": analyst_user,
                        "auto_remark": f"Parameter evaluated as {r_status} against spec limits."
                    }
                )
                created_results += 1

        # CoA for approved batches
        if p_status in [ChemicalAnalysisProcess.WorkflowStatus.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.COMPLETED]:
            coa, _ = ChemicalCoA.objects.get_or_create(
                batch=batch,
                defaults={
                    "title": f"Certificate of Analysis - {batch.batch_number}",
                    "coa_header": f"NAIROBI CITY WATER & SEWERAGE COMPANY\nQUALITY ASSURANCE DEPARTMENT - {ngethu.name}",
                    "coa_footer": "This certificate verifies compliance with KS EAS water chemical standards.",
                    "chemical_name": chem.name,
                    "supplier_name": supplier.name,
                }
            )

    print(f"Successfully seeded:")
    print(f" - {created_batches} Chemical Batches across 30 days")
    print(f" - {created_processes} Chemical Analysis Processes in active workflow stages")
    print(f" - {created_results} Analytical Test Results (PASS, FAIL, RETEST)")
    print(f" - Treatment Plants, Chemicals, Specs, Checklists, and CoAs")

if __name__ == "__main__":
    run_seed()
