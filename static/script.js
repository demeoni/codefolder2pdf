document.addEventListener('DOMContentLoaded', function() {
    // Clean up any duplicate form elements
    const mainContainer = document.querySelector('.container');
    if (mainContainer) {
        // Keep only the first form
        const forms = mainContainer.querySelectorAll('form');
        if (forms.length > 1) {
            for (let i = 1; i < forms.length; i++) {
                forms[i].parentNode.removeChild(forms[i]);
            }
        }

        // Keep only the first footer
        const footers = mainContainer.querySelectorAll('footer');
        if (footers.length > 1) {
            for (let i = 1; i < footers.length; i++) {
                footers[i].parentNode.removeChild(footers[i]);
            }
        }
    }

    // Setup file input change event
    const fileInput = document.getElementById('project_zip');
    if (fileInput) {
        fileInput.addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;

            // Auto-detect directories in the ZIP file - still useful for internal processing
            try {
                const statusDiv = document.createElement('div');
                statusDiv.className = 'directory-scan-status';
                statusDiv.textContent = 'Scanning ZIP file...';
                fileInput.parentNode.appendChild(statusDiv);

                // Create a FormData object to send the file
                const formData = new FormData();
                formData.append('project_zip', file);

                // Send the file to the server for scanning
                const response = await fetch('/scan-zip', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.error) {
                    statusDiv.textContent = 'Error: ' + data.error;
                    statusDiv.style.color = '#dc3545';
                } else {
                    const foundDirs = data.detected_dirs || [];

                    if (foundDirs.length > 0) {
                        statusDiv.textContent = 'Scan complete. Found ' + foundDirs.length + ' directories.';
                    } else {
                        statusDiv.textContent = 'Scan complete. No common directories found.';
                    }
                }

                // After 3 seconds, remove the status message
                setTimeout(() => {
                    statusDiv.remove();
                }, 3000);
            } catch (error) {
                console.error('Error scanning ZIP:', error);
            }
        });
    }

    // Split PDF toggle
    const splitPdfCheckbox = document.getElementById('split_pdf');
    const splitOptionsDiv = document.getElementById('split_options');

    if (splitPdfCheckbox && splitOptionsDiv) {
        // Check if the checkbox is already checked (it should be by default)
        if (splitPdfCheckbox.checked) {
            splitOptionsDiv.style.display = 'block';
        } else {
            splitOptionsDiv.style.display = 'none';
        }

        splitPdfCheckbox.addEventListener('change', function() {
            if (this.checked) {
                splitOptionsDiv.style.display = 'block';
            } else {
                splitOptionsDiv.style.display = 'none';
            }
        });
    }

    // Category include/exclude toggles
    const categoryCheckboxes = document.querySelectorAll('input[name="include_categories"]');
    if (categoryCheckboxes.length > 0) {
        // Make sure at least one category is always selected
        categoryCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', function() {
                // Count how many are checked
                const checkedCount = document.querySelectorAll('input[name="include_categories"]:checked').length;

                // If none are checked, re-check the current one
                if (checkedCount === 0) {
                    this.checked = true;
                    alert('At least one file category must be selected.');
                }
            });
        });
    }

    // Add a method to create the copy logs button
    function addCopyLogsButton() {
        // Check if the button already exists
        if (document.getElementById('copy-logs-button')) {
            return;
        }

        const terminalOutput = document.getElementById('terminal-output');
        if (!terminalOutput) return;

        // Create a button container
        const buttonContainer = document.createElement('div');
        buttonContainer.className = 'terminal-controls';
        buttonContainer.innerHTML = `
            <button id="copy-logs-button" class="copy-logs-button">
                <i class="copy-icon"></i>
                Copy Logs
            </button>
            <span id="copy-status" class="copy-status"></span>
        `;

        // Insert before the terminal
        terminalOutput.parentNode.insertBefore(buttonContainer, terminalOutput);

        // Add event listener to the button
        document.getElementById('copy-logs-button').addEventListener('click', function() {
            const terminalText = Array.from(terminalOutput.querySelectorAll('.terminal-line'))
                .map(line => line.textContent)
                .join('\n');

            if (navigator.clipboard) {
                navigator.clipboard.writeText(terminalText)
                    .then(() => {
                        const statusEl = document.getElementById('copy-status');
                        statusEl.textContent = 'Copied!';
                        statusEl.className = 'copy-status success';
                        setTimeout(() => {
                            statusEl.textContent = '';
                        }, 2000);
                    })
                    .catch(err => {
                        console.error('Error copying text: ', err);
                        const statusEl = document.getElementById('copy-status');
                        statusEl.textContent = 'Copy failed';
                        statusEl.className = 'copy-status error';
                    });
            } else {
                // Fallback for browsers that don't support clipboard API
                const textarea = document.createElement('textarea');
                textarea.value = terminalText;
                textarea.style.position = 'fixed';  // Prevent scrolling to the bottom
                document.body.appendChild(textarea);
                textarea.select();

                try {
                    document.execCommand('copy');
                    const statusEl = document.getElementById('copy-status');
                    statusEl.textContent = 'Copied!';
                    statusEl.className = 'copy-status success';
                    setTimeout(() => {
                        statusEl.textContent = '';
                    }, 2000);
                } catch (err) {
                    console.error('Fallback: Error copying text', err);
                    const statusEl = document.getElementById('copy-status');
                    statusEl.textContent = 'Copy failed';
                    statusEl.className = 'copy-status error';
                }

                document.body.removeChild(textarea);
            }
        });
    }

    // Add the copy logs button as soon as we start seeing terminal output
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList' &&
                document.querySelector('.terminal-output .terminal-line')) {
                addCopyLogsButton();
            }
        });
    });

    const terminalOutput = document.getElementById('terminal-output');
    if (terminalOutput) {
        observer.observe(terminalOutput, { childList: true });
    }

    // Update the event handler for process completion to include log download button
    function addLogDownloadButton(logsUrl) {
        if (!logsUrl) return;

        // Create log download button
        const terminalOutput = document.getElementById('terminal-output');
        if (!terminalOutput) return;

        const logButtonContainer = document.createElement('div');
        logButtonContainer.className = 'log-download-container';
        logButtonContainer.innerHTML = `
            <a href="${logsUrl}" class="log-download-button">
                <i class="log-icon"></i>
                Download Logs
            </a>
        `;

        // Add after the terminal
        terminalOutput.after(logButtonContainer);
    }

    // Form submission with progress tracking
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();

            const formData = new FormData(form);

            // Show progress container and terminal
            const progressContainer = document.getElementById('progress-container');
            const terminalOutput = document.getElementById('terminal-output');
            const progressBar = document.getElementById('progress-bar');
            const progressText = document.getElementById('progress-text');

            progressContainer.style.display = 'block';
            terminalOutput.style.display = 'block';

            // Clear previous terminal output
            terminalOutput.innerHTML = '';

            // Add initial message
            addTerminalLine('Starting to process the project...', 'info');

            // First submit the form to start processing
            fetch('/upload-async', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    addTerminalLine('Error: ' + data.error, 'error');
                    return;
                }

                const taskId = data.task_id;
                addTerminalLine('Task started with ID: ' + taskId, 'info');

                // Setup SSE for progress updates
                const eventSource = new EventSource('/progress?task_id=' + taskId);

                eventSource.onmessage = function(event) {
                    const data = JSON.parse(event.data);

                    // Ignore ping messages
                    if (data.ping) return;

                    if (data.progress !== undefined) {
                        // Update progress bar
                        progressBar.style.width = data.progress + '%';
                    }

                    if (data.message) {
                        progressText.textContent = data.message;
                    }

                    if (data.log) {
                        // Add log to terminal
                        addTerminalLine(data.log, data.type || 'info');
                    }

                    // If process is complete, close connection and show download buttons
                    if (data.complete) {
                        eventSource.close();
                        addTerminalLine('Processing complete!', 'info');

                        // Handle download buttons
                        if (data.download_url) {
                            // Create download button for output files
                            const downloadContainer = document.createElement('div');
                            downloadContainer.className = 'download-container';
                            downloadContainer.innerHTML = `
                                <a href="${data.download_url}" class="download-button">
                                    <i class="download-icon"></i>
                                    Download Files
                                </a>
                                <p class="download-note">Your files are ready for download</p>
                            `;
                            document.querySelector('.progress-container').after(downloadContainer);

                            addTerminalLine('Download button added. Click to download your files.', 'info');

                            // Auto-download after a delay
                            setTimeout(() => {
                                window.location.href = data.download_url;
                                addTerminalLine('Auto-downloading files...', 'info');
                            }, 2000);
                        }

                        // Add log download button if logs are available
                        if (data.logs_url) {
                            addLogDownloadButton(data.logs_url);
                            addTerminalLine('Log file available for download.', 'info');
                        }
                    }
                };

                eventSource.onerror = function() {
                    addTerminalLine('Error in event stream. Please check server logs.', 'error');
                    eventSource.close();
                };
            })
            .catch(error => {
                addTerminalLine('Error submitting form: ' + error.message, 'error');
            });
        });
    }
});

// Function to add a line to the terminal output
function addTerminalLine(text, type = 'info') {
    const terminal = document.getElementById('terminal-output');
    if (!terminal) return;

    const line = document.createElement('p');
    line.className = `terminal-line terminal-${type}`;

    // Format timestamp
    const now = new Date();
    const timestamp = now.toLocaleTimeString();

    line.textContent = `[${timestamp}] ${text}`;
    terminal.appendChild(line);

    // Auto-scroll to bottom
    terminal.scrollTop = terminal.scrollHeight;
}