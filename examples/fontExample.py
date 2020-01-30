from PaPDF import PaPDF

def main():
    with PaPDF("fontExample.pdf") as pdf:
        pdf.addText(20, 250, "Font selection example (Helvetica)")
        pdf.addTrueTypeFont("SourceSansPro-Regular", "SourceSansPro-Regular.ttf")
        pdf.setFont("SourceSansPro-Regular")
        pdf.addText(20, 240, "This text is printed in Source Sans Pro.")

# Note that Source Sans Pro font is distibuted under the SIL Open Font License,
# Version 1.1. The license is not copied below, but is available with a FAQ at:
# http://scripts.sil.org/OFL

# https://github.com/adobe-fonts/source-sans-pro
if __name__ == "__main__":
    main()
