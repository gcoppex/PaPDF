# PaPDF
Python library to create PDF

## Features:
 - Basic text writing with TrueType font embedding (including propper font subsetting)
 - Image insertion (JPEG images and PNG with transparency images support)
 - EAN13 barcode insertion

## Installation:
Use `pip3`for the installation of `PaPDF`:
```bash
pip3 install PaPDF
```
## Simple usage example:

The following snippet will create a pdf (`test.pdf`) with two pages and two
texts.

```python
import PaPDF
with PaPDF("test.pdf") as pdf:
    pdf.addText(40, 290, "Hello world")
    pdf.addPage()
    pdf.addText(40, 10, 'Hello world')
```


### TrueType font embedding:
More advanced example with the usage of a (subsetted) TrueType font. Basically
the same example as above but with a custom font, loaded from a font file.
```python
import PaPDF
with PaPDF("test.pdf") as pdf:
    pdf.addTrueTypeFont("<FontUserName>", "/path/to/font.ttf")
    pdf.currentFontName = "<FontUserName>"
    pdf.addText(40, 290, "Hello world")
    pdf.addPage()
    pdf.addText(40, 10, 'Hello world')
```

### Adding EAN13 Barcode:
Adding a barcode is pretty straight forward. Warning: make sure the last digit checksum is correctly computed, when calling the `addEAN13()` function.
```python
import PaPDF
with PaPDF("barcode.pdf") as pdf:
    pdf.addText(20, 250, "Simple EAN13 barcode example:")
    pdf.addEAN13(20, 225, "4012345123456")
```
![Generated barcode example](https://raw.githubusercontent.com/gcoppex/PaPDF/master/examples/barcode.png)
