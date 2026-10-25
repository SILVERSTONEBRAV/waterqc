import os
import sys
import django
from datetime import timedelta, date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qad.settings')
django.setup()

from django.utils import timezone
from django.contrib.auth import get_user_model
from ca.models import (
    Chemical, Supplier, ChemicalLocation, ChemicalSpecification,
    ChemicalSpecificationRemark, PackagingStatus, ChemicalCertApprover,
    ChemicalBatch, ChemicalAnalysisRequest, ChecklistForWaterTreatmentChemicalAnalysis,
    ChemicalAnalysisProcess, BatchTestResult, ChemicalAnalysisInput, ChemicalCoA
)
from t.models import TreatmentPlant

from django.contrib.auth.models import Group
User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first()
plant_user = User.objects.filter(username="TEST_PLANT_ANALYST").first() or admin_user

lab_group, _ = Group.objects.get_or_create(name="Laboratory Technician")
admin_user.groups.add(lab_group)
plant_user.groups.add(lab_group)

print(f"Using admin_user: {admin_user}, plant_user: {plant_user}")

# 1. Plants
plants_data = [
    {"name": "Ngethu Water Treatment Plant", "code": "NGH", "location": "Gatundu, Kiambu County"},
    {"name": "Sasumua Regional Plant", "code": "SAS", "location": "Njabini, Nyandarua County"},
    {"name": "Ruiru Treatment Works", "code": "RUI", "location": "Githunguri, Kiambu County"},
    {"name": "Kabete Water Treatment Plant", "code": "KAB", "location": "Kabete, Nairobi County"},
    {"name": "Gigiri Distribution Station", "code": "GIG", "location": "Gigiri, Nairobi County"},
    {"name": "Kiambu Pumping Station", "code": "KIA", "location": "Kiambu Town, Kiambu County"},
]

plants = {}
for p_info in plants_data:
    obj, created = TreatmentPlant.objects.update_or_create(
        code=p_info["code"],
        defaults={"name": p_info["name"], "location": p_info["location"]}
    )
    plants[p_info["code"]] = obj
    print(f"Plant: {obj.name} ({obj.code})")

# 2. Chemical Locations
locations = {}
loc_defs = [
    ("Ngethu Intake Bay", "NGH"),
    ("Ngethu Main Chemical Warehouse", "NGH"),
    ("Ngethu Chlorine Gas Enclosure", "NGH"),
    ("Sasumua Intake Bay", "SAS"),
    ("Sasumua Main Store", "SAS"),
    ("Ruiru Coagulant Yard", "RUI"),
    ("Kabete Central Lab Intake", "KAB"),
    ("Gigiri Distribution Bay", "GIG"),
    ("Kiambu Storage Depot", "KIA"),
]
for loc_name, p_code in loc_defs:
    loc, _ = ChemicalLocation.objects.get_or_create(
        name=loc_name,
        treatment_plant=plants[p_code]
    )
    locations[loc_name] = loc

# 3. Packaging Statuses
pkg_intact, _ = PackagingStatus.objects.get_or_create(
    name="Sound Sealed Bags",
    defaults={"description": "Standard 50kg multi-layer polypropylene woven sacks, hermetically sealed."}
)
pkg_cylinder, _ = PackagingStatus.objects.get_or_create(
    name="Pressurized Ton Cylinders",
    defaults={"description": "High-pressure ton containers inspected and pressure-certified."}
)
pkg_drums, _ = PackagingStatus.objects.get_or_create(
    name="Airtight Drums",
    defaults={"description": "Heavy-duty HDPE drums with tamper-evident seal."}
)

