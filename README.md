# PaPDF
Python library to create PDF

## Features:
 - Basic page addition (with support of multiple formats)
 - Basic text writing
 - TrueType font embedding (including propper font subsetting)

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
