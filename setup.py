import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="PaPdf",
    version="1.0.0",
    author="GCoppex",
    author_email="g.coppex@gmail.com",
    description="A python package to create PDF files",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gcoppex/papdf",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.5',
)
