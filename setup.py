import setuptools
from os import path

currDir = path.abspath(path.dirname(__file__))
with open(path.join(currDir, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()



setuptools.setup(
    name="PaPDF",
    version="1.1.0",
    author="GCoppex",
    author_email="g.coppex@gmail.com",
    description="A python package to create PDF files.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gcoppex/PaPDF",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.5',
)
