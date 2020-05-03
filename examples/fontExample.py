from PaPDF import PaPDF

def main():
    with PaPDF("fontExample.pdf") as pdf:
        pdf.addText(20, 250, "Font selection example (Helvetica)")
        pdf.addTrueTypeFont("SourceSansPro-Regular", "SourceSansPro-Regular.ttf")
        pdf.setFont("SourceSansPro-Regular")
        pdf.setLineThickness(0.5)

        text = "This text is printed in Source Sans Pro."
        pdf.addText(20, 240, text)

        text = "Foo bar short text"
        pdf.addText(20, 200, text)
        w = pdf.getTextWidth(text)
        pdf.addLine(20, 198.5, 20+w, 198.5)

        pdf.setFontSize(6);
        text = "Lorem ipsum dolor sit amet, consectetur adipisicing eli adipisicing elit, sed do eiusmod tempor incididunt."
        pdf.addText(20, 160, text)
        w = pdf.getTextWidth(text)
        pdf.addLine(20, 158.5, 20+w, 158.5)

        pdf.setFontSize(6);
        pdf.setFont("Helvetica")
        text = "Helvetica: Lorem ipsum dolor sit amet, consectetur adipisicing eli adipisicing elit, sed do eiusmod tempor incididunt."
        w = pdf.getTextWidth(text)
        pdf.addText(20, 140, text)
        pdf.addLine(20, 138.5, 20+w, 138.5)

        text = "Other Helvetica displayed text with automatic break line"
        pdf.setFontSize(14);
        pdf.addText(20, 100, text, 50)

# Note that Source Sans Pro font is distibuted under the SIL Open Font License,
# Version 1.1. The license is not copied below, but is available with a FAQ at:
# http://scripts.sil.org/OFL

# https://github.com/adobe-fonts/source-sans-pro
if __name__ == "__main__":
    main()
