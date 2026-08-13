"""
Popular Frequency Band Presets & User Custom Presets Panel.
Provides instant one-click tuning to Wi-Fi 2.4/5GHz, Cellular, Ham, ISM, Aviation, FM, etc.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QListWidget,
    QListWidgetItem, QPushButton, QLineEdit, QLabel, QInputDialog, QMessageBox
)
from PySide6.QtCore import Signal
from utils.presets import (
    PRESETS, format_frequency, load_user_presets, save_user_presets,
)


class PresetPanelWidget(QWidget):
    """Preset selection and custom band manager panel."""

    preset_selected = Signal(float, float, str)  # (start_hz, stop_hz, name)

    def __init__(self, parent=None):
        super().__init__(parent)
        #: Set by MainWindow so "Save Custom Preset" captures the range that is
        #: actually on screen rather than a hard-coded band.
        self.current_range_provider = None
        self.user_presets = load_user_presets()
        self.preset_list_data = self.user_presets + list(PRESETS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Preset Search & List Box
        # -------------------------------------------------------------
        box_presets = QGroupBox("Frequency Band Presets")
        layout_p = QVBoxLayout(box_presets)

        # Search Bar
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("🔍 Search presets (e.g. WiFi, Ham, 5G, ISM)...")
        self.edit_search.textChanged.connect(self.filter_presets)
        layout_p.addWidget(self.edit_search)

        # List Widget
        self.list_widget = QListWidget()
        self.list_widget.setToolTip("Double click a preset to apply sweep range instantly")
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.currentItemChanged.connect(self.on_current_item_changed)
        layout_p.addWidget(self.list_widget)

        # Details Display
        self.lbl_details = QLabel("Select a preset to view details.")
        self.lbl_details.setWordWrap(True)
        self.lbl_details.setStyleSheet("color: #00e5ff; font-weight: 500; font-size: 12px; padding: 4px;")
        layout_p.addWidget(self.lbl_details)

        # Action Buttons
        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("Apply Selected Preset")
        self.btn_apply.setObjectName("accentButton")
        self.btn_apply.clicked.connect(self.apply_selected_preset)
        btn_row.addWidget(self.btn_apply)

        self.btn_add_custom = QPushButton("+ Save Custom Preset")
        self.btn_add_custom.setToolTip("Save the current sweep range as a reusable preset")
        self.btn_add_custom.clicked.connect(self.save_custom_preset)
        btn_row.addWidget(self.btn_add_custom)

        layout_p.addLayout(btn_row)

        self.btn_delete_custom = QPushButton("Delete Selected Custom Preset")
        self.btn_delete_custom.setToolTip("Remove a preset you previously saved")
        self.btn_delete_custom.clicked.connect(self.delete_selected_preset)
        layout_p.addWidget(self.btn_delete_custom)

        layout.addWidget(box_presets)

        self.populate_presets()

    def populate_presets(self, filter_text: str = ""):
        """Populate preset items in list widget."""
        self.list_widget.clear()
        filter_text = filter_text.lower()

        for item in self.preset_list_data:
            name = item["name"]
            cat = item.get("category", "General")
            if filter_text in name.lower() or filter_text in cat.lower() or filter_text in item.get("description", "").lower():
                display_text = f"[{cat}] {name}"
                widget_item = QListWidgetItem(display_text)
                widget_item.setData(100, item)  # Store dict metadata
                self.list_widget.addItem(widget_item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def filter_presets(self, text: str):
        """Filter presets based on search query."""
        self.populate_presets(text)

    def on_current_item_changed(self, current: QListWidgetItem, previous):
        """Update details label when list selection changes."""
        if not current:
            self.lbl_details.setText("")
            return
        data = current.data(100)
        start_str = format_frequency(data["start_freq"])
        stop_str = format_frequency(data["stop_freq"])
        span_str = format_frequency(data["stop_freq"] - data["start_freq"])
        desc = data.get("description", "")

        self.lbl_details.setText(
            f"<b>{data['name']}</b><br>"
            f"Range: {start_str} - {stop_str} (Span: {span_str})<br>"
            f"<i>{desc}</i>"
        )

    def on_item_double_clicked(self, item: QListWidgetItem):
        """Double click handler to apply preset."""
        self.apply_selected_preset()

    def apply_selected_preset(self):
        """Emit selected preset frequency values."""
        current = self.list_widget.currentItem()
        if current:
            data = current.data(100)
            self.preset_selected.emit(data["start_freq"], data["stop_freq"], data["name"])

    def save_custom_preset(self):
        """Save the sweep range currently on screen as a named preset."""
        if self.current_range_provider is None:
            QMessageBox.warning(self, "Unavailable",
                                "The current sweep range is not available.")
            return

        start_hz, stop_hz = self.current_range_provider()
        if not (start_hz > 0 and stop_hz > start_hz):
            QMessageBox.warning(
                self, "Invalid Range",
                "The current sweep range is not valid, so there is nothing to save."
            )
            return

        name, ok = QInputDialog.getText(
            self, "Save Custom Preset",
            f"Name this preset\n({format_frequency(start_hz)} - {format_frequency(stop_hz)}):"
        )
        if not (ok and name.strip()):
            return
        name = name.strip()

        entry = {
            "name": name,
            "category": "User Presets",
            "start_freq": float(start_hz),
            "stop_freq": float(stop_hz),
            "description": (
                f"Saved range {format_frequency(start_hz)} - {format_frequency(stop_hz)}"
            ),
        }

        # Replace an existing preset of the same name rather than duplicating it.
        self.user_presets = [p for p in self.user_presets if p.get("name") != name]
        self.user_presets.insert(0, entry)
        self._persist_and_refresh(f"Custom preset '{name}' saved.")

    def delete_selected_preset(self):
        """Delete the selected preset, if it is one of the user's own."""
        current = self.list_widget.currentItem()
        if not current:
            return
        data = current.data(100)
        name = data.get("name")
        if data.get("category") != "User Presets":
            QMessageBox.information(
                self, "Built-in Preset",
                f"'{name}' is a built-in band and cannot be deleted."
            )
            return
        self.user_presets = [p for p in self.user_presets if p.get("name") != name]
        self._persist_and_refresh(f"Deleted custom preset '{name}'.")

    def _persist_and_refresh(self, message: str):
        """Write user presets to disk and rebuild the list."""
        self.preset_list_data = self.user_presets + list(PRESETS)
        self.populate_presets(self.edit_search.text())
        ok, detail = save_user_presets(self.user_presets)
        if ok:
            QMessageBox.information(self, "Presets Updated", f"{message}\n\nStored in:\n{detail}")
        else:
            QMessageBox.warning(
                self, "Could Not Save",
                f"{message}\n\nThe change is active for this session but could "
                f"not be written to disk:\n{detail}"
            )
