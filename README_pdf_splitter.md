# PDF Splitter

A simple Python utility to split large PDF files into smaller chunks based on file size.

## Features

- Split PDFs by specified file size (default: 390KB)
- Determine optimal page breakpoints to stay under size limit
- Handles PDFs of any size
- Simple command-line interface

## Requirements

- Python 3.6+
- PyPDF2 library

## Installation

1. Clone or download this repository
2. Install the required dependencies:
```bash
pip install -r requirements-pdf-splitter.txt
```

## Usage

### Basic Usage

```bash
python pdf_splitter.py input.pdf
```

This will split `input.pdf` into multiple PDFs, each no larger than 390KB (0.39MB), with filenames like `input_split_part1.pdf`, `input_split_part2.pdf`, etc.

### Advanced Options

```bash
python pdf_splitter.py input.pdf --max-size 1.5 --output-prefix my_split_pdf
```

This will:
- Split `input.pdf` into multiple PDFs
- Each output PDF will be at most 1.5MB in size
- Output files will be named `my_split_pdf_part1.pdf`, `my_split_pdf_part2.pdf`, etc.

### Command Line Arguments

- `input_pdf`: Path to the input PDF file (required)
- `--max-size`: Maximum size of each output PDF in megabytes (default: 0.39)
- `--output-prefix`: Prefix for output PDF files (default: input_filename_split)

## How It Works

The script uses PyPDF2 to read and write PDF files. It iteratively determines how many pages can fit within the specified size limit, creating new PDF files as needed. The algorithm adaptively adjusts the number of pages per file to stay under the size limit while maximizing the use of available space.

## Limitations

- The splitter works at the page level - it cannot split individual pages
- Very large individual pages might exceed the specified size limit
- Some PDF features like links between pages might not work across split files

## License

MIT