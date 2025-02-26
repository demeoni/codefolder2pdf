import os
import argparse
import tempfile
import shutil
import logging
import threading
import queue
import json
import time
from datetime import datetime  # Single import for datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.units import inch
from flask import Flask, render_template, request, send_file, redirect, url_for, Response, jsonify, session
from werkzeug.utils import secure_filename

# Add this global variable to track all log messages
all_log_messages = []

# List of common code file extensions to include
CODE_EXTENSIONS = [
    '.py', '.java', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass',
    '.c', '.cpp', '.cs', '.h', '.hpp', '.go', '.rs', '.rb', '.php', '.swift',
    '.scala', '.groovy', '.pl', '.sh', '.bat', '.ps1', '.sql', '.r',
    '.dart', '.lua', '.clj', '.ex', '.exs', '.erl', '.fs', '.f90', '.ml',
    '.hs', '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.md', '.jsx',
    '.vue', '.svelte', '.elm'
]

# Files to exclude (typically build related files)
EXCLUDED_FILE_EXTENSIONS = [
    '.kt', '.kts', '.jar', '.properties',
    '.pbxproj', '.xcconfig', '.xcworkspacedata', '.xcscheme',
    '.plist', '.jks', '.keystore', '.apk', '.ipa',
    '.so', '.a', '.dylib', '.framework',
    '.class', '.dex', '.o', '.d',
    '.iml', '.gradle', '.lock', '.bin',
]

# Directories to commonly exclude
COMMON_EXCLUDED_DIRS = [
    '.git', 'node_modules', '__pycache__', 'venv', 'env', '.venv', '.env', 'dist', 'build', 'obj', 'bin',
    '__MACOSX', '.trash', '.expo', '.gradle', 'gradle' 'Images.xcassets', 'android/app/src', 'Local Podspecs',
    'libs', 'jniLibs', 'intermediates', 'generated', 'outputs', 'tmp', 'temp', 'captures',
    'release', 'debug', 'caches', 'xcuserdata', 'xcshareddata', 'DerivedData',
    'Classes', 'Frameworks', 'Headers', 'PrivateHeaders', 'buildSrc', 'log', 'logs'

    # Add these additional directories that are typically very large
    'node_modules',  # Explicitly add again to ensure it's included
    '.next',         # Next.js build folder
    'vendor',        # PHP/Ruby vendor folder
    'bower_components', # Bower components
    '.nuxt',         # Nuxt.js build folder
    '.cache',        # Various cache folders
    'coverage',      # Test coverage reports
    'public/build',  # Public build folders
    'public/dist',   # Public dist folders
]

# Specific files to exclude by exact filename
EXCLUDED_FILES = [
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    'composer.lock',
    'Gemfile.lock',
    'poetry.lock',
    'Cargo.lock',
    'go.sum',
    '.DS_Store',
    'thumbs.db',
    'ehthumbs.db',
    'desktop.ini',
    '.gitkeep',
    '.gitattributes',
    '.gitignore',
    '.npmignore',
    '.env.local',
    '.env.development',
    '.env.test',
    '.env.production',
    '.eslintcache',
    '.eslintignore',
    'tsconfig.tsbuildinfo',
    'junit.xml',
    'coverage.xml',
    '.coverage',
    'coverage-final.json',
    'debug.log',
    'npm-debug.log',
    'yarn-debug.log',
    'yarn-error.log',
    'pnpm-debug.log',
    'report.*.json',
    'stats.json',
    'gradlew.bat',
    'AppDelegate.h',
    'Podfile.properties.json'
]

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a queue for progress updates
progress_queue = queue.Queue()

# Global variable to store current task ID
current_task_id = None


def get_folder_structure(path, level=0, prefix_map=None, excluded_dirs=None, include_files=True):
    """
    Generate a text representation of the folder structure with explicit tree formatting.
    Uses a completely different approach with explicit indentation and ASCII characters.
    """
    if excluded_dirs is None:
        excluded_dirs = COMMON_EXCLUDED_DIRS

    if prefix_map is None:
        prefix_map = []

    # Skip excluded directories
    basename = os.path.basename(path)
    if basename in excluded_dirs:
        return ""

    # Build current line indentation based on prefix_map
    indent = ""
    for i in range(len(prefix_map)):
        indent += "    " if not prefix_map[i] else "|   "

    # Add the appropriate connector for this level
    if level > 0:
        connector = "+-- "
    else:
        connector = ""

    # Create the current line with proper indentation and connector
    is_dir = os.path.isdir(path)
    line = indent + connector + basename + ("/" if is_dir else "") + "\n"

    # Return just this line if it's a file or we can't access directory contents
    if not is_dir:
        return line

    # Process the directory contents
    try:
        items = sorted([os.path.join(path, item) for item in os.listdir(path)],
                      key=lambda x: (not os.path.isdir(x), x.lower()))

        # Filter items
        items = [item for item in items if os.path.isdir(item) or include_files]
        items = [item for item in items if os.path.basename(item) not in excluded_dirs]
        items = [item for item in items if not os.path.basename(item).startswith('._')]

        # Process each item
        for i, item in enumerate(items):
            # Update prefix map for the next level
            is_last = (i == len(items) - 1)
            new_prefix_map = prefix_map + [not is_last]

            # Add this item to the output
            line += get_folder_structure(item, level+1, new_prefix_map, excluded_dirs, include_files)

        return line

    except (PermissionError, OSError):
        return line + indent + "    (Access error)\n"

def generate_improved_structure_pdf(output_path, root_path, excluded_dirs=None, pdf_title=None, machine_format=False):
    """Generate a PDF with explicit tree visualization."""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch

    if excluded_dirs is None:
        excluded_dirs = COMMON_EXCLUDED_DIRS

    # Common elements for all PDFs
    styles = getSampleStyleTools(machine_format=machine_format)

    # Create a custom monospaced style for tree structure
    tree_style = styles['Code']
    tree_style.fontName = 'Courier'  # Ensure monospace font
    tree_style.fontSize = 3 if machine_format else 8  # Use smaller font for machine format

    # Prepare document elements
    elements = []

    # Add title
    if pdf_title:
        title = pdf_title
    else:
        title = f"Code Collection: {os.path.basename(root_path)}"

    elements.append(Paragraph(title, styles['Title']))

    # Add format indicator
    if machine_format:
        elements.append(Paragraph("Machine-Readable Format (Compact Size)", styles['Normal']))
    else:
        elements.append(Paragraph("Human-Readable Format (Standard Size)", styles['Normal']))

    # Add generation timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph(f"Generated on: {timestamp}", styles['Normal']))

    # Add structure heading
    elements.append(Paragraph("Project Structure:", styles['Heading2']))

    # Add legend/key for the tree visualization
    elements.append(Paragraph("Key: '+--' indicates a branch, '|' indicates continuation", styles['Normal']))

    # Get the improved folder structure with clear tree visualization
    structure = get_folder_structure(root_path, excluded_dirs=excluded_dirs)

    # Add the structure using Preformatted to preserve spaces and formatting
    elements.append(Preformatted(structure, tree_style))

    # Create the PDF
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.75*inch
    )

    try:
        doc.build(elements)
        logger.info(f"Structure PDF successfully created with tree visualization at {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error building structure PDF: {str(e)}")
        return None

