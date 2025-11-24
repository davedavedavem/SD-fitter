print("Program is running. Please be patient while Python libraries are unpackaged.")

import sys
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QRadioButton,
    QCheckBox,
    QFileDialog,
    QLineEdit,
    QButtonGroup,
    QMessageBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
)
from PyQt5.QtGui import QIcon
import os
import traceback
from fitter import fitter


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # finds temp file for icon path
        if getattr(sys, "frozen", False):
            application_path = sys._MEIPASS
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))

        self.setWindowTitle("Semi-derivative Fitter")
        icon_path = os.path.join(application_path, "icon.ico")
        self.setWindowIcon(QIcon(icon_path))
        self.setGeometry(200, 200, 600, 400)

        self.input_file = None
        self.output_dir = None

        # UI setup
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Input format dropdown
        self.format_dropdown = QComboBox()
        self.format_dropdown.addItems(
            [
                "Template CSV file",
                "CH Instruments text file",
                "Nova ASCII export",
                "PSTrace CSV export",
            ]
        )
        layout.addWidget(QLabel("Select input data format:"))
        layout.addWidget(self.format_dropdown)

        # File selection
        self.file_button = QPushButton("Select input file")
        self.file_button.clicked.connect(self.select_file)
        self.file_label = QLabel("No file selected")
        layout.addWidget(self.file_button)
        layout.addWidget(self.file_label)

        # Output directory
        self.dir_button = QPushButton("Select output directory")
        self.dir_button.clicked.connect(self.select_directory)
        self.dir_label = QLabel("No directory selected")
        layout.addWidget(self.dir_button)
        layout.addWidget(self.dir_label)

        # Optional output name
        layout.addWidget(QLabel("Optional output name:"))
        self.output_name_input = QLineEdit()
        layout.addWidget(self.output_name_input)

        # Capacitance model group
        cap_group = QGroupBox("Capacitance model")
        cap_layout = QVBoxLayout()
        self.cap_button_group = QButtonGroup(self)
        for i, model in enumerate(["Piecewise CPE", "None"]):
            btn = QRadioButton(model)
            if i == 0:
                btn.setChecked(True)
            self.cap_button_group.addButton(btn)
            cap_layout.addWidget(btn)
        cap_group.setLayout(cap_layout)
        layout.addWidget(cap_group)

        # Peak picking group
        peak_group = QGroupBox("Peak detection")
        peak_layout = QVBoxLayout()
        self.peak_button_group = QButtonGroup(self)
        for i, model in enumerate(["Automatic", "Manual"]):
            btn = QRadioButton(model)
            if i == 0:
                btn.setChecked(True)
            self.peak_button_group.addButton(btn)
            peak_layout.addWidget(btn)
        peak_group.setLayout(peak_layout)
        layout.addWidget(peak_group)

        # Misc options
        misc_group = QGroupBox("Misc.")
        misc_layout = QVBoxLayout()
        self.misc_check1 = QCheckBox("Exponential background electrolysis")
        self.misc_check2 = QCheckBox(".csv export")
        self.misc_check3 = QCheckBox(".xlsx export")
        misc_layout.addWidget(self.misc_check1)
        misc_layout.addWidget(self.misc_check2)
        misc_layout.addWidget(self.misc_check3)
        misc_group.setLayout(misc_layout)
        layout.addWidget(misc_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.run_analysis)
        btn_layout.addWidget(self.run_button)

        self.about_button = QPushButton("About")
        self.about_button.clicked.connect(self.show_about)
        btn_layout.addWidget(self.about_button)
        layout.addLayout(btn_layout)

    def select_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select input file")
        if fname:
            self.input_file = fname
            self.file_label.setText(fname)

    def select_directory(self):
        dname = QFileDialog.getExistingDirectory(self, "Select output directory")
        if dname:
            self.output_dir = dname
            self.dir_label.setText(dname)

    def run_analysis(self):
        if not self.input_file or not self.output_dir:
            QMessageBox.warning(
                self,
                "Missing input",
                "Please select both an input file and output directory.",
            )
            return

        # Build dictionary for fitter
        userinput_dict = {
            "data_format": self.format_dropdown.currentText(),
            "filename": self.input_file,
            "output_dir": self.output_dir,
            "name": self.output_name_input.text(),
            "capacitance_model": self.cap_button_group.checkedButton().text(),
            "peak_detection": self.peak_button_group.checkedButton().text(),
            "bkg_exp": self.misc_check1.isChecked(),
            "csv": self.misc_check2.isChecked(),
            "xlsx": self.misc_check3.isChecked(),
        }

        # ask for scan rate in case of PSTrace data
        if self.format_dropdown.currentText() == "PSTrace CSV export":
            try:
                scan_rate, alert = QInputDialog.getText(
                    QWidget(), "Input text", "Please input scan rate (V/s):"
                )
                userinput_dict.update({"scan_rate": float(scan_rate)})
            except:
                alert = QMessageBox()
                alert.setWindowTitle("Error")
                alert.setText(
                    "Scan rate input required for data from PSTrace CSV export"
                )
                alert.exec_()
                return

        try:
            result = fitter(userinput_dict)
            QMessageBox.information(self, "Success", str(result))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            traceback.print_exc()

    def show_about(self):
        QMessageBox.information(
            self,
            "About",
            "Version 1.1.0 (Released 24/11/2025)<br/>"
            + "Semi-derivative Fitter was created by David S. Macedo and Conor F. Hogan.<br/><br/>"
            + "Source code and additional documentation can be found at <a href='www.github.com/davedavedavem/SD-fitter'>www.github.com/davedavedavem/SD-fitter</a><br/><br/>",
        )


if __name__ == "__main__":

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("icon.ico"))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
