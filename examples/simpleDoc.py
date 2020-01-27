from PaPDF import PaPDF

def main():
    with PaPDF("test.pdf") as pdf:
        pdf.addText(20, 250, "Hello world!")
        pdf.addLine(20, 249, 38.5, 249)
        pdf.addPage()
        pdf.addText(20, 250, "Hello, I am page 2 :-)")


if __name__ == "__main__":
    main()