# 4. Chemicals
chemicals_data = [
    {
        "name": "Alum (Aluminium Sulphate)",
        "code": "ALUM",
        "description": "Solid granular aluminium sulphate coagulant conforming to KS 05-459 Type 1.",
        "grade": "Type 1 Granular Coagulant Grade A",
        "hydrometer_formula": "reading * 1.025",
    },
    {
        "name": "Chlorine Gas",
        "code": "CHL",
        "description": "Liquefied elemental chlorine gas for primary disinfection and pathogen inactivation.",
        "grade": "Liquid Chlorine 99.5% Purity",
        "hydrometer_formula": "",
    },
    {
        "name": "Hydrated Lime",
        "code": "LIME",
        "description": "High-calcium hydrated lime for pre/post-alkalinity adjustment and pH correction.",
        "grade": "Industrial Grade 92% Ca(OH)2",
        "hydrometer_formula": "",
    },
    {
        "name": "Polymer Coagulant Aid",
        "code": "POLY",
        "description": "High molecular weight cationic polyacrylamide flocculant aid for rapid floc settlement.",
        "grade": "Polyelectrolyte Coagulant Aid High Charge",
        "hydrometer_formula": "",
    },
    {
        "name": "Soda Ash",
        "code": "SODA",
        "description": "Dense sodium carbonate buffer for stabilization and precipitation softening.",
        "grade": "Dense Soda Ash 99.2% Na2CO3",
        "hydrometer_formula": "",
    },
]

chems = {}
for c_info in chemicals_data:
    chem, _ = Chemical.objects.update_or_create(
        code=c_info["code"],
        defaults={
            "name": c_info["name"],
            "description": c_info["description"],
            "grade": c_info["grade"],
            "hydrometer_formula": c_info["hydrometer_formula"],
        }
    )
    chems[c_info["code"]] = chem
    print(f"Chemical: {chem.name} ({chem.code})")

# 5. Suppliers
suppliers_data = [
    {
        "name": "BOC Gases Kenya Ltd",
        "contract_number": "NCWSC-T-2025-081",
        "contact_info": "Industrial Area, Kitui Rd, Nairobi | Tel: +254 20 6944000 | Email: sales@boc.co.ke",
    },
    {
        "name": "Kel Chemicals Limited",
        "contract_number": "NCWSC-T-2025-042",
        "contact_info": "Thika Industrial Zone | Tel: +254 67 21245 | Email: watertech@kelchemicals.com",
    },
    {
        "name": "Alkaline Solutions East Africa",
        "contract_number": "NCWSC-T-2025-109",
        "contact_info": "Mombasa Road Business Park | Tel: +254 722 000111 | Email: orders@alkalinesolutions.co.ke",
    },
    {
        "name": "Ecolab Water Technologies",
        "contract_number": "NCWSC-T-2025-067",
        "contact_info": "Delta Corner, Westlands | Tel: +254 20 4277000 | Email: contact@ecolab.com",
    },
    {
        "name": "Davis & Shirtliff Ltd",
        "contract_number": "NCWSC-T-2025-115",
        "contact_info": "D&S Complex, Dundori Rd | Tel: +254 20 6968000 | Email: chemdept@dayliff.com",
    },
]

supps = {}
for s_info in suppliers_data:
    supp, _ = Supplier.objects.update_or_create(
        contract_number=s_info["contract_number"],
        defaults={
            "name": s_info["name"],
            "contact_info": s_info["contact_info"],
        }
    )
    supps[s_info["name"]] = supp
    print(f"Supplier: {supp.name}")

# 6. Approver
if admin_user:
    approver, _ = ChemicalCertApprover.objects.get_or_create(user=admin_user)

# 7. Chemical Specifications
specs_matrix = [
    ("ALUM", "Total Soluble Alumina (Al2O3)", "%", 16.5, 18.0),
    ("ALUM", "pH (1% w/v aqueous solution)", "pH", 3.0, 4.5),
    ("ALUM", "Water Insoluble Matter", "%", 0.0, 0.5),
    ("ALUM", "Iron content as Fe", "%", 0.0, 0.01),
    ("CHL", "Chlorine Purity (Cl2)", "%", 99.5, 100.0),
    ("CHL", "Moisture Content", "%", 0.0, 0.015),
    ("CHL", "Non-Volatile Residue", "%", 0.0, 0.01),
    ("LIME", "Available Calcium Hydroxide Ca(OH)2", "%", 90.0, 100.0),
    ("LIME", "Moisture Content", "%", 0.0, 2.0),
    ("LIME", "Acid Insoluble Matter", "%", 0.0, 1.5),
    ("POLY", "Active Polymer Content", "%", 90.0, 100.0),
    ("POLY", "Viscosity (0.5% aqueous solution)", "mPa.s", 800.0, 1500.0),
    ("POLY", "Residual Monomer Content", "%", 0.0, 0.05),
    ("SODA", "Total Alkalinity as Na2CO3", "%", 99.0, 100.0),
    ("SODA", "Chloride content as NaCl", "%", 0.0, 0.5),
    ("SODA", "Iron content as Fe2O3", "%", 0.0, 0.004),
]

specs_by_plant_chem = {}
for p_code, plant in plants.items():
    for c_code, param, unit, min_lim, max_lim in specs_matrix:
        chem = chems[c_code]
        spec, _ = ChemicalSpecification.objects.update_or_create(
            chemical=chem,
            parameter_name=param,
            treatment_plant=plant,
            version=1,
            defaults={
                "unit": unit,
                "min_limit": min_lim,
                "max_limit": max_lim,
                "is_required": True,
            }
        )
        remark, _ = ChemicalSpecificationRemark.objects.get_or_create(
            specification=spec,
            defaults={
                "on_pass": f"{param} conforms strictly to KS 05-459 water treatment standards.",
                "on_fail": f"{param} deviates from KS 05-459 threshold ({min_lim}-{max_lim} {unit}).",
            }
        )
        specs_by_plant_chem.setdefault((plant.id, chem.id), []).append(spec)

print(f"Total Chemical Specifications created: {ChemicalSpecification.objects.count()}")

# 8. Batches Seed Data
now = timezone.now()
today = now.date()

