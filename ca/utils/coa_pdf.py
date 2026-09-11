# ca/utils/coa_pdf.py
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image, ImageDraw, ImageFont
import qrcode
import textwrap
import math

def generate_qr_code(data: str) -> BytesIO:
    qr = qrcode.QRCode(box_size=6, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def wrap_text(c: canvas.Canvas, text: str, x: float, y: float, width: float, line_height: float, font_name: str, font_size: int):
    c.setFont(font_name, font_size)
    wrapped_lines = textwrap.wrap(text, width=int(width / (font_size * 0.55)))
    for line in wrapped_lines:
        c.drawString(x, y, line)
        y -= line_height
    return y

def create_celestial_watermark(text: str = "CONFIDENTIAL", font_size: int = 80, opacity: int = 25) -> Image.Image:
    """Create a celestial, futuristic watermark with a faint gradient."""
    img_size = 800
    wm = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(wm)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    text_width, text_height = draw.textsize(text, font=font)

    # Create a soft gradient along text
    for i, char in enumerate(text):
        color_val = 50 + int((205 / len(text)) * i)  # subtle rainbow-like gradient
        draw.text(
            ((img_size - text_width) / 2 + i * (text_width / len(text)), (img_size - text_height) / 2),
            char,
            fill=(color_val, 0, 255 - color_val, opacity),
            font=font
        )
    wm = wm.rotate(45, expand=1)
    return wm

def generate_coa_pdf(coa, qr_image: BytesIO = None, watermark: Image.Image = None) -> BytesIO:
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Fonts
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", "DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVuBold", "DejaVuSans-Bold.ttf"))
        title_font = "DejaVuBold"
        body_font = "DejaVu"
    except Exception:
        title_font = body_font = "Helvetica"

    # Fallback celestial watermark
    if watermark is None:
        watermark = create_celestial_watermark()

    def draw_watermark():
        try:
            wm_io = BytesIO()
            watermark.save(wm_io, format="PNG")
            wm_io.seek(0)
            wm_image = ImageReader(wm_io)
            p.saveState()
            for x_offset in range(-int(width), int(width*2), 300):
                for y_offset in range(-int(height), int(height*2), 300):
                    p.drawImage(wm_image, x_offset, y_offset, width=300, height=300, mask="auto")
            p.restoreState()
        except Exception as e:
            print("Watermark draw failed:", e)

    # --- Draw watermark ---
    draw_watermark()

    # --- Header with celestial gradient ---
    p.saveState()
    gradient_colors = [colors.HexColor("#6a11cb"), colors.HexColor("#2575fc")]
    for i, c in enumerate(gradient_colors):
        p.setFillColor(c)
        p.rect(0, height-60 + i*10, width, 10, stroke=0, fill=1)
    p.restoreState()
    p.setFont(title_font, 20)
    p.setFillColor(colors.darkblue)
    p.drawCentredString(width/2, height-50, coa.title)

    # --- COA Metadata ---
    p.setFont(body_font, 11)
    y = height - 100
    line_gap = 18
    metadata = [
        f"Chemical: {coa.chemical_name}",
        f"Supplier: {coa.supplier_name}",
        f"Batch: {coa.batch.sample_id}",
        f"Delivered To: {coa.delivered_to}",
        f"Delivery Date: {coa.delivery_date}",
        f"Delivery Note #: {coa.delivery_note_number}",
        f"Sampling Date: {coa.sampling_date}",
        f"Analysis Date: {coa.analysis_date}",
        f"Quantity: {coa.quantity} kg",
    ]
    for line in metadata:
        p.drawString(50, y, line)
        y -= line_gap

    # --- Remarks with elegant italic font ---
    if coa.remarks:
        p.setFont("Helvetica-Oblique", 10)
        p.drawString(50, y, "Remarks:")
        y -= line_gap
        y = wrap_text(p, coa.remarks, 60, y, width-120, line_gap, "Helvetica-Oblique", 10)
        y -= 10

    # --- Test Results Table with alternate row shading ---
    results = coa.batch.test_results.all()
    if results.exists():
        if y < 150:
            p.showPage()
            draw_watermark()
            y = height-100
            p.setFont(body_font, 11)

        p.setFont(title_font, 12)
        p.drawString(50, y, "Test Results:")
        y -= line_gap
        p.setFont(body_font, 10)
        # Header
        p.setFillColor(colors.HexColor("#4B0082"))
        p.drawString(60, y, "Parameter")
        p.drawString(220, y, "Value (unit)")
        p.drawString(360, y, "Status")
        y -= line_gap
        p.line(50, y+8, width-50, y+8)
        # Rows
        for idx, tr in enumerate(results):
            if y < 100:
                p.showPage()
                draw_watermark()
                y = height-100
                p.setFont(body_font, 10)

            param = tr.parameter.parameter_name if tr.parameter else "N/A"
            unit = f" {tr.parameter.unit}" if tr.parameter and tr.parameter.unit else ""
            value = str(tr.value) if tr.value is not None else tr.textual_result or ""
            status = tr.status
            # alternate row background
            if idx % 2 == 0:
                p.setFillColor(colors.HexColor("#f3f3f3"))
                p.rect(50, y-2, width-100, line_gap, stroke=0, fill=1)
            p.setFillColor(colors.black)
            p.drawString(60, y, param)
            p.drawString(220, y, value + unit)
            p.setFillColor(colors.green if status=="PASS" else colors.red if status=="FAIL" else colors.black)
            p.drawString(360, y, status)
            y -= line_gap
        p.setFillColor(colors.black)

    # --- Signature and Approval with embossed effect ---
    y -= 30
    p.setFont(body_font, 11)
    p.drawString(50, y, f"Approved By: {coa.approved_by.get_full_name() if coa.approved_by else ''}")
    y -= 20
    if coa.approved_by and hasattr(coa.approved_by, "chemicalcertapprover"):
        cert = getattr(coa.approved_by, "chemicalcertapprover")
        if cert.signature and cert.signature.path:
            try:
                sig_img = Image.open(cert.signature.path)
                sig_io = BytesIO()
                sig_img.save(sig_io, format="PNG")
                sig_io.seek(0)
                p.drawImage(ImageReader(sig_io), 60, y-50, width=100, height=50, mask="auto")
            except Exception:
                pass
    y -= 60

    # --- Footer with soft gradient ---
    p.saveState()
    p.setFillColor(colors.HexColor("#6a11cb"))
    p.rect(0, 20, width, 10, stroke=0, fill=1)
    p.setFillColor(colors.HexColor("#2575fc"))
    p.rect(0, 30, width, 10, stroke=0, fill=1)
    p.restoreState()
    p.setFont(body_font, 9)
    p.drawString(50, 15, f"Report Date: {coa.date_of_report.strftime('%Y-%m-%d %H:%M:%S')}")
    p.drawString(50, 3, f"Verified Hash: {coa.verified_hash}")

    # --- QR Code with halo ---
    if qr_image:
        try:
            halo = Image.new("RGBA", (100,100), (0,0,255,30))
            qr_img = Image.open(qr_image)
            qr_io = BytesIO()
            qr_img.save(qr_io, format="PNG")
            qr_io.seek(0)
            p.drawImage(ImageReader(qr_io), width-120, 40, 80, 80, mask="auto")
        except Exception:
            pass

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer
