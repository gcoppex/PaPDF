import setuptools

long_description = "# PaPDF" \
 + "Python library to create PDF" \
 + "## Features:" \
 + " - Basic page addition (with support of multiple formats)" \
 + " - Basic text writing" \
 + " - TrueType font embedding (including propper font subsetting)" \
 + " - EAN13 barcode insertion "


setuptools.setup(
    name="PaPdf",
    version="1.0.3",
    author="GCoppex",
    author_email="g.coppex@gmail.com",
    description="A python package to create PDF files.\nThe package" \
        + "supports basic text edition, font embedding (TrueType) and EAN13 " \
        + "barcode generation. Checkout https://github.com/gcoppex/PaPDF.",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url="https://github.com/gcoppex/PaPDF",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.5',
)
