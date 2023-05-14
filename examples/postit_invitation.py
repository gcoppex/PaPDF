#!/usr/bin/env python3
from PaPDF import PaPDF

def generate_pdf():
    text = """Dear Neighbors,

We are pleased to invite you to the annual
barbecue party.

Please confirm your attendance before
the end of the month.

PaPDF team"""
    with PaPDF("postit_invitation.pdf") as pdf:

        # Import a handwritten font, such as the following:
        # https://www.fontspace.com/dpdorkdiary-font-f19900
        # pdf.addTrueTypeFont("Dpdorkdiary", "Dpdorkdiary-P267.ttf")
        # pdf.setFont("Dpdorkdiary")
        pdf.setFillColor("#0335d0")
        pdf.setFontSize(14);

        markerWidth = 2.5

        pdf.setLineThickness(0.1)
        pdf.addLine(210/2,0, 210/2, markerWidth)
        pdf.addLine(210/2,297-markerWidth, 210/2, 297)

        leftMargin = 10
        topMargin = 25
        height = 100
        for i in range(0, 3):
            h = 290 - i*height
            pdf.addLine(0, h, markerWidth, h)
            pdf.addLine(210-markerWidth, h, 210, h)

            h -= topMargin
            pdf.addPar(leftMargin, h, text)
            pdf.addPar(210/2 + leftMargin, h, text)


if __name__ == "__main__":
    generate_pdf()
