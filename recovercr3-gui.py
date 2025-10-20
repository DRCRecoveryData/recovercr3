import sys
import os
import platform
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QPushButton, QSpinBox,
    QCheckBox, QTextEdit, QFileDialog, QGroupBox, QProgressBar
)
from PyQt6.QtCore import QProcess, QStandardPaths, QFileInfo, pyqtSignal, QTimer, QCoreApplication, QIODevice

# --- Configuration ---
# Set the path to the recovercr3.py script. 
# This assumes recovercr3.py is in the same directory as this GUI script.
FIXED_SCRIPT_PATH = str(Path(__file__).parent / "recovercr3.py") 
# Determine the command to execute Python 
PYTHON_COMMAND = "python" if platform.system() == "Windows" else "python3" 

class CarvingApp(QMainWindow):
    # Signal used for safely updating the progress bar from QProcess handlers
    progress_signal = pyqtSignal(int)
    
    # Persistent buffer for partial stdout lines
    _stdout_buffer = ""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CR3 File Carving Tool")
        self.setGeometry(100, 100, 700, 750) 
        self.setStyleSheet(self._get_dark_stylesheet())

        # QProcess object to run the script asynchronously
        self.process = QProcess(self)
        
        # Connect handlers for process output and completion
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)
        
        # Connect the custom signal to the progress update method
        self.progress_signal.connect(self._set_progress)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        # --- UI Setup ---
        self._setup_settings_form()
        self._setup_progress_area() 
        self._setup_controls()
        self._setup_logging_area()
        
        # Initial status
        self._set_progress(0)
        
        # Initial check for the recovercr3.py script
        if not Path(FIXED_SCRIPT_PATH).is_file():
            self.log_area.append(f"<span style='color: red;'>ERROR: Required script 'recovercr3.py' not found at: {FIXED_SCRIPT_PATH}</span>")


    def _get_dark_stylesheet(self):
        """Returns a modern dark mode CSS-like stylesheet."""
        return """
            QMainWindow, QWidget { 
                background-color: #2e2e2e; 
                color: #e0e0e0; 
                font-size: 10pt;
            }
            QLabel { color: #e0e0e0; }

            QGroupBox { 
                font-weight: bold; 
                border: 1px solid #4a4a4a; 
                border-radius: 5px; 
                margin-top: 10px;
                padding-top: 10px;
            }
            
            /* Inputs */
            QLineEdit, QTextEdit, QSpinBox {
                background-color: #3e3e3e; 
                color: #e0e0e0;
                border: 1px solid #5a5a5a;
                padding: 5px;
                border-radius: 4px;
            }
            
            /* Buttons */
            QPushButton {
                background-color: #007bff; 
                color: white; 
                border: none; 
                padding: 8px 15px; 
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0056b3; }
            QPushButton:pressed { background-color: #003d7a; }
            
            /* Main Start Button (larger) */
            QPushButton#StartButton {
                font-size: 12pt;
                padding: 15px;
                border-radius: 6px;
                background-color: #007bff;
            }
            QPushButton#StartButton:hover { background-color: #0056b3; }
            QPushButton:disabled { background-color: #4a4a4a; color: #999999; }
            
            /* Log Area */
            QTextEdit#LogArea { 
                background-color: #1e1e1e;
                color: #e0e0e0; 
                font-family: monospace;
                border: 1px solid #4a4a4a;
            }
            
            /* Progress Bar */
            QProgressBar {
                border: 1px solid #5a5a5a;
                border-radius: 5px;
                text-align: center;
                background-color: #3e3e3e;
                color: #e0e0e0;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #007bff; /* Blue progress fill */
                border-radius: 5px;
            }
        """

    def _setup_settings_form(self):
        settings_group = QGroupBox("Carving Configuration")
        form_layout = QFormLayout(settings_group)
        form_layout.setSpacing(15)

        # --- Input File ---
        self.input_file_edit = QLineEdit()
        self.input_browse_btn = QPushButton("Browse")
        self.input_browse_btn.clicked.connect(self._browse_input)
        input_layout = self._create_h_layout(self.input_file_edit, self.input_browse_btn)
        form_layout.addRow("Input Dump File:", input_layout)

        # --- Output Directory ---
        default_out_dir = str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)) / "Carved")
        self.output_dir_edit = QLineEdit(default_out_dir)
        self.output_browse_btn = QPushButton("Browse")
        self.output_browse_btn.clicked.connect(self._browse_output)
        
        output_layout = self._create_h_layout(self.output_dir_edit, self.output_browse_btn)
        form_layout.addRow("Output Folder (Absolute Path):", output_layout) 


        # --- Carving Options ---
        self.ext_edit = QLineEdit("CR3")
        form_layout.addRow("File Extension:", self.ext_edit)
        
        self.num_width_spin = QSpinBox()
        self.num_width_spin.setRange(1, 10)
        self.num_width_spin.setValue(4) 
        self.num_width_spin.setToolTip("Filename numbering width (e.g., 4 for 0001).")
        form_layout.addRow("Number Width:", self.num_width_spin)

        self.max_chunks_spin = QSpinBox()
        self.max_chunks_spin.setRange(0, 9999) 
        self.max_chunks_spin.setValue(0)
        self.max_chunks_spin.setToolTip("Set to 0 to use the Last Chunk Name option.")
        form_layout.addRow("Max Chunks (0=Default):", self.max_chunks_spin)
        
        self.last_chunk_edit = QLineEdit("mdat")
        self.last_chunk_edit.setToolTip("Name of the final CR3 atom (e.g., 'mdat'). Used if Max Chunks is 0.")
        form_layout.addRow("Last Chunk Name:", self.last_chunk_edit)
        
        self.verbose_check = QCheckBox()
        self.verbose_check.setStyleSheet("QCheckBox { spacing: 10px; }") 
        form_layout.addRow("Verbose Logging (-v):", self.verbose_check)

        self.layout.addWidget(settings_group)

    def _setup_progress_area(self):
        # Progress Bar
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('0%')
        progress_layout.addWidget(self.progress_bar)
        self.layout.addWidget(progress_group)


    def _setup_controls(self):
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        self.start_button = QPushButton("START CARVING")
        self.start_button.setObjectName("StartButton") 
        self.start_button.clicked.connect(self._start_carving)
        
        self.cancel_button = QPushButton("CANCEL")
        self.cancel_button.clicked.connect(self._cancel_carving)
        self.cancel_button.setEnabled(False) # Disable initially

        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.cancel_button)
        self.layout.addWidget(control_widget)

    def _setup_logging_area(self):
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_area = QTextEdit()
        self.log_area.setObjectName("LogArea") 
        self.log_area.setReadOnly(True)
        self.log_area.setText("Ready. Select input file and click START CARVING.")
        
        log_layout.addWidget(self.log_area)
        self.layout.addWidget(log_group)

    def _create_h_layout(self, *widgets):
        """Helper to create a horizontal box layout for form fields"""
        h_widget = QWidget()
        h_layout = QHBoxLayout(h_widget)
        h_layout.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            h_layout.addWidget(widget)
        return h_widget

    # --- File/Dir Browsing ---
    def _browse_input(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Input Dump File", 
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.HomeLocation), 
            "All Files (*);;Disk Images (*.dd *.img *.bin)"
        )
        if file_name:
            self.input_file_edit.setText(file_name)
            
            # Auto-set output directory to include the /Carved subfolder near the input file
            input_dir = Path(file_name).parent
            output_carved_path = str(input_dir / "Carved")
            self.output_dir_edit.setText(output_carved_path)

    def _browse_output(self):
        dir_name = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_dir_edit.text())
        if dir_name:
            self.output_dir_edit.setText(dir_name)

    # --- Process Control ---
    def _start_carving(self):
        self.log_area.clear()
        self._set_progress(0)
        self._stdout_buffer = "" # Reset buffer
        
        input_path = self.input_file_edit.text()
        output_path = self.output_dir_edit.text()

        # Basic Validation
        if not Path(input_path).is_file():
            self.log_area.append(f"<span style='color: red;'>ERROR: Input file not found or path is invalid: {input_path}</span>")
            return
        if not output_path:
            self.log_area.append("<span style='color: red;'>ERROR: Output directory must be specified.</span>")
            return
        if not Path(FIXED_SCRIPT_PATH).is_file():
            self.log_area.append(f"<span style='color: red;'>ERROR: Carving script 'recovercr3.py' not found at: {FIXED_SCRIPT_PATH}</span>")
            return

        # Build command line arguments
        args = [
            FIXED_SCRIPT_PATH,
            "--input", input_path,
            "--outdir", output_path, 
            "--ext", self.ext_edit.text(), 
            "--numwidth", str(self.num_width_spin.value()) 
        ]

        max_chunks = self.max_chunks_spin.value()
        if max_chunks > 0:
            args.extend(["--maxchunks", str(max_chunks)])
        else:
            last_chunk = self.last_chunk_edit.text().strip()
            if last_chunk:
                args.extend(["--lastchunk", last_chunk])

        if self.verbose_check.isChecked():
            args.append("-v")

        # Display command and start process
        command_line = f"{PYTHON_COMMAND} " + " ".join(args)
        self.log_area.append(f"<span style='color: yellow;'>Starting command:</span> {command_line}\n---")
        
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        
        # Start the process using the determined python command
        self.process.start(PYTHON_COMMAND, args)

    def _cancel_carving(self):
        if self.process.state() == QProcess.ProcessState.Running:
            self.log_area.append("<span style='color: orange;'>Process terminated by user (SIGKILL).</span>")
            self.process.kill()
            self.start_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.progress_signal.emit(0) # Reset progress

    # --- Process Output Handlers ---
    def _handle_stdout(self):
        """
        Reads stdout from the background process, extracts the progress marker, 
        and updates the progress bar via a signal. This is the critical fixed part.
        """
        # Read all available data and decode it, adding it to the buffer
        data = self.process.readAllStandardOutput().data().decode(errors='ignore')
        self._stdout_buffer += data
        
        # Split the buffer into lines. Only process fully received lines.
        # The last element will be a partial line or empty, which stays in the buffer.
        lines = self._stdout_buffer.split('\n')
        self._stdout_buffer = lines.pop() # Keep the last (partial) line

        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check for the specific progress marker
            if line.startswith("PROGRESS:"):
                try:
                    # Isolate the value after the colon
                    progress_value_str = line.split(':', 1)[1].strip()
                    # Convert to integer
                    progress = int(float(progress_value_str)) 
                    # Emit signal to safely update the progress bar in the GUI thread
                    self.progress_signal.emit(progress) 
                except (ValueError, IndexError):
                    # Log failure to parse progress line (to stderr/console for debugging)
                    print(f"GUI: Failed to parse progress line: {line}", file=sys.stderr)
                continue
            
            # Append any other non-progress stdout lines to the log area
            self.log_area.append(line)
            
        # Scroll to the bottom after processing all full lines
        self.log_area.ensureCursorVisible()


    def _handle_stderr(self):
        """Reads stderr from the background process and logs it."""
        # Read all data from stderr (where the script's logging output goes)
        data = self.process.readAllStandardError().data().decode(errors='ignore').strip()
        if not data:
            return

        for line in data.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Color-code log output based on logging level markers
            color = "#e0e0e0" # Default
            if "[ERROR]" in line:
                color = "red"
            elif "[WARNING]" in line:
                color = "orange"
            elif "[INFO]" in line:
                color = "lightgreen"
            elif "[DEBUG]" in line:
                color = "#88aadd" 
                
            self.log_area.append(f"<span style='color: {color};'>{line}</span>")
            # Scroll to the bottom
            self.log_area.ensureCursorVisible()

    def _set_progress(self, value):
        """Slot to safely update the progress bar from a signal."""
        # Cap value to 100
        value = min(100, max(0, value))
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(f'{value}%')

    def _process_finished(self, exit_code, exit_status):
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        
        # Ensure 100% completion is shown unless there was a known failure
        if exit_code == 0:
             self.progress_signal.emit(100) 

        if exit_code == 0:
            self.log_area.append("\n<span style='color: lightgreen; font-weight: bold;'>--- Carving FINISHED successfully! ---</span>")
        else:
            self.log_area.append(f"\n<span style='color: red; font-weight: bold;'>--- Carving FAILED with exit code {exit_code}. Check log for errors. ---</span>")
            
        self.log_area.ensureCursorVisible()


if __name__ == '__main__':
    # Increase the maximum recursion depth for complex Qt processing if necessary
    # sys.setrecursionlimit(2000) 
    app = QApplication(sys.argv)
    window = CarvingApp()
    window.show()
    sys.exit(app.exec())
