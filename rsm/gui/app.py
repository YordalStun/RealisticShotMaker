"""Application entry point."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication

STYLE = """
QWidget { font-size: 10pt; }
QMainWindow, QWidget#Central { background: #1b1917; }
QToolBar { background: #211e1b; border: none; padding: 4px; spacing: 6px; }
QGroupBox { border: 1px solid #36312c; border-radius: 6px; margin-top: 14px; padding: 10px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #d9a56b; font-weight: 600; }
QTabWidget::pane { border: 1px solid #36312c; border-radius: 6px; }
QTabBar::tab { background: #24211e; color: #b9ada0; padding: 7px 14px; border-top-left-radius: 6px;
               border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background: #2f2a25; color: #f1e7da; }
QPushButton { background: #2f2a25; border: 1px solid #453d35; border-radius: 6px; padding: 6px 14px; color: #efe5d8; }
QPushButton:hover { border-color: #d9a56b; }
QPushButton:disabled { color: #7d7368; }
QPushButton#Primary { background: #c47a35; border-color: #c47a35; color: #1b1208; font-weight: 700; }
QPushButton#Primary:hover { background: #d98c43; }
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { background: #24211e; border: 1px solid #3e3731;
               border-radius: 5px; padding: 3px 6px; color: #efe5d8; }
QSlider::groove:horizontal { height: 4px; background: #3e3731; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -6px 0; border-radius: 7px; background: #d9a56b; }
QSlider::sub-page:horizontal { background: #a8692d; border-radius: 2px; }
QTableWidget { background: #201d1a; gridline-color: #36312c; border: 1px solid #36312c; border-radius: 6px; }
QHeaderView::section { background: #24211e; color: #b9ada0; border: none; padding: 5px; }
QProgressBar { background: #24211e; border: 1px solid #3e3731; border-radius: 5px; text-align: center;
               color: #efe5d8; }
QProgressBar::chunk { background: #c47a35; border-radius: 4px; }
QLabel#Caption { color: #9d9184; }
QLabel#PathLabel { color: #b9ada0; }
QStatusBar { background: #211e1b; color: #b9ada0; }
QScrollArea { border: none; }
"""


def main(argv=None):
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv or sys.argv)
    app.setApplicationName("RealisticShotMaker")
    app.setOrganizationName("RealisticShotMaker")
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#1b1917"))
    pal.setColor(QPalette.WindowText, QColor("#efe5d8"))
    pal.setColor(QPalette.Base, QColor("#24211e"))
    pal.setColor(QPalette.AlternateBase, QColor("#2a2622"))
    pal.setColor(QPalette.Text, QColor("#efe5d8"))
    pal.setColor(QPalette.Button, QColor("#2f2a25"))
    pal.setColor(QPalette.ButtonText, QColor("#efe5d8"))
    pal.setColor(QPalette.Highlight, QColor("#c47a35"))
    pal.setColor(QPalette.HighlightedText, QColor("#1b1208"))
    pal.setColor(QPalette.ToolTipBase, QColor("#2f2a25"))
    pal.setColor(QPalette.ToolTipText, QColor("#efe5d8"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    from .main_window import MainWindow
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
