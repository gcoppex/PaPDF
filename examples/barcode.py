from PaPDF import PaPDF

def main():
    with PaPDF("barcode.pdf") as pdf:
        pdf.addText(20, 250, "Simple EAN13 barcode example:")
        pdf.addEAN13(20, 225, "4012345123456")


if __name__ == "__main__":
    main()