def collect_code_files(root_path, code_extensions=None, excluded_dirs=None, excluded_extensions=None, excluded_files=None, progress_callback=None):
    """Collect all code files in the given directory and its subdirectories with categorization."""
    if code_extensions is None:
        code_extensions = CODE_EXTENSIONS

    if excluded_dirs is None:
        excluded_dirs = COMMON_EXCLUDED_DIRS

    if excluded_extensions is None:
        excluded_extensions = EXCLUDED_FILE_EXTENSIONS

    if excluded_files is None:
        excluded_files = EXCLUDED_FILES

    # Initialize file collections
    code_files = []
    mobile_files = {
        'ios': [],
        'android': []
    }
    total_files = 0
    processed_files = 0

    # Paths that identify mobile files
    ios_patterns = ['ios/', '.xcodeproj/', '.xcworkspace/', '.pbxproj', '.storyboard', '.xib', '.swift', 'Images.xcassets/', '.h']
    android_patterns = ['android/', 'gradle/', '.gradle', '.xml', 'AndroidManifest.xml', '.properties']

    # First, count total files for progress reporting
    if progress_callback:
        progress_callback(0, "Counting files...", "Scanning directory structure")
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Skip excluded directories with a more robust check
            skip_dir = False
            dir_relative_path = os.path.relpath(dirpath, root_path)

            # Check if this directory or any parent directory should be excluded
            for excluded in excluded_dirs:
                # Check if this directory path contains any excluded directory
                if (excluded in dirpath.split(os.sep) or
                    f"/{excluded}/" in f"/{dir_relative_path}/" or
                    dir_relative_path == excluded or
                    dir_relative_path.startswith(f"{excluded}/")):
                    skip_dir = True
                    progress_callback(None, None, f"Skipping excluded directory: {dirpath}", "info")
                    break

            if skip_dir:
                dirnames[:] = []  # Don't traverse further in excluded directories
                continue

            # Filter dirnames to skip excluded directories
            dirnames[:] = [d for d in dirnames if d not in excluded_dirs]

            for filename in filenames:
                # Skip macOS hidden files (._filename)
                if filename.startswith('._'):
                    continue

                # Skip excluded specific files by name
                if filename in excluded_files:
                    continue

                # Skip excluded file extensions
                if any(filename.endswith(ext) for ext in excluded_extensions):
                    continue

                if any(filename.endswith(ext) for ext in code_extensions):
                    total_files += 1

        if total_files == 0:
            if progress_callback:
                progress_callback(100, "No code files found", "No files to process")
            return {'regular': [], 'ios': [], 'android': []}

    # Then collect the files with the same improved exclusion logic
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Skip excluded directories with more robust check
        skip_dir = False
        dir_relative_path = os.path.relpath(dirpath, root_path)

        # Check if this directory or any parent directory should be excluded
        for excluded in excluded_dirs:
            # Check if this directory path contains any excluded directory
            if (excluded in dirpath.split(os.sep) or
                f"/{excluded}/" in f"/{dir_relative_path}/" or
                dir_relative_path == excluded or
                dir_relative_path.startswith(f"{excluded}/")):
                skip_dir = True
                break

        if skip_dir:
            dirnames[:] = []  # Don't traverse further in excluded directories
            continue

        # Filter dirnames to skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]

        for filename in filenames:
            # Skip macOS hidden files (._filename)
            if filename.startswith('._'):
                continue

            # Skip excluded specific files by name
            if filename in excluded_files:
                if progress_callback:
                    progress_callback(None, None, f"Skipping excluded file: {os.path.join(dir_relative_path, filename)}", "info")
                continue

            # Skip excluded file extensions
            if any(filename.endswith(ext) for ext in excluded_extensions):
                continue

            if any(filename.endswith(ext) for ext in code_extensions):
                filepath = os.path.join(dirpath, filename)
                relative_path = os.path.relpath(filepath, root_path)

                # Categorize the file based on its path
                is_ios = any(pattern in relative_path.replace('\\', '/') for pattern in ios_patterns)
                is_android = any(pattern in relative_path.replace('\\', '/') for pattern in android_patterns)

                if is_ios:
                    mobile_files['ios'].append((relative_path, filepath))
                elif is_android:
                    mobile_files['android'].append((relative_path, filepath))
                else:
                    code_files.append((relative_path, filepath))

                processed_files += 1
                if progress_callback and total_files > 0:
                    progress = int((processed_files / total_files) * 40)  # Use 40% of progress bar for file collection
                    category = "iOS" if is_ios else "Android" if is_android else "Regular"
                    progress_callback(progress, f"Collecting files ({processed_files}/{total_files})",
                                    f"Found [{category}]: {relative_path}")

    # Sort by path for a more organized presentation
    code_files.sort(key=lambda x: x[0].lower())
    mobile_files['ios'].sort(key=lambda x: x[0].lower())
    mobile_files['android'].sort(key=lambda x: x[0].lower())

    if progress_callback:
        ios_count = len(mobile_files['ios'])
        android_count = len(mobile_files['android'])
        regular_count = len(code_files)
        progress_callback(40, "File collection complete",
                         f"Found {regular_count} regular files, {ios_count} iOS files, {android_count} Android files")

    return {
        'regular': code_files,
        'ios': mobile_files['ios'],
        'android': mobile_files['android']
    }

def getSampleStyleTools(machine_format=False):
    """Create and return a dictionary of styles for the PDF with built-in spacing."""
    styles = getSampleStyleSheet()

    # Font size adjustments for machine format
    code_font_size = 3 if machine_format else 8
    heading_font_size = 4 if machine_format else 10
    title_font_size = 6 if machine_format else 16
    normal_font_size = 4 if machine_format else 10

    # Add custom styles with built-in spacing
    if 'Code' not in styles:
        styles.add(ParagraphStyle(
            name='Code',
            fontName='Courier',
            fontSize=code_font_size,
            leading=code_font_size+2,  # Adjusted leading for better readability
            alignment=TA_LEFT,
            spaceAfter=2 if machine_format else 6,
            spaceBefore=1 if machine_format else 3
        ))

    if 'Warning' not in styles:
        styles.add(ParagraphStyle(
            name='Warning',
            parent=styles['Normal'],
            textColor='red',
            spaceBefore=1 if machine_format else 3,
            spaceAfter=1 if machine_format else 3
        ))

    if 'Heading4' not in styles:
        styles.add(ParagraphStyle(
            name='Heading4',
            parent=styles['Heading3'],
            fontSize=heading_font_size,
            leading=heading_font_size+2,
            spaceBefore=3 if machine_format else 8,
            spaceAfter=2 if machine_format else 6
        ))

    # Update existing styles
    styles['Title'].fontSize = title_font_size
    styles['Title'].leading = title_font_size+2
    styles['Title'].spaceBefore = 0
    styles['Title'].spaceAfter = 3 if machine_format else 8

    styles['Heading2'].fontSize = heading_font_size+2 if machine_format else 14
    styles['Heading2'].leading = (heading_font_size+2)+2 if machine_format else 16
    styles['Heading2'].spaceBefore = 3 if machine_format else 8
    styles['Heading2'].spaceAfter = 2 if machine_format else 6

    styles['Heading3'].fontSize = heading_font_size+1 if machine_format else 12
    styles['Heading3'].leading = (heading_font_size+1)+2 if machine_format else 14
    styles['Heading3'].spaceBefore = 2 if machine_format else 7
    styles['Heading3'].spaceAfter = 1 if machine_format else 4

    styles['Normal'].fontSize = normal_font_size
    styles['Normal'].leading = normal_font_size+2
    styles['Normal'].spaceBefore = 1 if machine_format else 4
    styles['Normal'].spaceAfter = 1 if machine_format else 4

    return styles

def generate_pdf(output_path, root_path, code_files, excluded_dirs=None, max_pdf_size_mb=None,
                progress_callback=None, pdf_title=None, include_structure=True, machine_format=False):
    """
    Generate a PDF containing all the code files with their content.
    If max_pdf_size_mb is specified, split into multiple PDFs to keep each under that size.

    Args:
        output_path: Path to save the PDF(s)
        root_path: Root directory of the project
        code_files: Dictionary or list of code files to include
        excluded_dirs: Directories to exclude from the structure
        max_pdf_size_mb: Maximum size for each PDF (if splitting)
        progress_callback: Callback function for progress updates
        pdf_title: Title for the PDF
        include_structure: Whether to include the project structure in each PDF
        machine_format: Whether to use machine-readable (smaller) fonts
    """
    if excluded_dirs is None:
        excluded_dirs = COMMON_EXCLUDED_DIRS

    if progress_callback:
        if machine_format:
            progress_callback(40, "Preparing machine-readable PDF generation", "Setting up document structure with compact fonts")
        else:
            progress_callback(40, "Preparing PDF generation", "Setting up document structure")

    # Common elements for all PDFs
    styles = getSampleStyleTools(machine_format=machine_format)

    # Prepare common header elements - NO SPACERS!
    header_elements = []

    # Add title
    if pdf_title:
        title = pdf_title
    else:
        title = f"Code Collection from {os.path.basename(root_path)}"

    header_elements.append(Paragraph(title, styles['Title']))

    # Add format indicator
    if machine_format:
        header_elements.append(Paragraph("Machine-Readable Format (Compact Size)", styles['Normal']))
    else:
        header_elements.append(Paragraph("Human-Readable Format (Standard Size)", styles['Normal']))

    # Add generation timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_elements.append(Paragraph(f"Generated on: {timestamp}", styles['Normal']))

    # Add folder structure if requested
    if include_structure:
        header_elements.append(Paragraph("Project Structure:", styles['Heading2']))
        structure = get_folder_structure(root_path, excluded_dirs=excluded_dirs)
        header_elements.append(Preformatted(structure, styles['Code']))

    # Check if we should split PDFs
    if max_pdf_size_mb is None or max_pdf_size_mb <= 0:
        # Don't split the PDF, use the single document approach
        return generate_single_document(output_path, header_elements, code_files, styles,
                                       progress_callback, machine_format=machine_format)
    else:
        # Split based on size limit
        return generate_split_documents(output_path, header_elements, code_files, styles,
                                       max_pdf_size_mb, progress_callback, machine_format=machine_format)

