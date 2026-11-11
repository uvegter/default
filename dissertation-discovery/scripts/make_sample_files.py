"""Regenerate the binary sample uploads in sample_data/ (fictional content).

    python scripts/make_sample_files.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample_data"

PDF_PAGES = [
    ["Northfield University (fictional sample) - Module specification", "",
     "ECON2140 Economics of Development", "Credits: 20", "Level: Year 2", "",
     "Module content",
     "Week 1: Poverty and inequality - measurement; poverty traps",
     "Week 2: Institutions and development - property rights; corruption; colonial legacies",
     "Week 3: Microfinance and cash transfers - evidence from randomised controlled trials",
     "Week 4: Structural transformation - the Lewis model; agricultural markets",
     "Week 5: Trade and development - commodity dependence", "",
     "Learning outcomes",
     "- Evaluate evidence from field experiments on anti-poverty programmes",
     "- Use cross-country panel data to describe development patterns", "",
     "Assessment", "Essay (40%) and examination (60%)"],
    ["ECON3110 Applied Econometrics", "Credits: 20", "Level: Year 3", "",
     "Module content",
     "Topic 1: Panel data methods - fixed effects; random effects",
     "Topic 2: Instrumental variables and endogeneity",
     "Topic 3: Difference-in-differences and regression discontinuity",
     "Topic 4: Time series - unit roots; cointegration; vector autoregression", "",
     "Methods and skills", "Students complete an empirical project in Stata or R using regression analysis."],
]


def make_pdf() -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(OUT / "sample_module_specs.pdf"), pagesize=A4)
    for lines in PDF_PAGES:
        y = 800
        for line in lines:
            c.setFont("Helvetica-Bold" if line[:4] == "ECON" else "Helvetica", 11)
            c.drawString(50, y, line)
            y -= 17
        c.showPage()
    c.save()


def make_scanned_pdf() -> None:
    """A PDF with pages but no text layer, to try the 'scanned document' message."""
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    with open(OUT / "sample_scanned_no_text.pdf", "wb") as fh:
        w.write(fh)


def make_docx() -> None:
    import docx

    d = docx.Document()
    d.add_heading("ECON2170 International Trade", level=1)
    table = d.add_table(rows=3, cols=2)
    for row, (k, v) in zip(table.rows, [("Credits", "10"), ("Level", "Year 2"), ("Module leader", "Dr B. Sample")]):
        row.cells[0].text, row.cells[1].text = k, v
    d.add_heading("Module content", level=2)
    for line in ["Comparative advantage: the Ricardian model; Heckscher-Ohlin",
                 "Trade policy: tariffs; trade agreements; protectionism",
                 "The gravity model of trade",
                 "Import competition and local labour markets",
                 "Global value chains and supply chains"]:
        d.add_paragraph(line, style="List Bullet")
    d.add_heading("Learning outcomes", level=2)
    d.add_paragraph("Apply regression analysis to bilateral trade data", style="List Bullet")
    d.add_heading("Assessment", level=2)
    d.add_paragraph("Data exercise (30%) and examination (70%)")
    d.save(str(OUT / "sample_module_spec.docx"))


if __name__ == "__main__":
    make_pdf()
    make_scanned_pdf()
    make_docx()
    print("wrote sample files to", OUT)
