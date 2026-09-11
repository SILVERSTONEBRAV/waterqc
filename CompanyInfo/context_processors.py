from .models import CompanyInfo

def company_context(request):
    company = CompanyInfo.objects.first()

    return {
        "company": {
            "name": company.name if company and company.name else "NCWSCwaterLAB",
            "slug": company.slug if company and company.slug else "ncwscwaterlab",
            "logo": company.logo if company and company.logo else None,
            "favicon": company.favicon if company and company.favicon else None,
            "motto": company.motto if company and company.motto else "",
            "phone_number": company.phone_number if company and company.phone_number else "",
            "address": company.address if company and company.address else "",
        }
    }
