from PaPDF import PaPDF


def main():
    with PaPDF("test.pdf") as pdf:
        pdf.addText(20, 250, "Embedding two images (transparent-PNG and JPG images):")
        pdf.addImage("lena.jpg", 10, 10, 100, 100)
        pdf.addImage("dices.png", 10, 125, 100, 100)

if __name__ == "__main__":
    main()
