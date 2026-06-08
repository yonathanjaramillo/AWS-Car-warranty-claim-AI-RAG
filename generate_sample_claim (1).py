"""
Generate a realistic mock warranty claim PDF for testing.
Run this script once to create data/mock/sample_claim.pdf
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "mock", "sample_claim.pdf")

def generate():
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    doc = SimpleDocTemplate(OUTPUT, pagesize=letter,
        leftMargin=0.75*inch, rightMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch)

    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph("<b>WARRANTY CLAIM FORM</b>", ParagraphStyle(
        "hdr", fontName="Helvetica-Bold", fontSize=18,
        spaceAfter=4, alignment=1)))
    story.append(Paragraph("Ford Motor Company — Dealer Warranty Submission", ParagraphStyle(
        "sub", fontName="Helvetica", fontSize=11,
        spaceAfter=20, alignment=1, textColor=colors.HexColor("#444"))))

    # Claim info
    claim_data = [
        ["CLAIM INFORMATION", ""],
        ["Claim Number:", "WC-2024-08847"],
        ["Claim Date:", "06/08/2024"],
        ["Dealer Code:", "FORD-MIA-0042"],
        ["Dealer Name:", "Miami Auto Group Ford"],
        ["RO Number:", "RO-2024-15523"],
    ]
    t1 = Table(claim_data, colWidths=[2.5*inch, 4*inch])
    t1.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0C2340")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("SPAN",(0,0),(-1,0)),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",(0,0),(-1,-1),10),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#CCCCCC")),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story.append(t1)
    story.append(Spacer(1, 16))

    # Vehicle info
    vehicle_data = [
        ["VEHICLE INFORMATION", ""],
        ["VIN:", "1FTFW1ET5DKE12345"],
        ["Year / Make / Model:", "2013 Ford F-150 XLT"],
        ["Mileage:", "34,218"],
        ["In-Service Date:", "03/15/2013"],
        ["Warranty Expiry:", "03/15/2016"],
    ]
    t2 = Table(vehicle_data, colWidths=[2.5*inch, 4*inch])
    t2.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#185FA5")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("SPAN",(0,0),(-1,0)),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",(0,0),(-1,-1),10),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#CCCCCC")),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story.append(t2)
    story.append(Spacer(1, 16))

    # Repair info
    repair_data = [
        ["REPAIR INFORMATION", "", ""],
        ["Repair Date:", "03/15/2024", ""],
        ["Labor Op Code:", "06-10B", "Engine Oil & Filter Change"],
        ["Part Number:", "FL3Z-6600-B", "Engine Oil Filter"],
        ["Technician ID:", "TECH-4821", ""],
    ]
    t3 = Table(repair_data, colWidths=[2.5*inch, 1.5*inch, 2.5*inch])
    t3.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0F6E56")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("SPAN",(0,0),(-1,0)),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",(0,0),(-1,-1),10),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#CCCCCC")),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story.append(t3)
    story.append(Spacer(1, 16))

    # Financial summary
    financial_data = [
        ["CLAIM AMOUNT SUMMARY", ""],
        ["Labor Amount:", "$312.00"],
        ["Parts Amount:", "$535.50"],
        ["Total Claim Amount:", "$847.50"],
    ]
    t4 = Table(financial_data, colWidths=[2.5*inch, 4*inch])
    t4.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#854F0B")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("SPAN",(0,0),(-1,0)),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
        ("FONTSIZE",(0,0),(-1,-1),10),
        ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#CCCCCC")),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
    ]))
    story.append(t4)
    story.append(Spacer(1, 20))

    story.append(Paragraph(
        "I certify that the above warranty claim is accurate and that the repair was performed "
        "in accordance with Ford Motor Company warranty policies and procedures.",
        ParagraphStyle("cert", fontName="Helvetica-Oblique", fontSize=9,
                      textColor=colors.HexColor("#666"))))

    doc.build(story)
    print(f"Sample claim PDF generated: {OUTPUT}")

if __name__ == "__main__":
    generate()
