from .models import JarTest
from datetime import date

def get_latest_dosage(chemical, treatment_plant):
    latest_test = JarTest.objects.filter(
        coagulant=chemical,
        treatment_plant=treatment_plant,
        established_dosage_mg_per_l__isnull=False,
        approval_status='approved'  # adjust field name/value to your model
    ).order_by('-test_date').first()

    if latest_test:
        return latest_test.established_dosage_mg_per_l
    return None
