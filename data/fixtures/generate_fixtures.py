"""
Generate the demo PDFs used by the golden demo and the test suite.

These are SYNTHETIC SPECIMENS written for testing. Every page carries a
footer saying so, so no generated file can be mistaken for a genuine trade
or government document.

The set deliberately includes the golden-demo contradiction:

    invoice_500.pdf        Commercial Invoice   Quantity: 500 units
    packing_list_450.pdf   Packing List         Quantity: 450 units   <- mismatch
    packing_list_500.pdf   Packing List         Quantity: 500 units   <- the fix

Run (only needed if you change the content):

    .venv\\Scripts\\python.exe data/fixtures/generate_fixtures.py

fpdf2 is a development-only dependency. The application itself never
generates PDFs.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

HERE = Path(__file__).resolve().parent

SPECIMEN_NOTICE = "SPECIMEN - SYNTHETIC TEST FIXTURE - NOT A GENUINE DOCUMENT"

EXPORTER = "Sialkot Leather Crafts (Pvt) Ltd"
EXPORTER_ADDRESS = "Plot 14, Small Industrial Estate, Sialkot, Punjab, Pakistan"
CONSIGNEE = "Hoffmann Lederwaren GmbH"
CONSIGNEE_ADDRESS = "Gerberstrasse 22, 60313 Frankfurt am Main, Germany"
GOODS = "Full-grain leather shoulder bags, article LB-220"
INVOICE_NO = "INV-2026-0412"


def build(filename: str, title: str, rows: list[tuple[str, str]]) -> Path:
    """Write a single-page document of label/value rows."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=10)
    for label, value in rows:
        if not label and not value:
            pdf.ln(3)
            continue
        pdf.cell(0, 7, f"{label}: {value}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 6, SPECIMEN_NOTICE, new_x="LMARGIN", new_y="NEXT")

    path = HERE / filename
    pdf.output(str(path))
    return path


def commercial_invoice() -> Path:
    return build(
        "invoice_500.pdf",
        "COMMERCIAL INVOICE",
        [
            ("Invoice No", INVOICE_NO),
            ("Invoice Date", "2026-09-02"),
            ("", ""),
            ("Exporter", EXPORTER),
            ("Exporter Address", EXPORTER_ADDRESS),
            ("NTN", "3520212345678"),
            ("", ""),
            ("Consignee", CONSIGNEE),
            ("Consignee Address", CONSIGNEE_ADDRESS),
            ("", ""),
            ("Description of Goods", GOODS),
            ("HS Code", "4202.21"),
            ("Country of Origin", "Pakistan"),
            ("Quantity", "500 units"),
            ("Unit Price", "EUR 49.00"),
            ("Total Value", "EUR 24500.00"),
            ("Incoterm", "FOB Karachi"),
        ],
    )


def packing_list(quantity: int, filename: str) -> Path:
    """The 450 version carries the golden demo's deliberate contradiction."""
    return build(
        filename,
        "PACKING LIST",
        [
            ("Packing List No", "PL-2026-0412"),
            ("Date", "2026-09-02"),
            ("Invoice No", INVOICE_NO),
            ("", ""),
            ("Exporter", EXPORTER),
            ("Consignee", CONSIGNEE),
            ("", ""),
            ("Description of Goods", GOODS),
            ("Country of Origin", "Pakistan"),
            ("Quantity", f"{quantity} units"),
            ("Number of Packages", "18 cartons"),
            ("Gross Weight", "612.5 kg"),
            ("Net Weight", "540.0 kg"),
        ],
    )


def certificate_of_origin() -> Path:
    return build(
        "certificate_of_origin.pdf",
        "CERTIFICATE OF ORIGIN",
        [
            ("Certificate No", "CO-PK-2026-8841"),
            ("Issue Date", "2026-09-03"),
            ("Issuing Authority", "Sialkot Chamber of Commerce and Industry"),
            ("", ""),
            ("Exporter", EXPORTER),
            ("Consignee", CONSIGNEE),
            ("", ""),
            ("Description of Goods", GOODS),
            ("Country of Origin", "Pakistan"),
            ("Quantity", "500 units"),
            ("Invoice No", INVOICE_NO),
        ],
    )


def unknown_document() -> Path:
    """A valid PDF that is none of the three supported types."""
    return build(
        "unknown_document.pdf",
        "DELIVERY NOTE",
        [
            ("Reference", "DN-2026-0091"),
            ("Carrier", "Karachi Freight Services"),
            ("Collected From", "Sialkot"),
            ("Remarks", "Driver to confirm collection time on arrival."),
        ],
    )


def no_text_layer() -> Path:
    """A structurally valid PDF with no extractable text.

    This is what a scanned or photographed document looks like to a text
    extractor, and it is how we test the unreadable path without needing a
    real scan.
    """
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_fill_color(235, 235, 235)
    pdf.rect(20, 20, 170, 120, style="F")  # a grey block, no glyphs
    path = HERE / "scanned_no_text.pdf"
    pdf.output(str(path))
    return path


def main() -> None:
    written = [
        commercial_invoice(),
        packing_list(450, "packing_list_450.pdf"),
        packing_list(500, "packing_list_500.pdf"),
        certificate_of_origin(),
        unknown_document(),
        no_text_layer(),
    ]
    for path in written:
        print(f"{path.name:<28} {path.stat().st_size:>7,} bytes")


if __name__ == "__main__":
    main()
