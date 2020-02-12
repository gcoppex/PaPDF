from PaPDF import PaPDF


def main():
    with PaPDF("test.pdf") as pdf:
        pdf.addText(20, 250, "Embedding an image")
        pdf.addImage("image.jpg", 100, 10, 512, 512)


if __name__ == "__main__":
    main()