batch_configs = [
    # Ngethu
    {"chem": "ALUM", "plant": "NGH", "supp": "Kel Chemicals Limited", "qty": 45000, "status": "APPROVED", "days_ago": 2},
    {"chem": "ALUM", "plant": "NGH", "supp": "Kel Chemicals Limited", "qty": 38000, "status": "APPROVED", "days_ago": 5},
    {"chem": "ALUM", "plant": "NGH", "supp": "Kel Chemicals Limited", "qty": 42000, "status": "UTILIZED", "days_ago": 12},
    {"chem": "CHL",  "plant": "NGH", "supp": "BOC Gases Kenya Ltd", "qty": 18000, "status": "APPROVED", "days_ago": 4},
    {"chem": "CHL",  "plant": "NGH", "supp": "BOC Gases Kenya Ltd", "qty": 15000, "status": "UTILIZED", "days_ago": 16},
    {"chem": "LIME", "plant": "NGH", "supp": "Alkaline Solutions East Africa", "qty": 24000, "status": "APPROVED", "days_ago": 7},
    {"chem": "LIME", "plant": "NGH", "supp": "Alkaline Solutions East Africa", "qty": 20000, "status": "ANALYSED", "days_ago": 1},
    {"chem": "POLY", "plant": "NGH", "supp": "Ecolab Water Technologies", "qty": 8500, "status": "APPROVED", "days_ago": 9},
    {"chem": "SODA", "plant": "NGH", "supp": "Davis & Shirtliff Ltd", "qty": 12000, "status": "RECEIVED", "days_ago": 0},
    {"chem": "ALUM", "plant": "NGH", "supp": "Kel Chemicals Limited", "qty": 30000, "status": "REJECTED", "days_ago": 20},

    # Sasumua
    {"chem": "ALUM", "plant": "SAS", "supp": "Kel Chemicals Limited", "qty": 32000, "status": "APPROVED", "days_ago": 3},
    {"chem": "ALUM", "plant": "SAS", "supp": "Kel Chemicals Limited", "qty": 28000, "status": "UTILIZED", "days_ago": 14},
    {"chem": "CHL",  "plant": "SAS", "supp": "BOC Gases Kenya Ltd", "qty": 12000, "status": "APPROVED", "days_ago": 6},
    {"chem": "LIME", "plant": "SAS", "supp": "Alkaline Solutions East Africa", "qty": 16000, "status": "APPROVED", "days_ago": 8},
    {"chem": "POLY", "plant": "SAS", "supp": "Ecolab Water Technologies", "qty": 6000, "status": "ANALYSED", "days_ago": 2},
    {"chem": "SODA", "plant": "SAS", "supp": "Davis & Shirtliff Ltd", "qty": 9000, "status": "RECEIVED", "days_ago": 1},

    # Ruiru
    {"chem": "ALUM", "plant": "RUI", "supp": "Kel Chemicals Limited", "qty": 26000, "status": "APPROVED", "days_ago": 4},
    {"chem": "CHL",  "plant": "RUI", "supp": "BOC Gases Kenya Ltd", "qty": 10000, "status": "APPROVED", "days_ago": 10},
    {"chem": "LIME", "plant": "RUI", "supp": "Alkaline Solutions East Africa", "qty": 14000, "status": "UTILIZED", "days_ago": 18},
    {"chem": "POLY", "plant": "RUI", "supp": "Ecolab Water Technologies", "qty": 5000, "status": "RECEIVED", "days_ago": 1},

    # Kabete
    {"chem": "ALUM", "plant": "KAB", "supp": "Kel Chemicals Limited", "qty": 22000, "status": "APPROVED", "days_ago": 5},
    {"chem": "CHL",  "plant": "KAB", "supp": "BOC Gases Kenya Ltd", "qty": 9000, "status": "APPROVED", "days_ago": 11},
    {"chem": "SODA", "plant": "KAB", "supp": "Davis & Shirtliff Ltd", "qty": 8000, "status": "ANALYSED", "days_ago": 3},

    # Gigiri
    {"chem": "CHL",  "plant": "GIG", "supp": "BOC Gases Kenya Ltd", "qty": 8000, "status": "APPROVED", "days_ago": 6},
    {"chem": "SODA", "plant": "GIG", "supp": "Davis & Shirtliff Ltd", "qty": 6500, "status": "RECEIVED", "days_ago": 2},

    # Kiambu
    {"chem": "CHL",  "plant": "KIA", "supp": "BOC Gases Kenya Ltd", "qty": 6000, "status": "APPROVED", "days_ago": 7},
    {"chem": "ALUM", "plant": "KIA", "supp": "Kel Chemicals Limited", "qty": 15000, "status": "ANALYSED", "days_ago": 2},
]

