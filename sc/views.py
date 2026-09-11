from django.template.loader import get_template
from xhtml2pdf import pisa
from django.http import HttpResponse
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import ShiftHandover

def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    result = HttpResponse(content_type='application/pdf')
    pisa_status = pisa.CreatePDF(html, dest=result)
    if pisa_status.err:
        return HttpResponse(f"We had some errors <pre>{html}</pre>")
    return result

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_shift_handover_pdf(request, pk):
    try:
        handover = ShiftHandover.objects.select_related(
            'shift', 'outgoing_supervisor', 'incoming_supervisor'
        ).prefetch_related('apparatus_conditions__apparatus').get(pk=pk)

        pdf = render_to_pdf('pdf/handover_template.html', {
            'handover': handover,
            'request': request  # allows use of {{ request.user }} in template
        })
        filename = f"Handover_{handover.shift.name}_{handover.date}.pdf"
        pdf['Content-Disposition'] = f'attachment; filename="{filename}"'
        return pdf
    except ShiftHandover.DoesNotExist:
        return HttpResponse("Handover not found", status=404)
