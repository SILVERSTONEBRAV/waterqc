from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.http import HttpResponse

def render_to_pdf(template_src: str, context_dict: dict, filename: str = None) -> HttpResponse:
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()

    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        if filename:
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    return HttpResponse("PDF generation failed", status=500)