for idx, cfg in enumerate(batch_configs, start=1):
    chem = chems[cfg["chem"]]
    plant = plants[cfg["plant"]]
    supp = supps[cfg["supp"]]
    deliv_date = today - timedelta(days=cfg["days_ago"])
    deliv_note = f"DN-{plant.code}-{2026}-{idx:04d}"
    batch_num = f"BN-{chem.code}-{idx:04d}"

    batch, b_created = ChemicalBatch.objects.get_or_create(
        batch_number=batch_num,
        defaults={
            "delivery_note_number": deliv_note,
            "chemical": chem,
            "supplier": supp,
            "treatment_plant": plant,
            "quantity_received": float(cfg["qty"]),
            "unit": "kg",
            "package_count": int(cfg["qty"] / 50) if cfg["chem"] != "CHL" else int(cfg["qty"] / 1000),
            "received_by": admin_user,
            "status": cfg["status"],
            "coa_generated": (cfg["status"] in ["APPROVED", "UTILIZED"]),
            "remarks": f"Operational delivery for {plant.name} water purification intake.",
        }
    )

    # Pick location
    loc_candidates = [l for l in locations.values() if l.treatment_plant_id == plant.id]
    loc = loc_candidates[0] if loc_candidates else locations["Ngethu Intake Bay"]

    # Request
    req_status = (
        ChemicalAnalysisRequest.Status.COMPLETED if cfg["status"] in ["APPROVED", "UTILIZED", "REJECTED"]
        else ChemicalAnalysisRequest.Status.IN_PROGRESS if cfg["status"] == "ANALYSED"
        else ChemicalAnalysisRequest.Status.PENDING
    )
    req, req_created = ChemicalAnalysisRequest.objects.get_or_create(
        batch=batch,
        defaults={
            "requested_by": admin_user,
            "delivery_date": deliv_date,
            "location": loc,
            "analysis_started_at": now - timedelta(days=cfg["days_ago"], hours=4),
            "analysis_deadline": now - timedelta(days=cfg["days_ago"]) + timedelta(hours=9),
            "completed_at": now - timedelta(days=cfg["days_ago"], hours=1) if req_status == ChemicalAnalysisRequest.Status.COMPLETED else None,
            "completed_by": admin_user if req_status == ChemicalAnalysisRequest.Status.COMPLETED else None,
            "status": req_status,
        }
    )
    if req_created:
        # Add the admin user as assigned analyst first (M2M must exist before received_by)
        req.assigned_analysts.add(admin_user)
        # Now safe to set received_by
        req.received_by = admin_user
        ChemicalAnalysisRequest.objects.filter(pk=req.pk).update(received_by=admin_user)

    # Checklist
    chk, _ = ChecklistForWaterTreatmentChemicalAnalysis.objects.get_or_create(
        chemical_analysis_request=req,
        chemical=chem,
        defaults={
            "manufacturer_name_indicated": True,
            "chemical_name_on_label": True,
            "min_mass_indicated": True,
            "grade": ChecklistForWaterTreatmentChemicalAnalysis.Grade.PREMIUM,
            "manufacture_date": deliv_date - timedelta(days=30),
            "expiry_date": deliv_date + timedelta(days=700),
            "storage_conditions": "Cool, dry, ventilated chemical warehouse away from direct sunlight.",
            "net_weight": Decimal(str(cfg["qty"])),
            "country_of_origin": "KE",
            "handling_instructions": "Wear standard PPE (acid/alkali resistant gloves, goggles, face shield, respirator).",
            "sampled_by": admin_user,
            "requested_by": admin_user,
            "completed": True,
            "completed_at": now - timedelta(days=cfg["days_ago"], hours=5),
            "completed_by": admin_user,
        }
    )

    # Process
    wf_status = (
        ChemicalAnalysisProcess.WorkflowStatus.UTILIZED if cfg["status"] == "UTILIZED"
        else ChemicalAnalysisProcess.WorkflowStatus.APPROVED if cfg["status"] == "APPROVED"
        else ChemicalAnalysisProcess.WorkflowStatus.REJECTED if cfg["status"] == "REJECTED"
        else ChemicalAnalysisProcess.WorkflowStatus.QA if cfg["status"] == "ANALYSED"
        else ChemicalAnalysisProcess.WorkflowStatus.RECEIVED
    )
    proc, _ = ChemicalAnalysisProcess.objects.get_or_create(
        batch=batch,
        defaults={
            "analysis_request": req,
            "status": wf_status,
            "started_at": now - timedelta(days=cfg["days_ago"], hours=5),
            "analysis_started_at": now - timedelta(days=cfg["days_ago"], hours=4),
            "checklist_completed_at": now - timedelta(days=cfg["days_ago"], hours=5),
            "analysis_completed_at": now - timedelta(days=cfg["days_ago"], hours=2) if wf_status != ChemicalAnalysisProcess.WorkflowStatus.RECEIVED else None,
            "qa_reviewed_at": now - timedelta(days=cfg["days_ago"], hours=1) if wf_status in [ChemicalAnalysisProcess.WorkflowStatus.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.UTILIZED] else None,
            "approved_at": now - timedelta(days=cfg["days_ago"]) if wf_status in [ChemicalAnalysisProcess.WorkflowStatus.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.UTILIZED] else None,
            "assigned_analyst": admin_user,
            "qa_officer": admin_user,
            "approver": admin_user if wf_status in [ChemicalAnalysisProcess.WorkflowStatus.APPROVED, ChemicalAnalysisProcess.WorkflowStatus.UTILIZED] else None,
        }
    )

    # Test Results & Inputs
    specs = specs_by_plant_chem.get((plant.id, chem.id), [])
    is_rejected = (cfg["status"] == "REJECTED")

    for s_idx, spec in enumerate(specs):
        if cfg["status"] in ["APPROVED", "UTILIZED", "ANALYSED", "REJECTED"]:
            if is_rejected and s_idx == 0:
                # Deliberately fail first spec for rejected batch
                val = (spec.min_limit - 1.0) if spec.min_limit else 0.0
                res_status = BatchTestResult.Status.FAIL
            else:
                if spec.min_limit is not None and spec.max_limit is not None:
                    val = round((spec.min_limit + spec.max_limit) / 2.0, 3)
                elif spec.min_limit is not None:
                    val = round(spec.min_limit + 1.0, 3)
                else:
                    val = 1.0
                res_status = BatchTestResult.Status.PASS

            res, _ = BatchTestResult.objects.get_or_create(
                batch=batch,
                parameter=spec,
                defaults={
                    "value": val,
                    "textual_result": f"{val} {spec.unit}",
                    "status": res_status,
                    "tested_at": now - timedelta(days=cfg["days_ago"], hours=3),
                    "analyst": admin_user,
                    "auto_remark": "Meets KS 05-459 specification standard." if res_status == BatchTestResult.Status.PASS else "Failed specification limit.",
                }
            )

            # ChemicalAnalysisInput (only if spec has an analysis_method)
            if getattr(spec, "analysis_method", None):
                try:
                    ChemicalAnalysisInput.objects.get_or_create(
                        test_result=res,
                        defaults={
                            "inputs": {"sample_mass": 5.0, "titre_volume": 14.8, "factor": 1.01},
                            "calculated_value": val,
                        }
                    )
                except Exception:
                    pass

    # CoA
    if cfg["status"] in ["APPROVED", "UTILIZED"]:
        coa, coa_created = ChemicalCoA.objects.get_or_create(
            batch=batch,
            defaults={
                "title": f"CERTIFICATE OF ANALYSIS - {batch.sample_id}",
                "chemical_name": chem.name,
                "supplier_name": supp.name,
                "quantity": batch.quantity_received,
                "delivered_to": plant.name,
                "delivery_date": deliv_date,
                "delivery_note_number": deliv_note,
                "packaging_status": pkg_intact if cfg["chem"] != "CHL" else pkg_cylinder,
                "sampling_date": deliv_date,
                "analysis_date": deliv_date,
                "results_summary": "All physicochemical, active content, and impurity tests conform strictly to KS 05-459 standards.",
                "remarks": "Approved for full operational water treatment utilization at treatment works.",
            }
        )
        ChemicalCoA.objects.filter(pk=coa.pk).update(
            approved_by=admin_user,
            approved_on=now - timedelta(days=cfg["days_ago"])
        )

print("\n--- SEEDING COMPLETED ---")
print("Batches count:", ChemicalBatch.objects.count())
print("Requests count:", ChemicalAnalysisRequest.objects.count())
print("Processes count:", ChemicalAnalysisProcess.objects.count())
print("Results count:", BatchTestResult.objects.count())
print("Inputs count:", ChemicalAnalysisInput.objects.count())
print("CoAs count:", ChemicalCoA.objects.count())
