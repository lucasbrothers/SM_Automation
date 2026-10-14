"""Explicit light controls keep OS dark palettes from obscuring query results."""
from pathlib import Path

LIGHT_CONTROLS = """
QTreeWidget, QListWidget, QAbstractItemView {
    background: #ffffff; color: #23344c;
    selection-background-color: #dceaff; selection-color: #172d48;
}
QMenu, QToolTip { background: #ffffff; color: #23344c; border: 1px solid #b9c9dc; }
QTableCornerButton::section, QAbstractScrollArea::corner { background: #edf2f8; border: none; }
QScrollBar:horizontal { background: #eaf0f8; height: 16px; margin: 0px; border: 1px solid #ccd8e8; }
QScrollBar:vertical { background: #eaf0f8; width: 16px; margin: 0px; border: 1px solid #ccd8e8; }
QScrollBar::handle:horizontal { background: #91abc9; min-width: 36px; border: 1px solid #6e8fb6; border-radius: 5px; }
QScrollBar::handle:vertical { background: #91abc9; min-height: 36px; border: 1px solid #6e8fb6; border-radius: 5px; }
QScrollBar::handle:hover { background: #7398c2; }
QScrollBar::handle:pressed { background: #567fac; }
QScrollBar::add-page, QScrollBar::sub-page { background: #eaf0f8; border: none; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; height: 0px; border: none; background: #eaf0f8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { width: 0px; height: 0px; border: none; background: #eaf0f8; }
QScrollBar::left-arrow, QScrollBar::right-arrow, QScrollBar::up-arrow, QScrollBar::down-arrow { width: 0px; height: 0px; border: none; background: #eaf0f8; }
QSlider::groove:horizontal { height: 6px; background: #eaf0f8; border: 1px solid #ccd8e8; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; margin: -5px 0px; background: #7398c2; border: 1px solid #567fac; border-radius: 6px; }
QSplitter::handle { background: #d6e0ee; }
"""

_CHECK_ICON = (Path(__file__).resolve().parent / "assets" / "check.svg").as_posix()
LIGHT_CONTROLS += """
QCheckBox::indicator { width:18px; height:18px; border:1px solid #91abc9; border-radius:3px; background:#ffffff; }
QCheckBox::indicator:unchecked { image:none; }
QCheckBox::indicator:hover { border:1px solid #2869df; background:#edf4ff; }
QCheckBox::indicator:checked { image:url("%s"); background:#2869df; border:1px solid #2869df; }
QCheckBox::indicator:disabled { border:1px solid #ccd8e8; background:#edf2f8; }
""" % _CHECK_ICON


def light_palette():
    """Native controls also need light colors when Windows uses a dark palette."""
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    colors = {"Window":"#f3f6fb", "WindowText":"#23344c", "Base":"#ffffff",
              "AlternateBase":"#f4f7fb", "Text":"#23344c", "Button":"#ffffff",
              "ButtonText":"#23344c", "Highlight":"#2869df", "HighlightedText":"#ffffff",
              "ToolTipBase":"#ffffff", "ToolTipText":"#23344c", "Light":"#ffffff",
              "Midlight":"#edf2f8", "Mid":"#b9c9dc", "Dark":"#91abc9", "Shadow":"#6e8fb6"}
    for name,color in colors.items(): palette.setColor(getattr(QPalette.ColorRole,name),QColor(color))
    for name in ("WindowText","Text","ButtonText"):
        palette.setColor(QPalette.ColorGroup.Disabled,getattr(QPalette.ColorRole,name),QColor("#7a889b"))
    return palette
