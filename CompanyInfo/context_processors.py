from django.core.cache import cache
from .models import CompanyInfo


def company_context(request):
    data = cache.get("global_company_info_context")
    if data is None:
        try:
            company = CompanyInfo.objects.first()
            if company:
                data = {
                    "name": company.name or "NCWSCwaterLAB",
                    "slug": company.slug or "ncwscwaterlab",
                    "logo": company.logo if company.logo else None,
                    "favicon": company.favicon if company.favicon else None,
                    "motto": company.motto or "",
                    "phone_number": company.phone_number or "",
                    "address": company.address or "",
                }
            else:
                data = {
                    "name": "NCWSCwaterLAB",
                    "slug": "ncwscwaterlab",
                    "logo": None,
                    "favicon": None,
                    "motto": "",
                    "phone_number": "",
                    "address": "",
                }
        except Exception:
            data = {
                "name": "NCWSCwaterLAB",
                "slug": "ncwscwaterlab",
                "logo": None,
                "favicon": None,
                "motto": "",
                "phone_number": "",
                "address": "",
            }
        cache.set("global_company_info_context", data, 3600)

    return {"company": data}
