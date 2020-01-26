# PaPDF
Python library to create PDF


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
