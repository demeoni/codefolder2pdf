"""
PDF Splitter Script

This script splits a large PDF file into smaller chunks based on file size.
It uses PyPDF2 to handle PDF operations without redoing the heavy work of code collection.

Usage:
    python pdf_splitter.py input.pdf --max-size 0.39 --output-prefix split_pdf
"""

import os
import sys
import argparse
import logging
from PyPDF2 import PdfReader, PdfWriter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_pdf_size(pdf_path):
    """Get the size of a PDF file in megabytes."""
    return os.path.getsize(pdf_path) / (1024 * 1024)  # Convert bytes to MB

def split_pdf(input_path, max_size_mb=0.39, output_prefix=None):
    """
    Split a PDF file into multiple smaller PDFs based on file size.

    Args:
        input_path (str): Path to the input PDF file
        max_size_mb (float): Maximum size of each output PDF in megabytes
        output_prefix (str, optional): Prefix for output PDF files

    Returns:
        list: Paths to the generated PDF files
    """
    if not os.path.exists(input_path):
        logger.error(f"Input file does not exist: {input_path}")
        return []

    # Determine output prefix
    if output_prefix is None:
        base_name, ext = os.path.splitext(input_path)
        output_prefix = f"{base_name}_split"

    # Read input PDF
    try:
        reader = PdfReader(input_path)
    except Exception as e:
        logger.error(f"Error reading PDF file: {str(e)}")
        return []

    total_pages = len(reader.pages)
    logger.info(f"Splitting PDF with {total_pages} pages")

    current_part = 1
    start_page = 0
    output_files = []

    while start_page < total_pages:
        # Estimate how many pages to include in this part
        # Start with 10 pages and adjust based on actual size
        end_page = min(start_page + 10, total_pages)

        # Create a new PDF writer
        writer = PdfWriter()

        # Add pages to the writer
        for i in range(start_page, end_page):
            writer.add_page(reader.pages[i])

        # Create temporary output file
        temp_output = f"{output_prefix}_temp.pdf"
        with open(temp_output, "wb") as output_file:
            writer.write(output_file)

        # Check the size of the temporary file
        temp_size = get_pdf_size(temp_output)

        # If the size is less than max_size_mb and we haven't reached the end,
        # try adding more pages
        while temp_size < max_size_mb and end_page < total_pages:
            # Add 5 more pages or as many as available
            next_end = min(end_page + 5, total_pages)

            # Create a new writer with all current pages plus the new ones
            new_writer = PdfWriter()

            # Re-add all the existing pages
            for i in range(start_page, end_page):
                new_writer.add_page(reader.pages[i])

            # Add the new pages
            for i in range(end_page, next_end):
                new_writer.add_page(reader.pages[i])

            # Write to the temporary file
            with open(temp_output, "wb") as output_file:
                new_writer.write(output_file)

            # Update the end page and check size again
            end_page = next_end
            temp_size = get_pdf_size(temp_output)

        # If the temporary file is too big, go back 5 pages and try again
        while temp_size > max_size_mb and end_page > start_page + 5:
            end_page -= 5

            # Create a new writer with fewer pages
            new_writer = PdfWriter()

            # Add the reduced set of pages
            for i in range(start_page, end_page):
                new_writer.add_page(reader.pages[i])

            # Write to the temporary file
            with open(temp_output, "wb") as output_file:
                new_writer.write(output_file)

            # Check size again
            temp_size = get_pdf_size(temp_output)

        # Rename the temporary file to the final output file
        output_file = f"{output_prefix}_part{current_part}.pdf"
        os.rename(temp_output, output_file)
        output_files.append(output_file)

        logger.info(f"Created part {current_part}: {output_file} with pages {start_page+1}-{end_page} ({temp_size:.2f} MB)")

        # Move to the next part
        start_page = end_page
        current_part += 1

    logger.info(f"PDF splitting complete. Created {len(output_files)} parts.")
    return output_files

def main():
    parser = argparse.ArgumentParser(description="Split a large PDF file into smaller chunks based on file size.")
    parser.add_argument("input_pdf", help="Path to the input PDF file")
    parser.add_argument("--max-size", type=float, default=0.39, help="Maximum size of each output PDF in megabytes (default: 0.39)")
    parser.add_argument("--output-prefix", help="Prefix for output PDF files (default: input_filename_split)")

    args = parser.parse_args()

    # Call the split_pdf function with command line arguments
    output_files = split_pdf(args.input_pdf, args.max_size, args.output_prefix)

    # Print summary
    if output_files:
        print(f"\nSplit complete! Generated {len(output_files)} PDF files:")
        for output_file in output_files:
            size_mb = get_pdf_size(output_file)
            print(f"  - {output_file} ({size_mb:.2f} MB)")
    else:
        print("Failed to split the PDF file. Check the logs for details.")

if __name__ == "__main__":
    main()