def generate_single_document(output_path, header_elements, code_files, styles, progress_callback=None, machine_format=False):
    """Generate a single PDF document without splitting and without spacers."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted, KeepTogether, PageBreak

    if progress_callback:
        if machine_format:
            progress_callback(45, "Creating single machine-readable PDF", "Preparing compact content")
        else:
            progress_callback(45, "Creating single PDF", "Preparing content")

    # Use a slightly larger bottom margin to avoid "flowable too large" errors
    doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=0.5*inch,
                           leftMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.75*inch)

    # Start with header elements
    elements = header_elements.copy()

    # Check if we have categorized files (dictionary) or just a flat list
    if isinstance(code_files, dict):
        # We have categorized files
        regular_files = code_files.get('regular', [])
        ios_files = code_files.get('ios', [])
        android_files = code_files.get('android', [])

        # Process regular files
        if regular_files:
            elements.append(Paragraph("Regular Code Files", styles['Heading2']))
            # NO SPACER HERE

            # Add each file
            for i, (relative_path, filepath) in enumerate(regular_files):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                        content = file.read()

                    # Create a group for this file
                    file_elements = []
                    file_elements.append(Paragraph(relative_path, styles['Heading3']))
                    file_elements.append(Preformatted(content, styles['Code']))

                    # Add the group to the document
                    elements.append(KeepTogether(file_elements))

                    if progress_callback:
                        progress = 45 + int((i / len(regular_files)) * 20)
                        format_type = "compact " if machine_format else ""
                        progress_callback(progress, f"Adding {format_type}regular file {i+1}/{len(regular_files)}",
                                         f"Added: {relative_path}")
                except Exception as e:
                    logger.error(f"Error processing file {relative_path}: {str(e)}")
                    elements.append(Paragraph(f"Error processing file: {str(e)}", styles['Warning']))

        # Process iOS files
        if ios_files:
            # Add a page break before iOS section
            elements.append(PageBreak())
            elements.append(Paragraph("iOS Code Files", styles['Heading2']))

            # Add each file
            for i, (relative_path, filepath) in enumerate(ios_files):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                        content = file.read()

                    # Create a group for this file
                    file_elements = []
                    file_elements.append(Paragraph(relative_path, styles['Heading3']))
                    file_elements.append(Preformatted(content, styles['Code']))

                    # Add the group to the document
                    elements.append(KeepTogether(file_elements))

                    if progress_callback:
                        progress = 65 + int((i / len(ios_files)) * 15)
                        progress_callback(progress, f"Adding iOS file {i+1}/{len(ios_files)}",
                                         f"Added: {relative_path}")
                except Exception as e:
                    logger.error(f"Error processing file {relative_path}: {str(e)}")
                    elements.append(Paragraph(f"Error processing file: {str(e)}", styles['Warning']))

        # Process Android files
        if android_files:
            # Add a page break before Android section
            elements.append(PageBreak())
            elements.append(Paragraph("Android Code Files", styles['Heading2']))

            # Add each file
            for i, (relative_path, filepath) in enumerate(android_files):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                        content = file.read()

                    # Create a group for this file
                    file_elements = []
                    file_elements.append(Paragraph(relative_path, styles['Heading3']))
                    file_elements.append(Preformatted(content, styles['Code']))

                    # Add the group to the document
                    elements.append(KeepTogether(file_elements))

                    if progress_callback:
                        progress = 80 + int((i / len(android_files)) * 10)
                        progress_callback(progress, f"Adding Android file {i+1}/{len(android_files)}",
                                         f"Added: {relative_path}")
                except Exception as e:
                    logger.error(f"Error processing file {relative_path}: {str(e)}")
                    elements.append(Paragraph(f"Error processing file: {str(e)}", styles['Warning']))
    else:
        # Legacy support for flat list of files
        elements.append(Paragraph("Code Files:", styles['Heading2']))

        # Add each file
        for i, (relative_path, filepath) in enumerate(code_files):
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                    content = file.read()

                # Create a group for this file
                file_elements = []
                file_elements.append(Paragraph(relative_path, styles['Heading3']))
                file_elements.append(Preformatted(content, styles['Code']))

                # Add the group to the document
                elements.append(KeepTogether(file_elements))

                if progress_callback:
                    progress = 45 + int((i / len(code_files)) * 45)
                    progress_callback(progress, f"Adding file {i+1}/{len(code_files)}",
                                     f"Added: {relative_path}")
            except Exception as e:
                logger.error(f"Error processing file {relative_path}: {str(e)}")
                elements.append(Paragraph(f"Error processing file: {str(e)}", styles['Warning']))

    # Build the PDF with a try/except block to handle any remaining issues
    if progress_callback:
        if machine_format:
            progress_callback(90, "Generating compact PDF", "Creating final document with 3px fonts")
        else:
            progress_callback(90, "Generating PDF", "Creating final document")

    try:
        doc.build(elements)

        if machine_format:
            logger.info(f"Machine-readable PDF generated successfully at {output_path}")
        else:
            logger.info(f"Human-readable PDF generated successfully at {output_path}")

        if progress_callback:
            format_type = "Machine-readable" if machine_format else "Human-readable"
            progress_callback(100, f"{format_type} PDF generated successfully",
                             f"Output saved to: {os.path.basename(output_path)}")

        return output_path
    except Exception as e:
        logger.error(f"Error building PDF: {str(e)}")

        if progress_callback:
            progress_callback(None, None, f"Error generating PDF: {str(e)}", "error")
            progress_callback(100, "PDF generation failed", "Try using the external PDF splitter tool", complete=True)

        # Return the path anyway, even though the generation failed
        return output_path

def _generate_split_pdfs(output_path, header_elements, code_files, styles, max_pdf_size_mb, progress_callback=None):
    """Generate multiple PDFs, each under the specified size limit."""
    from reportlab.platypus import PageBreak, KeepTogether
    from reportlab.lib.styles import ParagraphStyle
    import os.path

    if progress_callback:
        progress_callback(45, "Preparing split PDFs", "Calculating file sizes")

    # Convert MB to bytes for comparison
    max_size_bytes = max_pdf_size_mb * 1024 * 1024

    # Create a modified Code style with less spacing
    compact_code_style = ParagraphStyle(
        name='CompactCode',
        fontName='Courier',
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        spaceAfter=5  # Reduced from 10
    )

    # Prepare output paths
    base_name, ext = os.path.splitext(output_path)
    output_files = []

    # Initialize first PDF
    current_part = 1
    current_output = f"{base_name}_part{current_part}{ext}"
    doc = SimpleDocTemplate(current_output, pagesize=letter, rightMargin=0.5*inch,
                           leftMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)

    # Start with header elements
    current_elements = header_elements.copy()

    # Add code files header
    current_elements.append(Paragraph("Code Files:", styles['Heading2']))
    # No spacer here - let the natural paragraph spacing handle it

    # Add part information
    current_elements.append(Paragraph(f"Part {current_part}", styles['Heading3']))
    # No spacer here - let the natural paragraph spacing handle it

    # Initialize file size estimation (header elements typically don't exceed 1MB)
    estimated_size = 1 * 1024 * 1024  # Start with 1MB for headers

    # Process all code files
    total_files = len(code_files)
    for i, (relative_path, filepath) in enumerate(code_files):
        try:
            # Try to read the file content
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                    content = file.read()
            except UnicodeDecodeError:
                # For binary files or files with encoding issues
                content = "[Binary file or encoding error - content not displayed]"
            except Exception as e:
                content = f"[Error reading file: {str(e)}]"

            # Estimate size contribution of this file
            # Rough estimate: assume each character takes about 2 bytes in the PDF
            file_contribution = len(content) * 2 + 5000  # 5KB overhead for headings

            # Check if adding this file would exceed the limit and we already have content
            if estimated_size + file_contribution > max_size_bytes and len(current_elements) > len(header_elements) + 2:
                # Build current PDF
                if progress_callback:
                    progress_callback(45 + int((i / total_files) * 45),
                                    f"Creating PDF part {current_part}",
                                    f"Finalizing part {current_part}")

                try:
                    doc.build(current_elements)
                    output_files.append(current_output)
                    logger.info(f"Generated PDF part {current_part} at {current_output}")

                    if progress_callback:
                        progress_callback(None, None, f"Generated: {os.path.basename(current_output)}")
                except Exception as e:
                    logger.error(f"Error building PDF part {current_part}: {str(e)}")
                    if progress_callback:
                        progress_callback(None, None, f"Error generating PDF part {current_part}: {str(e)}", "error")

                # Start new PDF
                current_part += 1
                current_output = f"{base_name}_part{current_part}{ext}"
                doc = SimpleDocTemplate(current_output, pagesize=letter, rightMargin=0.5*inch,
                                        leftMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)

                # Reset elements with headers
                current_elements = header_elements.copy()

                # Add code files header
                current_elements.append(Paragraph("Code Files:", styles['Heading2']))

                # Add part information
                current_elements.append(Paragraph(f"Part {current_part}", styles['Heading3']))

                # Reset size estimation
                estimated_size = 1 * 1024 * 1024  # 1MB for headers

            # Create a group of elements for this file that will try to stay together
            file_elements = []

            # Add file path as a heading
            file_elements.append(Paragraph(relative_path, styles['Heading4']))

            # Add file content with the compact style
            file_elements.append(Preformatted(content, compact_code_style))

            # Try to keep these elements together
            current_elements.append(KeepTogether(file_elements))

            # Update size estimation
            estimated_size += file_contribution

            if progress_callback:
                progress = 45 + int((i / total_files) * 45)
                progress_callback(progress, f"Processing files ({i+1}/{total_files})",
                                f"Added to part {current_part}: {relative_path}")

            logger.info(f"Added file: {relative_path} to part {current_part}")
        except Exception as e:
            logger.error(f"Error processing file {relative_path}: {str(e)}")
            current_elements.append(Paragraph(f"Error processing file: {str(e)}", styles['Warning']))

            if progress_callback:
                progress_callback(None, None, f"Error with file: {relative_path}", "warning")

    # Build final PDF if there are elements
    if len(current_elements) > len(header_elements) + 2:
        if progress_callback:
            progress_callback(90, f"Finalizing PDF part {current_part}", "Creating final document")

        try:
            doc.build(current_elements)
            output_files.append(current_output)
            logger.info(f"Generated PDF part {current_part} at {current_output}")

            if progress_callback:
                progress_callback(None, None, f"Generated: {os.path.basename(current_output)}")
        except Exception as e:
            logger.error(f"Error building final PDF part {current_part}: {str(e)}")
            if progress_callback:
                progress_callback(None, None, f"Error generating final PDF part: {str(e)}", "error")

    # If only one part was created, rename it to the original name
    if len(output_files) == 1:
        try:
            os.rename(output_files[0], output_path)
            output_files = [output_path]
            logger.info(f"Renamed single part to {output_path}")

            if progress_callback:
                progress_callback(None, None, f"Renamed to: {os.path.basename(output_path)}")
        except Exception as e:
            logger.error(f"Error renaming output file: {str(e)}")

    if progress_callback:
        progress_callback(100, "PDF generation complete", f"Created {len(output_files)} PDF parts")

    return output_files

def generate_split_documents(output_path, header_elements, code_files, styles, max_pdf_size_mb,
                            progress_callback=None, machine_format=False):
    """Generate split PDF documents based on categorization."""
    # Check if we have categorized files (dictionary) or just a flat list
    if isinstance(code_files, dict):
        # We have categorized files
        regular_files = code_files.get('regular', [])
        ios_files = code_files.get('ios', [])
        android_files = code_files.get('android', [])

        # Always create multiple PDFs with the specified size limit
        return _generate_split_pdfs_with_categories(
            output_path, header_elements, regular_files, ios_files, android_files,
            styles, max_pdf_size_mb, progress_callback, machine_format=machine_format
        )
    else:
        # Legacy support for flat list of files
        return _generate_split_pdfs(output_path, header_elements, code_files, styles, max_pdf_size_mb,
                                   progress_callback, machine_format=machine_format)


def _generate_split_pdfs_with_categories(output_path, header_elements, regular_files, ios_files, android_files,
                                        styles, max_pdf_size_mb, progress_callback=None, machine_format=False):
    """Generate multiple PDFs, each under the specified size limit, with categorized files."""
    from reportlab.pdfgen import canvas
    import os.path

    if progress_callback:
        format_type = "compact " if machine_format else ""
        progress_callback(45, f"Preparing split {format_type}PDFs", "Calculating file sizes")

    # IMPORTANT FIX: Convert MB to bytes correctly and log the value
    # Use proper conversion: 1 MB = 1,048,576 bytes
    max_size_bytes = max_pdf_size_mb * 1048576

    # Add explicit logging of target size
    if progress_callback:
        format_type = "Machine-readable" if machine_format else "Human-readable"
        progress_callback(None, None, f"Target {format_type} PDF size: {max_pdf_size_mb} MB = {max_size_bytes} bytes", "info")

    # Prepare output paths
    base_name, ext = os.path.splitext(output_path)
    output_files = []

    # Create separate PDFs for each category
    # 1. Regular files
    if regular_files:
        # Add format indicator to filename if machine format
        format_indicator = "_machine" if machine_format else ""
        regular_pdf = f"{base_name}_regular{format_indicator}{ext}"

        # IMPORTANT FIX: Create new minimal header WITHOUT the project structure
        # Just keep title and timestamp, remove the structure part
        elements = []
        for element in header_elements:
            # Only copy the Title, format indicator, and timestamp paragraphs, skip the project structure
            if isinstance(element, Paragraph) and (
                element.text.startswith("Code Collection") or
                element.text.startswith("Generated on") or
                "Format" in element.text
            ):
                elements.append(element)

        # Add the category heading
        elements.append(Paragraph("Regular Code Files", styles['Heading2']))

        # Split regular files if needed
        regular_pdfs = _split_category_files(
            regular_pdf, elements, regular_files, styles, max_size_bytes,
            progress_callback, progress_start=45, progress_range=20,
            category="Regular", machine_format=machine_format
        )

        output_files.extend(regular_pdfs)

    # 2. iOS files
    if ios_files:
        # Add format indicator to filename if machine format
        format_indicator = "_machine" if machine_format else ""
        ios_pdf = f"{base_name}_ios{format_indicator}{ext}"

        # IMPORTANT FIX: Create new minimal header WITHOUT the project structure
        # Just keep title and timestamp, remove the structure part
        elements = []
        for element in header_elements:
            # Only copy the Title, format indicator, and timestamp paragraphs, skip the project structure
            if isinstance(element, Paragraph) and (
                element.text.startswith("Code Collection") or
                element.text.startswith("Generated on") or
                "Format" in element.text
            ):
                elements.append(element)

        # Add the category heading
        elements.append(Paragraph("iOS Code Files", styles['Heading2']))

        # Split iOS files if needed
        ios_pdfs = _split_category_files(
            ios_pdf, elements, ios_files, styles, max_size_bytes,
            progress_callback, progress_start=65, progress_range=15,
            category="iOS", machine_format=machine_format
        )

        output_files.extend(ios_pdfs)

    # 3. Android files
    if android_files:
        # Add format indicator to filename if machine format
        format_indicator = "_machine" if machine_format else ""
        android_pdf = f"{base_name}_android{format_indicator}{ext}"

        # IMPORTANT FIX: Create new minimal header WITHOUT the project structure
        # Just keep title and timestamp, remove the structure part
        elements = []
        for element in header_elements:
            # Only copy the Title, format indicator, and timestamp paragraphs, skip the project structure
            if isinstance(element, Paragraph) and (
                element.text.startswith("Code Collection") or
                element.text.startswith("Generated on") or
                "Format" in element.text
            ):
                elements.append(element)

        # Add the category heading
        elements.append(Paragraph("Android Code Files", styles['Heading2']))

        # Split Android files if needed
        android_pdfs = _split_category_files(
            android_pdf, elements, android_files, styles, max_size_bytes,
            progress_callback, progress_start=80, progress_range=15,
            category="Android", machine_format=machine_format
        )

        output_files.extend(android_pdfs)

    if progress_callback:
        format_type = "machine-readable" if machine_format else "human-readable"
        progress_callback(100, "PDF generation complete", f"Created {len(output_files)} {format_type} PDF files")

    return output_files

def _split_category_files(base_output, header_elements, files, styles, max_size_bytes, progress_callback=None,
                          progress_start=0, progress_range=100, category="", machine_format=False):
    """Split a category of files into multiple PDFs based on size limit - NO SPACERS."""
    from reportlab.platypus import PageBreak, KeepTogether
    from reportlab.lib.styles import ParagraphStyle

    # Create a modified Code style with minimal spacing
    code_font_size = 3 if machine_format else 8
    compact_code_style = ParagraphStyle(
        name='CompactCode',
        fontName='Courier',
        fontSize=code_font_size,
        leading=code_font_size+2,
        alignment=TA_LEFT,
        spaceAfter=1 if machine_format else 3,
        spaceBefore=0 if machine_format else 1
    )

    output_files = []
    current_part = 1
    current_output = base_output.replace('.pdf', f'_part{current_part}.pdf')
    doc = SimpleDocTemplate(current_output, pagesize=letter, rightMargin=0.5*inch,
                           leftMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)

    # Start with header elements
    current_elements = header_elements.copy()

    # Add part information (with no spacers)
    current_elements.append(Paragraph(f"{category} Files - Part {current_part}", styles['Heading3']))

    # Initialize file size estimation (header elements typically don't exceed 1MB)
    estimated_size = 1 * 1024 * 1024  # Start with 1MB for headers

    # IMPORTANT: Set a minimum size for file contribution to ensure files aren't too small
    MIN_FILE_CONTRIBUTION = 30 * 1024  # Minimum 30KB per file

    # Process all files
    total_files = len(files)
    processed_files = 0

    if total_files == 0:
        if progress_callback:
            progress_callback(progress_start + progress_range, f"No {category} files to process",
                            f"Skipping {category} category: no files found")
        return output_files

    for i, (relative_path, filepath) in enumerate(files):
        try:
            # Try to read the file content
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as file:
                    content = file.read()
            except UnicodeDecodeError:
                # For binary files or files with encoding issues
                content = "[Binary file or encoding error - content not displayed]"
            except Exception as e:
                content = f"[Error reading file: {str(e)}]"

            # Estimate size contribution of this file
            # Rough estimate: assume each character takes about 2 bytes in the PDF
            file_contribution = max(len(content) * 2 + 5000, MIN_FILE_CONTRIBUTION)  # Ensure minimum size

            # Check if adding this file would exceed the limit and we already have content
            if estimated_size + file_contribution > max_size_bytes and len(current_elements) > len(header_elements) + 1:
                # Build current PDF
                if progress_callback:
                    current_progress = progress_start + int((i / total_files) * progress_range)
                    format_type = "compact " if machine_format else ""
                    progress_callback(current_progress, f"Creating {format_type}{category} PDF part {current_part}",
                                    f"Finalizing part {current_part}")

                try:
                    doc.build(current_elements)
                    output_files.append(current_output)
                    logger.info(f"Generated {category} PDF part {current_part} at {current_output}")

                    if progress_callback:
                        progress_callback(None, None, f"Generated: {os.path.basename(current_output)}")
                except Exception as e:
                    logger.error(f"Error building PDF part {current_part}: {str(e)}")
                    if progress_callback:
                        progress_callback(None, None, f"Error generating PDF part {current_part}: {str(e)}", "error")

                # Start new PDF
                current_part += 1
                current_output = base_output.replace('.pdf', f'_part{current_part}.pdf')
                doc = SimpleDocTemplate(current_output, pagesize=letter, rightMargin=0.5*inch,
                                       leftMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)

                # Reset elements with headers
                current_elements = header_elements.copy()
                current_elements.append(Paragraph(f"{category} Files - Part {current_part}", styles['Heading3']))

                # Reset size estimation
                estimated_size = 1 * 1024 * 1024  # 1MB for headers

            # Create a group of elements for this file that will try to stay together
            file_elements = []

            # Add file path as a heading
            file_elements.append(Paragraph(relative_path, styles['Heading4']))

            # Add file content with the compact style
            file_elements.append(Preformatted(content, compact_code_style))

            # Try to keep these elements together
            current_elements.append(KeepTogether(file_elements))

            # Update size estimation
            estimated_size += file_contribution
            processed_files += 1

            if progress_callback:
                current_progress = progress_start + int((i / total_files) * progress_range)
                format_type = "compact " if machine_format else ""
                progress_callback(current_progress, f"Processing {format_type}{category} files ({i+1}/{total_files})",
                                f"Added to part {current_part}: {relative_path}")

            logger.info(f"Added file: {relative_path} to {category} part {current_part}")

        except Exception as e:
            logger.error(f"Error processing file {relative_path}: {str(e)}")
            current_elements.append(Paragraph(f"Error processing file {relative_path}: {str(e)}", styles['Warning']))

            if progress_callback:
                progress_callback(None, None, f"Error with file: {relative_path}", "warning")

    # Build final PDF if there are elements beyond just the headers
    if len(current_elements) > len(header_elements) + 1:
        if progress_callback:
            # Calculate final progress correctly
            current_progress = progress_start + progress_range - 5
            format_type = "compact " if machine_format else ""
            progress_callback(current_progress, f"Creating {format_type}{category} PDF part {current_part}",
                            f"Finalizing part {current_part}")

        try:
            doc.build(current_elements)
            output_files.append(current_output)
            logger.info(f"Generated {category} PDF part {current_part} at {current_output}")

            if progress_callback:
                progress_callback(None, None, f"Generated: {os.path.basename(current_output)}")
        except Exception as e:
            logger.error(f"Error building final PDF part {current_part}: {str(e)}")
            if progress_callback:
                progress_callback(None, None, f"Error generating final PDF part: {str(e)}", "error")

    # If we only created one part, rename it to the base name
    if len(output_files) == 1 and '_part1.pdf' in output_files[0]:
        try:
            new_output = base_output
            os.rename(output_files[0], new_output)
            output_files = [new_output]
            logger.info(f"Renamed single part to {new_output}")

            if progress_callback:
                progress_callback(None, None, f"Renamed to: {os.path.basename(new_output)}")
        except Exception as e:
            logger.error(f"Error renaming output file: {str(e)}")

    if progress_callback:
        format_type = "machine-readable" if machine_format else "human-readable"
        progress_callback(progress_start + progress_range,
                        f"{category} PDF generation complete",
                        f"Created {len(output_files)} {format_type} {category} PDF file(s) with {processed_files} code files")

    return output_files

def generate_structure_pdf(output_path, root_path, excluded_dirs=None, pdf_title=None):
    """Generate a PDF containing only the project structure with enhanced formatting."""
    if excluded_dirs is None:
        excluded_dirs = COMMON_EXCLUDED_DIRS

    # Common elements for all PDFs
    styles = getSampleStyleTools()

    # Prepare header elements
    elements = []

    # Add title
    if pdf_title:
        title = pdf_title
    else:
        title = f"Code Collection: {os.path.basename(root_path)}"

    elements.append(Paragraph(title, styles['Title']))

    # Add generation timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph(f"Generated on: {timestamp}", styles['Normal']))

    # Create enhanced project structure visualization
    elements.append(Paragraph("Project Structure:", styles['Heading2']))

    # Get structure with enhanced ASCII art
    structure = get_folder_structure(root_path, excluded_dirs=excluded_dirs)

    # Add a label to clarify formatting
    elements.append(Paragraph("Key: '+--' indicates a branch, '|' indicates continuation", styles['Normal']))

    # Create a more visually appealing structure representation
    elements.append(Preformatted(structure, styles['Code']))

    # Create the PDF
    doc = SimpleDocTemplate(output_path, pagesize=letter, rightMargin=0.5*inch,
                           leftMargin=0.5*inch, topMargin=0.5*inch, bottomMargin=0.75*inch)

    try:
        doc.build(elements)
        logger.info(f"Structure PDF successfully created at {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error building structure PDF: {str(e)}")
        return None

# Flask application
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 750 * 1024 * 1024  # 750 MB limit
app.secret_key = os.urandom(24)  # For session management

# Flask route for static files is handled automatically when using static_folder parameter
# We can remove the custom route


@app.route('/')
def index():
    # Make sure we're always returning a fresh rendered template
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    """Backward compatibility route for direct uploads."""
    return redirect(url_for('index'))

# Progress monitoring functions
# Modify the add_progress_update function to store all log messages
def add_progress_update(progress=None, message=None, log=None, log_type='info', complete=False, download_url=None):
    """Add a progress update to the queue and store in log history."""
    global progress_queue
    global all_log_messages

    # Get current timestamp
    timestamp = datetime.now().isoformat()

    # Format log message for history
    if log:
        # Add timestamp to log message for history
        formatted_log = f"[{datetime.now().strftime('%I:%M:%S %p')}] {log}"
        all_log_messages.append(formatted_log)

    # Create the update dictionary
    update = {
        'timestamp': timestamp
    }

    if progress is not None:
        update['progress'] = progress

    if message:
        update['message'] = message

    if log:
        update['log'] = log
        update['type'] = log_type

    if complete:
        update['complete'] = True
        if download_url:
            update['download_url'] = download_url

        # When processing is complete, save logs to file and add download link
        if all_log_messages:
            logs_path = save_logs_to_file()
            if logs_path:
                # Include in the same update - show log download separately
                update['logs_url'] = f"/download?filename=process_logs.txt&task_id={current_task_id}&logs=true"

    progress_queue.put(update)

# Add function to save logs to a file
def save_logs_to_file():
    """Save all collected log messages to a text file."""
    try:
        logs_path = os.path.join(app.config['UPLOAD_FOLDER'], f"process_logs_{current_task_id}.txt")
        with open(logs_path, 'w', encoding='utf-8') as f:
            # Add header
            f.write(f"Code Collector Process Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            # Write all log messages
            for msg in all_log_messages:
                f.write(f"{msg}\n")

        # Register the log file for download
        with app.app_context():
            if not hasattr(app, 'download_files'):
                app.download_files = {}
            app.download_files[f"{current_task_id}_logs"] = logs_path

        return logs_path
    except Exception as e:
        logger.error(f"Error saving logs to file: {str(e)}")
        return None

@app.route('/progress')
def progress_stream():
    """Server-sent events stream for progress updates."""
    # Capture task_id from the request arguments within the request context
    task_id = request.args.get('task_id', '')
    current_task = current_task_id  # Store the global task ID locally

    def generate():
        # Don't use request object inside this generator
        if task_id != current_task:
            yield f"data: {json.dumps({'error': 'Invalid task ID'})}\n\n"
            return

        # Send initial message
        yield f"data: {json.dumps({'log': 'Connected to progress stream', 'type': 'info'})}\n\n"

        while True:
            try:
                # Try to get an update from the queue with a timeout
                update = progress_queue.get(timeout=1)
                yield f"data: {json.dumps(update)}\n\n"

                # If this update indicates completion, we're done
                if 'complete' in update and update['complete']:
                    break

            except queue.Empty:
                # Send a ping to keep the connection alive
                yield f"data: {json.dumps({'ping': True})}\n\n"

            except Exception as e:
                # Send error and break on any other exception
                yield f"data: {json.dumps({'error': str(e), 'type': 'error'})}\n\n"
                break

    return Response(generate(), mimetype='text/event-stream')

def process_project_async(zip_path, output_path, extract_dir, excluded_dirs, max_pdf_size=None):
    """Process the project in a background thread."""
    try:
        # Extract the zip file
        import zipfile
        add_progress_update(5, "Extracting ZIP file", "Unpacking project files...")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        add_progress_update(10, "Extraction complete", "ZIP file extracted successfully")

        # Determine project root directory
        contents = os.listdir(extract_dir)
        if len(contents) == 1 and os.path.isdir(os.path.join(extract_dir, contents[0])):
            project_dir = os.path.join(extract_dir, contents[0])
            add_progress_update(None, None, f"Project root identified: {contents[0]}")
        else:
            project_dir = extract_dir
            add_progress_update(None, None, "Using ZIP root as project directory")

        # Collect code files with progress updates
        add_progress_update(15, "Collecting code files", "Scanning project structure...")
        code_files = collect_code_files(project_dir, excluded_dirs=excluded_dirs,
                                       progress_callback=add_progress_update)

        if not code_files:
            add_progress_update(None, None, "No code files found in the project", "warning")
            add_progress_update(100, "Process complete", "No files to process", complete=True)
            return None

        # Generate PDF with progress updates
        output_files = generate_pdf(output_path, project_dir, code_files,
                                  excluded_dirs=excluded_dirs,
                                  max_pdf_size_mb=max_pdf_size,
                                  progress_callback=add_progress_update)

        # Determine download URL and add completion message
        if isinstance(output_files, list) and len(output_files) > 1:
            # Create zip file for multiple PDFs
            import zipfile

            zip_filename = 'code_collection_pdfs.zip'
            zip_path = os.path.join(os.path.dirname(output_path), zip_filename)

            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for pdf_file in output_files:
                    zipf.write(pdf_file, os.path.basename(pdf_file))

            add_progress_update(None, None, f"Created ZIP archive with {len(output_files)} PDF files")
            download_url = f"/download?filename={zip_filename}"
            session['download_file'] = zip_path
        else:
            # Single PDF
            if isinstance(output_files, list):
                download_path = output_files[0]
                filename = os.path.basename(download_path)
            else:
                download_path = output_files
                filename = os.path.basename(download_path)

            download_url = f"/download?filename={filename}"
            session['download_file'] = download_path

        add_progress_update(100, "Processing complete", "Files ready for download", complete=True, download_url=download_url)

    except Exception as e:
        logger.error(f"Error in background processing: {str(e)}")
        add_progress_update(None, None, f"Error: {str(e)}", "error")
        add_progress_update(100, "Process failed", "An error occurred", complete=True)

@app.route('/upload-async', methods=['POST'])
def upload_async():
    """Handle file upload with asynchronous processing."""
    global current_task_id

    if 'project_zip' not in request.files:
        return redirect(url_for('index'))

    file = request.files['project_zip']
    if file.filename == '':
        return redirect(url_for('index'))

    # Clear the progress queue
    while not progress_queue.empty():
        progress_queue.get()

    # Generate a unique task ID
    current_task_id = datetime.now().strftime("%Y%m%d%H%M%S") + str(os.urandom(4).hex())

    # Set up the excluded directories list
    # Instead of getting from form checkboxes, we now always use the COMMON_EXCLUDED_DIRS
    excluded_dirs = COMMON_EXCLUDED_DIRS.copy()

    # Add custom excluded directories
    custom_excluded = request.form.get('custom_excluded_dirs', '').split(',')
    custom_excluded = [d.strip() for d in custom_excluded if d.strip()]
    excluded_dirs.extend(custom_excluded)

    # Get max PDF size if provided
    max_pdf_size_mb = None
    if request.form.get('split_pdf', 'off') == 'on':
        try:
            max_pdf_size_mb = float(request.form.get('max_pdf_size', '0'))
            if max_pdf_size_mb <= 0:
                max_pdf_size_mb = 0.39  # Default to 390KB (0.39MB)
        except ValueError:
            max_pdf_size_mb = 0.39  # Default to 390KB (0.39MB)
    else:
        # Always split at 390KB
        max_pdf_size_mb = 0.39  # 390KB

    # Get output format preference (new feature)
    machine_format = request.form.get('output_format', 'human') == 'machine'

    # Get selected file categories
    include_categories = request.form.getlist('include_categories')
    # Default to all categories if none selected
    if not include_categories:
        include_categories = ['regular', 'ios', 'android']

    # Create temporary directories
    extract_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'extract_' + current_task_id)
    os.makedirs(extract_dir, exist_ok=True)

    # Save uploaded file
    zip_filename = secure_filename(file.filename)
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], zip_filename)
    file.save(zip_path)

    # Get base filename without .zip extension for PDF output
    pdf_basename = os.path.splitext(zip_filename)[0]

    # Add format indicator to filename if machine format
    format_indicator = "_machine" if machine_format else ""
    pdf_filename = f"{pdf_basename}_code{format_indicator}.pdf"
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)

    # Create a dictionary for additional parameters - this way we can add parameters without
    # having to update function signatures everywhere
    process_params = {
        'include_categories': include_categories,
        'machine_format': machine_format  # Pass the new parameter
    }

    # Start background processing thread with all data it needs
    thread = threading.Thread(
        target=process_project_async_worker,
        args=(zip_path, pdf_path, extract_dir, excluded_dirs, max_pdf_size_mb, current_task_id, zip_filename),
        kwargs=process_params
    )
    thread.daemon = True
    thread.start()

    # Return the task ID and status page
    return jsonify({
        'task_id': current_task_id,
        'status': 'processing'
    })

@app.route('/download', methods=['GET'])
def download_file():
    """Handle file downloads."""
    filename = request.args.get('filename', '')
    task_id = request.args.get('task_id', '')
    is_logs = request.args.get('logs', 'false') == 'true'

    if not filename or not task_id:
        return redirect(url_for('index'))

    # Get the file path based on what's being downloaded
    if is_logs:
        # Handle logs file
        key = f"{task_id}_logs"
        if not hasattr(app, 'download_files') or key not in app.download_files:
            return redirect(url_for('index'))
        file_path = app.download_files[key]
    else:
        # Handle regular output files
        if not hasattr(app, 'download_files') or task_id not in app.download_files:
            return redirect(url_for('index'))
        file_path = app.download_files[task_id]

    if not os.path.exists(file_path):
        return redirect(url_for('index'))

    # Log successful download
    logger.info(f"Sending file for download: {filename} (Task ID: {task_id})")

    # Send the file
    response = send_file(file_path, as_attachment=True, download_name=filename)

    return response

@app.route('/scan-zip', methods=['POST'])
def scan_zip():
    """Scan a ZIP file to detect directories for auto-exclusion."""
    if 'project_zip' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['project_zip']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    try:
        # Create a dedicated folder for this scan to avoid conflicts
        scan_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'scan_' + datetime.now().strftime("%Y%m%d%H%M%S"))
        os.makedirs(scan_dir, exist_ok=True)

        # Save the uploaded file temporarily
        zip_path = os.path.join(scan_dir, file.filename)
        file.save(zip_path)

        # Extract directory information from the ZIP
        import zipfile
        detected_dirs = set()
        all_paths = set()

        logger.info(f"Scanning ZIP file: {file.filename}")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                # Normalize path separators (handle both / and \)
                normalized_path = file_info.filename.replace('\\', '/')
                all_paths.add(normalized_path)

                # Extract directory components
                path_parts = normalized_path.split('/')

                # Process each directory level
                current_path = ""
                for i, part in enumerate(path_parts[:-1]):  # Skip the last part if it's a file
                    if part:  # Skip empty parts
                        current_path = current_path + part + "/"
                        detected_dirs.add(part)  # Add individual directory names

        logger.info(f"Detected directories: {detected_dirs}")

        # Look for common directories to exclude
        common_dirs = [
            '.git', 'node_modules', '__pycache__', 'venv', 'env', '.venv', '.env', 'dist', 'build', 'obj', 'bin',
            '__MACOSX', '.trash', '.expo', '.gradle', 'ios/Pods', 'Pods', 'Local Podspecs', 'Images.xcassets',
            'android/app/src'
        ]
        found_dirs = [dir_name for dir_name in common_dirs if dir_name in detected_dirs]

        # Also check for these directories anywhere in the paths
        for common_dir in common_dirs:
            for path in all_paths:
                if f"/{common_dir}/" in path or path.startswith(f"{common_dir}/"):
                    if common_dir not in found_dirs:
                        found_dirs.append(common_dir)
                        break

        # Also check for macOS hidden files pattern (._filename.ext)
        mac_files = any(path.startswith('._') or '/._./' in path for path in all_paths)
        if mac_files and '__MACOSX' not in found_dirs:
            found_dirs.append('__MACOSX')

        logger.info(f"Found directories to exclude: {found_dirs}")

        # Clean up the temporary file and directory
        os.remove(zip_path)
        os.rmdir(scan_dir)

        return jsonify({"detected_dirs": found_dirs}), 200

    except Exception as e:
        logger.error(f"Error scanning ZIP: {str(e)}")
        return jsonify({"error": str(e)}), 500

def cleanup():
    """Clean up temporary files on application exit."""
    try:
        if hasattr(app, 'config') and 'UPLOAD_FOLDER' in app.config and os.path.exists(app.config['UPLOAD_FOLDER']):
            shutil.rmtree(app.config['UPLOAD_FOLDER'])
    except Exception as e:
        logger.error(f"Error during final cleanup: {str(e)}")

import atexit
atexit.register(cleanup)

def save_code_to_text_files(code_files, output_folder, progress_callback=None):
    """
    Save all code files as text files when PDF generation fails.
    This is a fallback solution to ensure users can at least view the code.

    Args:
        code_files: Dict or list of code files
        output_folder: Path to save the text files
        progress_callback: Optional callback for progress updates

    Returns:
        Path to ZIP file containing all text files
    """
    import os
    import zipfile
    import shutil

    # Create temporary directory for text files
    text_files_dir = os.path.join(output_folder, "code_files_text")
    if os.path.exists(text_files_dir):
        shutil.rmtree(text_files_dir)
    os.makedirs(text_files_dir)

    # Initialize counters
    total_files = 0
    processed_files = 0

    # Count files for progress reporting
    if isinstance(code_files, dict):
        total_files = sum(len(files) for files in code_files.values())
    else:
        total_files = len(code_files)

    if progress_callback:
        progress_callback(0, "Saving code to text files", "Creating text file backup")

    # Process files based on structure
    if isinstance(code_files, dict):
        # Create category directories
        for category, files in code_files.items():
            category_dir = os.path.join(text_files_dir, category)
            os.makedirs(category_dir, exist_ok=True)

            for i, (relative_path, filepath) in enumerate(files):
                # Create subdirectories if needed
                file_dir = os.path.dirname(relative_path)
                if file_dir:
                    os.makedirs(os.path.join(category_dir, file_dir), exist_ok=True)

                try:
                    # Read file content
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as src_file:
                        content = src_file.read()

                    # Save content to text file
                    output_path = os.path.join(category_dir, relative_path)
                    with open(output_path, 'w', encoding='utf-8') as out_file:
                        out_file.write(content)

                    processed_files += 1
                    if progress_callback:
                        progress = int((processed_files / total_files) * 90)
                        progress_callback(progress, f"Saving files ({processed_files}/{total_files})",
                                        f"Saved: {category}/{relative_path}")
                except Exception as e:
                    logger.error(f"Error saving file {relative_path}: {str(e)}")
                    if progress_callback:
                        progress_callback(None, None, f"Error with file: {relative_path}", "warning")
    else:
        # Flat list of files
        for i, (relative_path, filepath) in enumerate(code_files):
            # Create subdirectories if needed
            file_dir = os.path.dirname(relative_path)
            if file_dir:
                os.makedirs(os.path.join(text_files_dir, file_dir), exist_ok=True)

            try:
                # Read file content
                with open(filepath, 'r', encoding='utf-8', errors='replace') as src_file:
                    content = src_file.read()

                # Save content to text file
                output_path = os.path.join(text_files_dir, relative_path)
                with open(output_path, 'w', encoding='utf-8') as out_file:
                    out_file.write(content)

                processed_files += 1
                if progress_callback:
                    progress = int((processed_files / total_files) * 90)
                    progress_callback(progress, f"Saving files ({processed_files}/{total_files})",
                                    f"Saved: {relative_path}")
            except Exception as e:
                logger.error(f"Error saving file {relative_path}: {str(e)}")
                if progress_callback:
                    progress_callback(None, None, f"Error with file: {relative_path}", "warning")

    # Create a ZIP file of all text files
    if progress_callback:
        progress_callback(90, "Creating ZIP archive", "Compressing text files")

    zip_filename = os.path.join(output_folder, "code_files.zip")
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(text_files_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, text_files_dir)
                zipf.write(file_path, arcname)

    if progress_callback:
        progress_callback(100, "Text files ready", f"Created archive with {processed_files} files")

    # Clean up the temporary directory
    shutil.rmtree(text_files_dir)

    return zip_filename


# Add this to the process_project_async_worker function to use as a fallback
def process_project_async_worker(zip_path, output_path, extract_dir, excluded_dirs, max_pdf_size=None, task_id=None, zip_filename=None, **kwargs):
    """Process the project in a background thread without requiring Flask request context."""
    global all_log_messages
    global current_task_id

    # Set current task ID
    current_task_id = task_id

    # Get include_categories from kwargs or use default
    include_categories = kwargs.get('include_categories', ['regular', 'ios', 'android'])

    # Get machine_format from kwargs (new feature)
    machine_format = kwargs.get('machine_format', False)

    # Clear previous log history
    all_log_messages = []

    try:
        # Log the format choice
        if machine_format:
            add_progress_update(None, None, "Using machine-readable format with compact 3px fonts", "info")
            add_progress_update(None, None, "This format saves significant file space but may be harder to read", "info")
        else:
            add_progress_update(None, None, "Using standard human-readable format", "info")

        # Extract the zip file
        import zipfile
        add_progress_update(5, "Extracting ZIP file", "Unpacking project files...")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        add_progress_update(10, "Extraction complete", "ZIP file extracted successfully")

        # Determine project root directory
        contents = os.listdir(extract_dir)
        if len(contents) == 1 and os.path.isdir(os.path.join(extract_dir, contents[0])):
            project_dir = os.path.join(extract_dir, contents[0])
            project_name = contents[0]
            add_progress_update(None, None, f"Project root identified: {project_name}")
        else:
            project_dir = extract_dir
            project_name = os.path.splitext(zip_filename)[0] if zip_filename else "Project"
            add_progress_update(None, None, "Using ZIP root as project directory")

        # Use zip filename for the PDF title if available
        pdf_title = f"Code Collection: {os.path.splitext(zip_filename)[0]}" if zip_filename else None

        # Add __MACOSX and other special directories to excluded_dirs if not already there
        for special_dir in COMMON_EXCLUDED_DIRS:
            if special_dir not in excluded_dirs:
                excluded_dirs.append(special_dir)

        # Also exclude files starting with ._
        add_progress_update(None, None, f"Excluded directories: {', '.join(excluded_dirs)}")

        # Collect code files with progress updates
        add_progress_update(15, "Collecting code files", "Scanning project structure...")

        # Use the new categorized file collection with excluded extensions
        file_categories = collect_code_files(
            project_dir,
            excluded_dirs=excluded_dirs,
            excluded_extensions=EXCLUDED_FILE_EXTENSIONS,
            excluded_files=EXCLUDED_FILES,
            progress_callback=add_progress_update
        )

        # Filter categories based on user selection
        filtered_categories = {}
        if 'regular' in include_categories:
            filtered_categories['regular'] = file_categories['regular']
            add_progress_update(None, None, f"Including {len(file_categories['regular'])} regular files")

        if 'ios' in include_categories:
            filtered_categories['ios'] = file_categories['ios']
            add_progress_update(None, None, f"Including {len(file_categories['ios'])} iOS files")

        if 'android' in include_categories:
            filtered_categories['android'] = file_categories['android']
            add_progress_update(None, None, f"Including {len(file_categories['android'])} Android files")

        # Count selected files
        total_selected = sum(len(files) for files in filtered_categories.values())
        add_progress_update(None, None, f"Total files selected for processing: {total_selected}")

        # Count total files
        total_regular = len(file_categories['regular'])
        total_ios = len(file_categories['ios'])
        total_android = len(file_categories['android'])
        total_files = total_regular + total_ios + total_android

        if total_files == 0:
            add_progress_update(None, None, "No code files found in the project", "warning")
            add_progress_update(100, "Process complete", "No files to process", complete=True)
            return None

        add_progress_update(None, None,
                          f"Found {total_regular} regular files, {total_ios} iOS files, {total_android} Android files")

        # First, generate the structure-only PDF with clear naming
        base_path, ext = os.path.splitext(output_path)

        # Add format indicator to structure filename if machine format
        format_indicator = "_machine" if machine_format else ""
        structure_pdf_path = f"{base_path}_structure{format_indicator}{ext}"

        add_progress_update(40, "Generating structure PDF",
                           f"Creating project structure document with {'compact' if machine_format else 'standard'} fonts")

        # Generate the structure PDF with explicit logging and machine format parameter
        structure_pdf = generate_improved_structure_pdf(
            structure_pdf_path,
            project_dir,
            excluded_dirs=excluded_dirs,
            pdf_title=pdf_title,
            machine_format=machine_format  # Pass the machine format parameter
        )

        if not structure_pdf:
            add_progress_update(None, None, "Error generating structure PDF", "error")
            structure_exists = False
        else:
            # Verify the file exists and log its properties
            if os.path.exists(structure_pdf):
                file_size = os.path.getsize(structure_pdf)
                format_type = "machine-readable" if machine_format else "human-readable"
                add_progress_update(None, None,
                                  f"{format_type.capitalize()} structure PDF generated: {os.path.basename(structure_pdf)} (Size: {file_size/1024:.2f} KB)")
                structure_exists = True
            else:
                add_progress_update(None, None, "Structure PDF path returned but file not found", "warning")
                structure_exists = False

        # Then generate the code PDFs without the structure
        format_type = "compact " if machine_format else ""
        add_progress_update(50, f"Generating {format_type}code PDFs", "Creating code file documents")

        # Try to generate PDF without structure
        pdf_success = True
        try:
            # Generate PDF with progress updates, categorized files, and machine format parameter
            output_files = generate_pdf(
                output_path,
                project_dir,
                filtered_categories,
                excluded_dirs=excluded_dirs,
                max_pdf_size_mb=max_pdf_size,
                progress_callback=add_progress_update,
                pdf_title=pdf_title,
                machine_format=machine_format  # Pass the machine format parameter
            )
        except Exception as e:
            logger.error(f"PDF generation failed completely: {str(e)}")
            add_progress_update(None, None, f"PDF generation failed: {str(e)}", "error")
            pdf_success = False
            output_files = []

        # If PDF generation failed or there are no output files, fallback to text files
        if not pdf_success or not output_files:
            add_progress_update(60, "PDF generation failed", "Falling back to text files")
            # Create text files instead
            text_zip = save_code_to_text_files(
                filtered_categories,
                os.path.dirname(output_path),
                progress_callback=add_progress_update
            )

            # Use the text files ZIP as the download
            download_url = f"/download?filename=code_files.zip&task_id={task_id}"

            # Save download file path with task_id in app config
            with app.app_context():
                if not hasattr(app, 'download_files'):
                    app.download_files = {}
                app.download_files[task_id] = text_zip

            add_progress_update(100, "Text files created", "PDF generation failed but text files are available for download",
                              complete=True, download_url=download_url)
            return

        # Prepare file list for output
        if not isinstance(output_files, list):
            if output_files:
                output_files = [output_files]
            else:
                output_files = []

        # Make sure we have a list for the next steps
        add_progress_update(None, None, f"Generated {len(output_files)} code PDF files", "info")

        # Handle structure PDF inclusion
        # IMPORTANT: Make sure structure PDF is ALWAYS included in output_files
        if structure_exists and os.path.exists(structure_pdf):
            # Add at beginning if not already in the list
            if structure_pdf not in output_files:
                output_files.insert(0, structure_pdf)
                add_progress_update(None, None, f"Added structure PDF to output files: {os.path.basename(structure_pdf)}")
            else:
                add_progress_update(None, None, "Structure PDF was already in output files list")
        else:
            add_progress_update(None, None, "Structure PDF not available to include in output", "warning")

        # Continue with normal flow for PDF downloads
        # Determine download URL and add completion message
        if isinstance(output_files, list) and len(output_files) > 1:
            # Create zip file for multiple PDFs
            import zipfile

            # Use project name from zip file with format indicator
            zip_basename = os.path.splitext(zip_filename)[0] if zip_filename else "code_collection"
            format_indicator = "_machine" if machine_format else ""
            zip_filename_output = f'{zip_basename}_pdfs{format_indicator}.zip'
            zip_path = os.path.join(os.path.dirname(output_path), zip_filename_output)

            # Log all files being added to ZIP
            add_progress_update(None, None, f"Preparing to add {len(output_files)} files to ZIP:", "info")

            total_size = 0
            for i, pdf_file in enumerate(output_files):
                file_exists = os.path.exists(pdf_file)
                file_size = os.path.getsize(pdf_file) if file_exists else 0
                total_size += file_size
                add_progress_update(None, None,
                                  f"File {i+1}: {os.path.basename(pdf_file)} - Exists: {file_exists}, Size: {file_size/1024:.2f} KB",
                                  "info" if file_exists else "warning")

            # Create the ZIP file with all PDFs
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for pdf_file in output_files:
                    if os.path.exists(pdf_file):
                        arcname = os.path.basename(pdf_file)
                        zipf.write(pdf_file, arcname)
                        add_progress_update(None, None, f"Added to ZIP: {arcname} (Size: {os.path.getsize(pdf_file)/1024:.2f} KB)")
                    else:
                        add_progress_update(None, None, f"Could not add to ZIP - file not found: {pdf_file}", "warning")

            # Verify the zip file contents
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zip_contents = zipf.namelist()
                zip_size = os.path.getsize(zip_path)
                add_progress_update(None, None, f"ZIP file contains {len(zip_contents)} files: {', '.join(zip_contents)}")
                add_progress_update(None, None, f"ZIP file size: {zip_size/1024:.2f} KB (Original PDFs: {total_size/1024:.2f} KB)")
                if machine_format:
                    add_progress_update(None, None, "Using machine format saved significant file space!", "info")

            format_type = "machine-readable" if machine_format else "human-readable"
            add_progress_update(None, None, f"Created ZIP archive with {len(output_files)} {format_type} PDF files")
            download_url = f"/download?filename={zip_filename_output}&task_id={task_id}"

            # Save download file path with task_id in app config
            with app.app_context():
                if not hasattr(app, 'download_files'):
                    app.download_files = {}
                app.download_files[task_id] = zip_path
        else:
            # Single PDF
            if isinstance(output_files, list) and output_files:
                download_path = output_files[0]
                filename = os.path.basename(download_path)
            else:
                download_path = output_files
                filename = os.path.basename(download_path)

            # Verify file exists
            if os.path.exists(download_path):
                file_size = os.path.getsize(download_path)
                format_type = "machine-readable" if machine_format else "human-readable"
                add_progress_update(None, None, f"Single {format_type} PDF ready: {filename} (Size: {file_size/1024:.2f} KB)")
            else:
                add_progress_update(None, None, f"Warning: Download file not found: {download_path}", "warning")

            download_url = f"/download?filename={filename}&task_id={task_id}"

            # Save download file path with task_id in app config
            with app.app_context():
                if not hasattr(app, 'download_files'):
                    app.download_files = {}
                app.download_files[task_id] = download_path

        format_type = "machine-readable" if machine_format else "human-readable"
        add_progress_update(100, "Processing complete", f"{format_type.capitalize()} files ready for download",
                          complete=True, download_url=download_url)

    except Exception as e:
        logger.error(f"Error in background processing: {str(e)}")
        add_progress_update(None, None, f"Error: {str(e)}", "error")
        add_progress_update(100, "Process failed", "An error occurred", complete=True)

if __name__ == "__main__":
    import sys

    # Run as web application only
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    app.run(debug=True, host='0.0.0.0', port=port)