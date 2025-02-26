# Code Collector

A Python web application that collects code files from a project folder into a set of organized PDF documents, with a separate project structure PDF for easy navigation.

## Features

- **Project Structure PDF**: Generates a dedicated PDF with complete folder tree at the top
- **Code Organization**: Creates separate PDFs for regular, iOS, and Android code
- **Smart Splitting**: Automatically splits PDFs to keep file sizes manageable
- **Intelligent Detection**: Identifies code files by extension and categorizes mobile files
- **Automatic Exclusion**: Skips common build directories and large artifacts
- **Web Interface**: Clean, responsive UI with real-time progress tracking
- **Large Project Support**: Handles complex projects with hundreds of files
- **Real-time Progress**: Terminal-like output showing processing status

## Automatically Excluded Content

### Excluded Directories
- Build directories: `node_modules`, `.git`, `build`, `dist`, etc.
- Environment directories: `venv`, `.env`, `.venv`, etc.
- Cache directories: `__pycache__`, `.cache`, etc.
- Mobile-specific: `Pods`, `.gradle`, etc.

### Excluded Files
- Package manager files: `package-lock.json`, `yarn.lock`, etc.
- Configuration locks: `Gemfile.lock`, `Cargo.lock`, etc.
- System files: `.DS_Store`, `thumbs.db`, etc.
- Debug logs: `npm-debug.log`, `yarn-error.log`, etc.
- Git files: `.gitignore`, `.gitattributes`, etc.

## Web Interface

The web interface provides:
- File upload for your project ZIP
- Checkboxes to select directories to exclude
- Option to control PDF splitting
- Real-time progress tracking with visual feedback
- Terminal-like output showing processing status

## Supported File Extensions

The application recognizes common code file extensions including:

- Python (.py)
- JavaScript (.js, .jsx)
- TypeScript (.ts, .tsx)
- HTML, CSS (.html, .css, .scss, .sass)
- Java (.java)
- C/C++ (.c, .cpp, .h, .hpp)
- Go (.go)
- Rust (.rs)
- Ruby (.rb)
- PHP (.php)
- And many more...

## PDF Organization

For better navigation, the code files are organized into separate PDFs:

1. **Structure PDF**: Complete folder structure tree
2. **Regular Code PDFs**: Application source code
3. **iOS Code PDFs**: iOS-specific files if detected
4. **Android Code PDFs**: Android-specific files if detected

## PDF Splitting

For large projects, the PDF splitting feature:
- Prevents PDFs from becoming too large and unmanageable
- Makes files easier to share via email
- Organizes files into logical sections
- Keeps PDF rendering faster and more reliable

## Requirements

- Python 3.6+
- Flask
- ReportLab
- PyPDF2 (for PDF splitting)

## Installation

1. Clone this repository
2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

```bash
# Start the web server
python code_collector.py

# Start on a specific port
python code_collector.py serve 8080
```

Then open your browser and navigate to `http://localhost:5000` (or the port you specified).

## Limitations

- Maximum upload size for web interface: 750MB
- PDF generation may be slow for very large projects
- Some non-UTF-8 encoded files might not be properly displayed

## License

MIT