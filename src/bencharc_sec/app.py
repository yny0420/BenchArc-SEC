"""PySide6 desktop application for BenchArc SEC."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .core import (
    PlotSettings,
    PeakAreaResult,
    TraceData,
    detect_plot_rectangle,
    digitize_image,
    integrate_peak,
    read_trace,
    render_svg,
    sample_image_color,
    suggest_settings,
    with_normalized_axis,
)


DATA_SUFFIXES = {".txt", ".csv", ".tsv"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


@dataclass
class SECItem:
    path: Path
    kind: str
    trace: TraceData | None = None
    settings: PlotSettings | None = None
    svg: str = ""
    plot_bottom_left: tuple[int, int] | None = None
    plot_top_right: tuple[int, int] | None = None
    sampled_trace_color: str = "#858585"
    color_tolerance: float = 45.0


class ImageCanvas(QLabel):
    image_clicked = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(600, 420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #f4f4f4; border: 1px solid #d0d0d0;")
        self._original = QPixmap()
        self._displayed = QPixmap()
        self._offset = QPointF()
        self._marks: dict[str, tuple[int, int]] = {}

    def set_image(self, path: str | Path) -> None:
        self._original = QPixmap(str(path))
        if self._original.isNull():
            raise ValueError("Could not open the selected image.")
        self._marks.clear()
        self._refresh()

    def set_mark(self, name: str, point: tuple[int, int] | None) -> None:
        if point is None:
            self._marks.pop(name, None)
        else:
            self._marks[name] = point
        self.update()

    def _refresh(self) -> None:
        if self._original.isNull():
            return
        self._displayed = self._original.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._offset = QPointF(
            (self.width() - self._displayed.width()) / 2,
            (self.height() - self._displayed.height()) / 2,
        )
        self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._refresh()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f4f4f4"))
        if self._displayed.isNull():
            painter.end()
            return
        painter.drawPixmap(self._offset, self._displayed)
        colors = {
            "bottom_left": QColor("#D33F49"),
            "top_right": QColor("#2F6FAF"),
            "trace": QColor("#2AA876"),
        }
        for name, (image_x, image_y) in self._marks.items():
            point = self._to_widget(image_x, image_y)
            painter.setPen(QPen(colors.get(name, QColor("#D33F49")), 3))
            painter.drawLine(QPointF(point.x() - 10, point.y()), QPointF(point.x() + 10, point.y()))
            painter.drawLine(QPointF(point.x(), point.y() - 10), QPointF(point.x(), point.y() + 10))
        painter.end()

    def _to_widget(self, image_x: int, image_y: int) -> QPointF:
        scale_x = self._displayed.width() / self._original.width()
        scale_y = self._displayed.height() / self._original.height()
        return QPointF(
            self._offset.x() + image_x * scale_x,
            self._offset.y() + image_y * scale_y,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._displayed.isNull():
            return
        x = event.position().x() - self._offset.x()
        y = event.position().y() - self._offset.y()
        if not (0 <= x < self._displayed.width() and 0 <= y < self._displayed.height()):
            return
        image_x = round(x / self._displayed.width() * self._original.width())
        image_y = round(y / self._displayed.height() * self._original.height())
        self.image_clicked.emit(
            min(self._original.width() - 1, image_x),
            min(self._original.height() - 1, image_y),
        )


def _double_spin(minimum: float = -1_000_000, maximum: float = 1_000_000) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(4)
    widget.setSingleStep(0.5)
    widget.setKeyboardTracking(False)
    return widget


class BenchArcSECWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BenchArc SEC 0.2.4")
        self.resize(1320, 820)
        self.setAcceptDrops(True)

        self.items: list[SECItem] = []
        self.current_item_index = -1
        self.trace: TraceData | None = None
        self.current_svg = ""
        self.source_path: Path | None = None
        self.image_path: Path | None = None
        self.click_mode: str | None = None
        self.plot_bottom_left: tuple[int, int] | None = None
        self.plot_top_right: tuple[int, int] | None = None
        self.sampled_trace_color = "#858585"
        self._loading_controls = False
        self._switching_item = False

        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(120)
        self.render_timer.timeout.connect(self.update_preview)

        self._build_toolbar()
        self._build_help_menu()
        self._build_main_ui()
        self.statusBar().showMessage("Open a UNICORN TXT/CSV/TSV file or a chromatogram image.")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_data = QAction("Add data files", self)
        open_data.triggered.connect(self.open_data_dialog)
        toolbar.addAction(open_data)

        open_image = QAction("Add images", self)
        open_image.triggered.connect(self.open_image_dialog)
        toolbar.addAction(open_image)
        toolbar.addSeparator()

        apply_all = QAction("Apply settings to all", self)
        apply_all.triggered.connect(self.apply_current_settings_to_all)
        toolbar.addAction(apply_all)

        batch_export = QAction("Batch export", self)
        batch_export.triggered.connect(self.batch_export_dialog)
        toolbar.addAction(batch_export)
        toolbar.addSeparator()

        export_svg = QAction("Export SVG", self)
        export_svg.triggered.connect(self.export_svg)
        toolbar.addAction(export_svg)

        export_png = QAction("Export 600 dpi PNG", self)
        export_png.triggered.connect(self.export_png)
        toolbar.addAction(export_png)

    def _build_help_menu(self) -> None:
        help_menu = self.menuBar().addMenu("Help")

        guide_action = QAction("User Guide", self)
        guide_action.triggered.connect(self.show_user_guide)
        help_menu.addAction(guide_action)

        about_action = QAction("About BenchArc SEC", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def show_user_guide(self) -> None:
        QMessageBox.information(
            self,
            "BenchArc SEC User Guide",
            "1. Add one or more UNICORN TXT, CSV, or TSV files.\n"
            "2. Select a chromatogram in the Source list.\n"
            "3. Adjust axis limits, tick spacing, labels, and publication style.\n"
            "4. Optionally normalize the Y axis or subtract the visible baseline.\n"
            "5. For peak area, enter the start/end volume and enable Calculate and shade.\n"
            "6. Export the current figure as SVG/600 dpi PNG, or use Batch export.\n\n"
            "Image-derived curves are approximate; raw instrument data are preferred for quantitative work.\n\n"
            "Full guide: https://github.com/yny0420/BenchArc-SEC/blob/main/USER_GUIDE.md",
        )

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About BenchArc SEC",
            "BenchArc SEC 0.2.4\n\n"
            "Publication-ready size-exclusion chromatography figures.\n\n"
            "Copyright © 2026 Yang Yu. All rights reserved.\n"
            "https://github.com/yny0420/BenchArc-SEC",
        )

    def _build_main_ui(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        self.setCentralWidget(central)

        controls_container = QWidget()
        controls = QVBoxLayout(controls_container)
        controls.setContentsMargins(4, 4, 8, 4)
        controls.setSpacing(10)

        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)
        self.source_label = QLabel("No file loaded")
        self.source_label.setWordWrap(True)
        source_layout.addWidget(self.source_label)
        self.source_list = QListWidget()
        self.source_list.setMinimumHeight(100)
        self.source_list.currentRowChanged.connect(self.select_item)
        source_layout.addWidget(self.source_list)
        remove_source = QPushButton("Remove selected from batch")
        remove_source.clicked.connect(self.remove_selected_item)
        source_layout.addWidget(remove_source)
        controls.addWidget(source_group)

        self.image_group = self._build_image_group()
        self.image_group.setVisible(False)
        controls.addWidget(self.image_group)

        axis_group = QGroupBox("Axes")
        axis_form = QFormLayout(axis_group)
        self.x_min = _double_spin()
        self.x_max = _double_spin()
        self.y_min = _double_spin()
        self.y_max = _double_spin()
        self.x_major = _double_spin(0.0001)
        self.x_minor = _double_spin(0.0001)
        self.y_major = _double_spin(0.0001)
        self.y_minor = _double_spin(0.0001)
        self.x_label = QLineEdit("Elution volume (ml)")
        self.y_label = QLineEdit("UV 280 (mAU)")
        for label, widget in (
            ("X minimum", self.x_min),
            ("X maximum", self.x_max),
            ("Y minimum", self.y_min),
            ("Y maximum", self.y_max),
            ("X major tick", self.x_major),
            ("X minor tick", self.x_minor),
            ("Y major tick", self.y_major),
            ("Y minor tick", self.y_minor),
            ("X label", self.x_label),
            ("Y label", self.y_label),
        ):
            axis_form.addRow(label, widget)
        controls.addWidget(axis_group)

        style_group = QGroupBox("Publication style")
        style_form = QFormLayout(style_group)
        self.reference_preset = QPushButton("Apply bold gray preset")
        self.reference_preset.clicked.connect(self.apply_reference_preset)
        style_form.addRow(self.reference_preset)
        self.color_button = QPushButton("#858585")
        self.color_button.clicked.connect(self.choose_trace_color)
        self._set_color_button("#858585")
        self.trace_width = _double_spin(0.2, 30)
        self.axis_width = _double_spin(0.2, 20)
        self.tick_font = _double_spin(5, 80)
        self.label_font = _double_spin(5, 100)
        self.show_tick_labels = QCheckBox()
        self.show_tick_labels.setChecked(True)
        self.show_peak_label = QCheckBox()
        style_form.addRow("Trace color", self.color_button)
        style_form.addRow("Trace width", self.trace_width)
        style_form.addRow("Axis width", self.axis_width)
        style_form.addRow("Tick font size", self.tick_font)
        style_form.addRow("Axis label size", self.label_font)
        style_form.addRow("Show tick labels", self.show_tick_labels)
        style_form.addRow("Annotate main peak", self.show_peak_label)
        controls.addWidget(style_group)

        transform_group = QGroupBox("Data transformations")
        transform_form = QFormLayout(transform_group)
        self.smooth_window = QSpinBox()
        self.smooth_window.setRange(1, 999)
        self.smooth_window.setSingleStep(2)
        self.smooth_window.setValue(1)
        self.baseline_subtract = QCheckBox()
        self.normalization_mode = QComboBox()
        self.normalization_mode.addItem("Off", "none")
        self.normalization_mode.addItem("Visible maximum = 1", "maximum")
        self.normalization_mode.addItem("Selected peak = 1", "peak")
        self.normalization_peak_x = _double_spin()
        self.normalization_window = _double_spin(0.0001)
        self.normalization_window.setValue(0.5)
        transform_form.addRow("Smoothing window", self.smooth_window)
        transform_form.addRow("Subtract baseline", self.baseline_subtract)
        transform_form.addRow("Y-axis scaling", self.normalization_mode)
        transform_form.addRow("Reference peak near (ml)", self.normalization_peak_x)
        transform_form.addRow("Peak half-window (ml)", self.normalization_window)
        note = QLabel("Scaling changes display values only; original data remain unchanged. All transformations are recorded in SVG metadata.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        transform_form.addRow(note)
        controls.addWidget(transform_group)

        area_group = QGroupBox("Peak area")
        area_form = QFormLayout(area_group)
        self.show_area = QCheckBox()
        self.area_start = _double_spin()
        self.area_end = _double_spin()
        suggest_area = QPushButton("Set ±1 ml around main peak")
        suggest_area.clicked.connect(self.set_area_around_main_peak)
        self.area_result_label = QLabel("Peak-area calculation is off.")
        self.area_result_label.setWordWrap(True)
        self.area_result_label.setStyleSheet("color: #555;")
        area_form.addRow("Calculate and shade", self.show_area)
        area_form.addRow("Start (ml)", self.area_start)
        area_form.addRow("End (ml)", self.area_end)
        area_form.addRow(suggest_area)
        area_form.addRow(self.area_result_label)
        controls.addWidget(area_group)
        controls.addStretch(1)

        scroll = QScrollArea()
        self.controls_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls_container)
        scroll.setMinimumWidth(350)
        scroll.setMaximumWidth(430)
        layout.addWidget(scroll)

        self.svg_preview = QSvgWidget()
        self.svg_preview.setMinimumSize(700, 500)
        self.svg_preview.setStyleSheet("background: white; border: 1px solid #d0d0d0;")
        self.image_canvas = ImageCanvas()
        self.image_canvas.image_clicked.connect(self.handle_image_click)
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.svg_preview)
        self.preview_stack.addWidget(self.image_canvas)
        layout.addWidget(self.preview_stack, 1)

        self._connect_render_controls()
        self._apply_settings_to_controls(
            PlotSettings(0, 20, 0, 35, 2, 0.5, 5, 1)
        )

    def _build_image_group(self) -> QGroupBox:
        group = QGroupBox("Image digitization")
        layout = QVBoxLayout(group)
        explanation = QLabel(
            "Calibrate the plot rectangle, enter the visible axis limits below, "
            "then sample the chromatogram trace color. Image-derived data are marked approximate."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        auto_button = QPushButton("Auto-detect plot rectangle")
        auto_button.clicked.connect(self.auto_detect_plot)
        layout.addWidget(auto_button)
        buttons = QHBoxLayout()
        bottom_left = QPushButton("Set bottom-left")
        bottom_left.clicked.connect(lambda: self.set_click_mode("bottom_left"))
        top_right = QPushButton("Set top-right")
        top_right.clicked.connect(lambda: self.set_click_mode("top_right"))
        buttons.addWidget(bottom_left)
        buttons.addWidget(top_right)
        layout.addLayout(buttons)
        color_pick = QPushButton("Sample trace color from image")
        color_pick.clicked.connect(lambda: self.set_click_mode("trace"))
        layout.addWidget(color_pick)
        self.calibration_label = QLabel("Plot rectangle: not calibrated")
        self.calibration_label.setWordWrap(True)
        layout.addWidget(self.calibration_label)
        tolerance_row = QFormLayout()
        self.color_tolerance = QDoubleSpinBox()
        self.color_tolerance.setRange(1, 255)
        self.color_tolerance.setValue(45)
        tolerance_row.addRow("Color tolerance", self.color_tolerance)
        layout.addLayout(tolerance_row)
        extract = QPushButton("Extract curve and preview")
        extract.clicked.connect(self.extract_image_curve)
        layout.addWidget(extract)
        return_to_image = QPushButton("Return to calibration image")
        return_to_image.clicked.connect(lambda: self.preview_stack.setCurrentWidget(self.image_canvas))
        layout.addWidget(return_to_image)
        return group

    def _connect_render_controls(self) -> None:
        widgets = (
            self.x_min,
            self.x_max,
            self.y_min,
            self.y_max,
            self.x_major,
            self.x_minor,
            self.y_major,
            self.y_minor,
            self.trace_width,
            self.axis_width,
            self.tick_font,
            self.label_font,
            self.smooth_window,
            self.color_tolerance,
            self.normalization_peak_x,
            self.normalization_window,
            self.area_start,
            self.area_end,
        )
        for widget in widgets:
            widget.valueChanged.connect(self.schedule_preview)
        for widget in (self.x_label, self.y_label):
            widget.textChanged.connect(self.schedule_preview)
        for widget in (
            self.show_tick_labels,
            self.show_peak_label,
            self.baseline_subtract,
            self.show_area,
        ):
            widget.toggled.connect(self.schedule_preview)
        self.normalization_mode.currentIndexChanged.connect(self.normalization_changed)
        self.normalization_changed()

    def schedule_preview(self) -> None:
        if not self._loading_controls and self.trace is not None:
            self.render_timer.start()

    def _update_normalization_controls(self) -> None:
        peak_mode = self.normalization_mode.currentData() == "peak"
        self.normalization_peak_x.setEnabled(peak_mode)
        self.normalization_window.setEnabled(peak_mode)

    def normalization_changed(self) -> None:
        self._update_normalization_controls()
        if self._loading_controls:
            return
        mode = self.normalization_mode.currentData()
        self._loading_controls = True
        try:
            if mode == "none":
                if self.trace is not None:
                    suggested = suggest_settings(self.trace)
                    self.y_min.setValue(suggested.y_min)
                    self.y_max.setValue(suggested.y_max)
                    self.y_major.setValue(suggested.y_major)
                    self.y_minor.setValue(suggested.y_minor)
                self.y_label.setText("UV 280 (mAU)")
            else:
                self.y_min.setValue(0.0)
                self.y_max.setValue(1.05)
                self.y_major.setValue(0.2)
                self.y_minor.setValue(0.05)
                label = "Relative A280" if mode == "peak" else "Normalized A280"
                self.y_label.setText(label)
        finally:
            self._loading_controls = False
        self.schedule_preview()

    def set_area_around_main_peak(self) -> None:
        if self.trace is None:
            return
        mask = (self.trace.x >= self.x_min.value()) & (self.trace.x <= self.x_max.value())
        if not mask.any():
            return
        indices = mask.nonzero()[0]
        peak_index = int(indices[int(self.trace.y[mask].argmax())])
        peak_x = float(self.trace.x[peak_index])
        self.area_start.setValue(max(self.x_min.value(), peak_x - 1.0))
        self.area_end.setValue(min(self.x_max.value(), peak_x + 1.0))
        self.show_area.setChecked(True)
        self.schedule_preview()

    def _settings_from_controls(self) -> PlotSettings:
        normalization = self.normalization_mode.currentData()
        settings = PlotSettings(
            x_min=self.x_min.value(),
            x_max=self.x_max.value(),
            y_min=self.y_min.value(),
            y_max=self.y_max.value(),
            x_major=self.x_major.value(),
            x_minor=self.x_minor.value(),
            y_major=self.y_major.value(),
            y_minor=self.y_minor.value(),
            x_label=self.x_label.text().strip() or "Elution volume (ml)",
            y_label=self.y_label.text().strip() or "UV 280 (mAU)",
            trace_color=self.color_button.text(),
            trace_width=self.trace_width.value(),
            axis_width=self.axis_width.value(),
            tick_font_size=self.tick_font.value(),
            label_font_size=self.label_font.value(),
            show_tick_labels=self.show_tick_labels.isChecked(),
            show_peak_label=self.show_peak_label.isChecked(),
            smooth_window=self.smooth_window.value(),
            baseline_subtract=self.baseline_subtract.isChecked(),
            normalize=normalization != "none",
            normalization_mode="maximum" if normalization == "none" else normalization,
            normalization_peak_x=self.normalization_peak_x.value(),
            normalization_window=self.normalization_window.value(),
            show_area=self.show_area.isChecked(),
            area_start=self.area_start.value(),
            area_end=self.area_end.value(),
        )
        return with_normalized_axis(settings)

    def _apply_settings_to_controls(self, settings: PlotSettings) -> None:
        self._loading_controls = True
        try:
            self.x_min.setValue(settings.x_min)
            self.x_max.setValue(settings.x_max)
            self.y_min.setValue(settings.y_min)
            self.y_max.setValue(settings.y_max)
            self.x_major.setValue(settings.x_major)
            self.x_minor.setValue(settings.x_minor)
            self.y_major.setValue(settings.y_major)
            self.y_minor.setValue(settings.y_minor)
            self.x_label.setText(settings.x_label)
            self.y_label.setText(settings.y_label)
            self.trace_width.setValue(settings.trace_width)
            self.axis_width.setValue(settings.axis_width)
            self.tick_font.setValue(settings.tick_font_size)
            self.label_font.setValue(settings.label_font_size)
            self.show_tick_labels.setChecked(settings.show_tick_labels)
            self.show_peak_label.setChecked(settings.show_peak_label)
            self.smooth_window.setValue(settings.smooth_window)
            self.baseline_subtract.setChecked(settings.baseline_subtract)
            mode = settings.normalization_mode if settings.normalize else "none"
            mode_index = self.normalization_mode.findData(mode)
            self.normalization_mode.setCurrentIndex(max(0, mode_index))
            self.normalization_peak_x.setValue(settings.normalization_peak_x)
            self.normalization_window.setValue(settings.normalization_window)
            self.show_area.setChecked(settings.show_area)
            self.area_start.setValue(settings.area_start)
            self.area_end.setValue(settings.area_end)
            self._set_color_button(settings.trace_color)
        finally:
            self._loading_controls = False
        self._update_normalization_controls()

    def apply_reference_preset(self) -> None:
        self._loading_controls = True
        try:
            self._set_color_button("#858585")
            self.trace_width.setValue(7.0)
            self.axis_width.setValue(5.0)
            self.tick_font.setValue(34.0)
            self.label_font.setValue(42.0)
            self.show_tick_labels.setChecked(True)
            self.show_peak_label.setChecked(False)
        finally:
            self._loading_controls = False
        self.schedule_preview()

    def _set_color_button(self, color: str) -> None:
        color = color.upper()
        self.color_button.setText(color)
        self.color_button.setStyleSheet(
            f"background: {color}; color: {'black' if QColor(color).lightness() > 150 else 'white'};"
        )

    def choose_trace_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.color_button.text()), self, "Trace color")
        if color.isValid():
            self._set_color_button(color.name().upper())
            self.schedule_preview()

    def open_data_dialog(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Add SEC data files",
            "",
            "SEC data (*.txt *.csv *.tsv);;All files (*)",
        )
        if filenames:
            self.add_paths([Path(filename) for filename in filenames])

    def open_image_dialog(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Add chromatogram images",
            "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff);;All files (*)",
        )
        if filenames:
            self.add_paths([Path(filename) for filename in filenames])

    def _suggest_item_settings(self, trace: TraceData) -> PlotSettings:
        settings = suggest_settings(trace)
        mask = (trace.x >= settings.x_min) & (trace.x <= settings.x_max)
        indices = mask.nonzero()[0]
        peak_index = int(indices[int(trace.y[mask].argmax())])
        peak_x = float(trace.x[peak_index])
        half_width = min(1.0, max((settings.x_max - settings.x_min) * 0.08, 0.1))
        return replace(
            settings,
            normalization_peak_x=peak_x,
            normalization_window=max(settings.x_minor, 0.1),
            area_start=max(settings.x_min, peak_x - half_width),
            area_end=min(settings.x_max, peak_x + half_width),
        )

    def add_paths(self, paths: list[Path]) -> None:
        existing = {item.path.resolve() for item in self.items}
        first_new = -1
        errors: list[str] = []
        for path in paths:
            path = path.expanduser()
            if path.resolve() in existing:
                continue
            suffix = path.suffix.lower()
            if suffix in DATA_SUFFIXES:
                try:
                    trace = read_trace(path)
                    item = SECItem(
                        path=path,
                        kind="data",
                        trace=trace,
                        settings=self._suggest_item_settings(trace),
                    )
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
                    continue
            elif suffix in IMAGE_SUFFIXES:
                item = SECItem(
                    path=path,
                    kind="image",
                    settings=PlotSettings(
                        6, 18, 0, 35, 2, 0.5, 5, 1,
                        normalization_peak_x=13,
                        area_start=12,
                        area_end=14,
                    ),
                )
            else:
                errors.append(f"{path.name}: unsupported file type")
                continue
            if first_new < 0:
                first_new = len(self.items)
            self.items.append(item)
            existing.add(path.resolve())
            label = f"{path.name}  [{'data' if item.kind == 'data' else 'image'}]"
            self.source_list.addItem(label)

        if first_new >= 0:
            self.source_list.setCurrentRow(first_new)
        if errors:
            QMessageBox.warning(self, "Some files were not added", "\n".join(errors))
        self.statusBar().showMessage(
            f"Batch contains {len(self.items)} file(s). Select an item to edit it."
        )

    def _store_current_item(self) -> None:
        if not (0 <= self.current_item_index < len(self.items)):
            return
        item = self.items[self.current_item_index]
        item.trace = self.trace
        item.settings = self._settings_from_controls()
        item.svg = self.current_svg
        item.plot_bottom_left = self.plot_bottom_left
        item.plot_top_right = self.plot_top_right
        item.sampled_trace_color = self.sampled_trace_color
        item.color_tolerance = self.color_tolerance.value()

    def select_item(self, row: int) -> None:
        if self._switching_item or (row >= 0 and row == self.current_item_index):
            return
        self._store_current_item()
        if not (0 <= row < len(self.items)):
            self.current_item_index = -1
            self.trace = None
            self.current_svg = ""
            self.source_label.setText("No file loaded")
            return

        self._switching_item = True
        self.current_item_index = row
        item = self.items[row]
        self.source_path = item.path
        self.trace = item.trace
        self.current_svg = item.svg
        self._apply_settings_to_controls(item.settings or PlotSettings(0, 20, 0, 35, 2, 0.5, 5, 1))
        try:
            if item.kind == "data":
                self.image_path = None
                self.image_group.setVisible(False)
                assert item.trace is not None
                self.source_label.setText(
                    f"{item.path.name}\n{len(item.trace.x):,} points; columns: "
                    f"{item.trace.x_name} / {item.trace.y_name}"
                )
                self.preview_stack.setCurrentWidget(self.svg_preview)
                self.update_preview()
            else:
                self.image_path = item.path
                self.plot_bottom_left = item.plot_bottom_left
                self.plot_top_right = item.plot_top_right
                self.sampled_trace_color = item.sampled_trace_color
                self.color_tolerance.setValue(item.color_tolerance)
                self.image_canvas.set_image(item.path)
                self.image_group.setVisible(True)
                self.source_label.setText(
                    f"{item.path.name}\nImage digitization mode"
                    + ("; curve extracted" if item.trace is not None else "; calibration required")
                )
                if self.plot_bottom_left:
                    self.image_canvas.set_mark("bottom_left", self.plot_bottom_left)
                if self.plot_top_right:
                    self.image_canvas.set_mark("top_right", self.plot_top_right)
                self._update_calibration_label()
                if item.trace is not None:
                    self.preview_stack.setCurrentWidget(self.svg_preview)
                    self.update_preview()
                else:
                    self.preview_stack.setCurrentWidget(self.image_canvas)
                    self.auto_detect_plot(silent=True)
        except Exception as exc:
            self._show_error("Could not load selected item", exc)
        finally:
            self._switching_item = False

    def remove_selected_item(self) -> None:
        row = self.source_list.currentRow()
        if not (0 <= row < len(self.items)):
            return
        self._switching_item = True
        self.source_list.takeItem(row)
        self.items.pop(row)
        self.current_item_index = -1
        self._switching_item = False
        if self.items:
            next_row = min(row, len(self.items) - 1)
            self.source_list.setCurrentRow(next_row)
            self.select_item(next_row)
        else:
            self.select_item(-1)

    def load_data(self, path: Path) -> None:
        self.add_paths([path])

    def load_image(self, path: Path) -> None:
        self.add_paths([path])

    def set_click_mode(self, mode: str) -> None:
        self.click_mode = mode
        prompts = {
            "bottom_left": "Click the bottom-left axis intersection.",
            "top_right": "Click the top-right corner of the plot area.",
            "trace": "Click directly on the chromatogram trace.",
        }
        self.preview_stack.setCurrentWidget(self.image_canvas)
        self.statusBar().showMessage(prompts[mode])

    def handle_image_click(self, x: int, y: int) -> None:
        if not self.image_path or not self.click_mode:
            return
        if self.click_mode == "bottom_left":
            self.plot_bottom_left = (x, y)
            self.image_canvas.set_mark("bottom_left", (x, y))
        elif self.click_mode == "top_right":
            self.plot_top_right = (x, y)
            self.image_canvas.set_mark("top_right", (x, y))
        elif self.click_mode == "trace":
            try:
                self.sampled_trace_color = sample_image_color(self.image_path, x, y)
            except Exception as exc:
                self._show_error("Could not sample color", exc)
                return
            self.image_canvas.set_mark("trace", (x, y))
            self._set_color_button(self.sampled_trace_color)
        self.click_mode = None
        self._update_calibration_label()

    def auto_detect_plot(self, silent: bool = False) -> None:
        if not self.image_path:
            return
        try:
            left, top, right, bottom = detect_plot_rectangle(self.image_path)
        except Exception as exc:
            if not silent:
                self._show_error("Automatic axis detection failed", exc)
            return
        self.plot_bottom_left = (left, bottom)
        self.plot_top_right = (right, top)
        self.image_canvas.set_mark("bottom_left", self.plot_bottom_left)
        self.image_canvas.set_mark("top_right", self.plot_top_right)
        self._update_calibration_label()
        if not silent:
            self.statusBar().showMessage("Plot rectangle detected. Verify the crosshairs before extraction.")

    def _update_calibration_label(self) -> None:
        rectangle = "not calibrated"
        if self.plot_bottom_left and self.plot_top_right:
            rectangle = (
                f"left={self.plot_bottom_left[0]}, top={self.plot_top_right[1]}, "
                f"right={self.plot_top_right[0]}, bottom={self.plot_bottom_left[1]}"
            )
        self.calibration_label.setText(
            f"Plot rectangle: {rectangle}\nSampled trace color: {self.sampled_trace_color}"
        )

    def extract_image_curve(self) -> None:
        if not self.image_path or not self.plot_bottom_left or not self.plot_top_right:
            QMessageBox.warning(self, "Calibration required", "Set the plot bottom-left and top-right points first.")
            return
        rectangle = (
            self.plot_bottom_left[0],
            self.plot_top_right[1],
            self.plot_top_right[0],
            self.plot_bottom_left[1],
        )
        limits = (self.x_min.value(), self.x_max.value(), self.y_min.value(), self.y_max.value())
        try:
            self.trace = digitize_image(
                self.image_path,
                rectangle,
                limits,
                self.sampled_trace_color,
                self.color_tolerance.value(),
            )
        except Exception as exc:
            self._show_error("Could not extract curve", exc)
            return
        self.preview_stack.setCurrentWidget(self.svg_preview)
        self.update_preview()
        self.statusBar().showMessage(
            "Approximate curve extracted from image. Verify it against the source image before export."
        )

    def update_preview(self) -> None:
        if self.trace is None:
            return
        try:
            settings = self._settings_from_controls()
            self.current_svg = render_svg(self.trace, settings)
            self.svg_preview.load(QByteArray(self.current_svg.encode("utf-8")))
            if settings.show_area:
                result = integrate_peak(self.trace, settings)
                self.area_result_label.setText(self._format_area_result(result))
            else:
                self.area_result_label.setText("Peak-area calculation is off.")
            if 0 <= self.current_item_index < len(self.items):
                item = self.items[self.current_item_index]
                item.trace = self.trace
                item.settings = settings
                item.svg = self.current_svg
        except Exception as exc:
            self.area_result_label.setText(f"Calculation unavailable: {exc}")
            self.statusBar().showMessage(f"Preview error: {exc}")

    def _format_area_result(self, result: PeakAreaResult) -> str:
        displayed_unit = "relative·ml" if result.normalization_x is not None else "mAU·ml"
        text = (
            f"Interval: {result.start:.3f}–{result.end:.3f} ml\n"
            f"Raw integral: {result.raw_area:.5g} mAU·ml\n"
            f"Linear-baseline corrected: {result.baseline_corrected_area:.5g} mAU·ml\n"
            f"Displayed-scale integral: {result.displayed_area:.5g} {displayed_unit}"
        )
        if result.normalization_x is not None and result.normalization_y is not None:
            text += (
                f"\nReference peak: {result.normalization_x:.3f} ml, "
                f"original height {result.normalization_y:.5g} mAU"
            )
        return text

    def _default_export_name(self, suffix: str) -> str:
        stem = self.source_path.stem if self.source_path else "bencharc_sec"
        return f"{stem}_publication{suffix}"

    def apply_current_settings_to_all(self) -> None:
        if self.trace is None or not self.items:
            QMessageBox.information(self, "Nothing to apply", "Add at least one chromatogram first.")
            return
        settings = self._settings_from_controls()
        self._store_current_item()
        for item in self.items:
            item.settings = settings
            item.svg = ""
        self.update_preview()
        self.statusBar().showMessage(
            f"Applied the current axes, transformations, integration bounds, and style to {len(self.items)} item(s)."
        )

    def batch_export_dialog(self) -> None:
        if not self.items:
            QMessageBox.information(self, "Nothing to export", "Add chromatograms first.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Choose batch export folder")
        if not directory:
            return
        try:
            exported, skipped, report_path = self.batch_export(Path(directory))
        except Exception as exc:
            self._show_error("Batch export failed", exc)
            return
        message = f"Exported {exported} chromatogram(s) as editable SVG and 600 dpi PNG."
        if skipped:
            message += f" Skipped {skipped} image(s) whose curves have not been extracted."
        if report_path is not None:
            message += f" Peak-area results: {report_path.name}."
        QMessageBox.information(self, "Batch export complete", message)
        self.statusBar().showMessage(message)

    def batch_export(self, directory: Path) -> tuple[int, int, Path | None]:
        directory.mkdir(parents=True, exist_ok=True)
        self._store_current_item()
        exported = 0
        skipped = 0
        used_names: set[str] = set()
        area_rows: list[dict[str, str]] = []
        for item in self.items:
            if item.trace is None:
                skipped += 1
                continue
            settings = item.settings or self._suggest_item_settings(item.trace)
            svg = render_svg(item.trace, settings)
            base = item.path.stem
            candidate = base
            suffix = 2
            while candidate.lower() in used_names:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used_names.add(candidate.lower())
            svg_path = directory / f"{candidate}_publication.svg"
            png_path = directory / f"{candidate}_publication.png"
            svg_path.write_text(svg, encoding="utf-8")
            if not self._save_png_from_svg(svg, png_path):
                raise ValueError(f"Qt could not save {png_path.name}.")
            exported += 1
            if settings.show_area:
                result = integrate_peak(item.trace, settings)
                area_rows.append(
                    {
                        "file": item.path.name,
                        "source_kind": item.trace.source_kind,
                        "approximate": str(item.trace.approximate).lower(),
                        "area_start_ml": f"{result.start:.8g}",
                        "area_end_ml": f"{result.end:.8g}",
                        "raw_area_mAU_ml": f"{result.raw_area:.10g}",
                        "linear_baseline_corrected_area_mAU_ml": f"{result.baseline_corrected_area:.10g}",
                        "displayed_scale_area": f"{result.displayed_area:.10g}",
                        "normalization_mode": settings.normalization_mode if settings.normalize else "none",
                        "normalization_peak_ml": "" if result.normalization_x is None else f"{result.normalization_x:.8g}",
                        "normalization_peak_original_mAU": "" if result.normalization_y is None else f"{result.normalization_y:.10g}",
                    }
                )

        report_path: Path | None = None
        if area_rows:
            report_path = directory / "BenchArc_SEC_peak_areas.csv"
            with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(area_rows[0]))
                writer.writeheader()
                writer.writerows(area_rows)
        return exported, skipped, report_path

    def export_svg(self) -> None:
        if not self.current_svg:
            QMessageBox.information(self, "Nothing to export", "Load or extract a chromatogram first.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export editable SVG",
            self._default_export_name(".svg"),
            "SVG (*.svg)",
        )
        if not filename:
            return
        self.save_svg(filename)
        self.statusBar().showMessage(f"Exported editable SVG: {filename}")

    def save_svg(self, filename: str | Path) -> None:
        if not self.current_svg:
            raise ValueError("No chromatogram is available to export.")
        Path(filename).write_text(self.current_svg, encoding="utf-8")

    def export_png(self) -> None:
        if not self.current_svg:
            QMessageBox.information(self, "Nothing to export", "Load or extract a chromatogram first.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export 600 dpi PNG",
            self._default_export_name(".png"),
            "PNG (*.png)",
        )
        if not filename:
            return
        if not self.save_png(filename):
            QMessageBox.critical(self, "Export failed", "Qt could not save the PNG file.")
            return
        self.statusBar().showMessage(f"Exported 600 dpi PNG: {filename}")

    def save_png(self, filename: str | Path) -> bool:
        if not self.current_svg:
            raise ValueError("No chromatogram is available to export.")
        return self._save_png_from_svg(self.current_svg, filename)

    @staticmethod
    def _save_png_from_svg(svg: str, filename: str | Path) -> bool:
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        scale = 4
        size = renderer.defaultSize() * scale
        image = QImage(size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        dots_per_meter = round(600 / 0.0254)
        image.setDotsPerMeterX(dots_per_meter)
        image.setDotsPerMeterY(dots_per_meter)
        return image.save(str(filename), "PNG")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and all(
            Path(url.toLocalFile()).suffix.lower() in DATA_SUFFIXES | IMAGE_SUFFIXES
            for url in urls
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.add_paths([Path(url.toLocalFile()) for url in event.mimeData().urls()])
        event.acceptProposedAction()

    def _show_error(self, title: str, error: Exception) -> None:
        QMessageBox.critical(self, title, str(error))
        self.statusBar().showMessage(f"{title}: {error}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("BenchArc SEC")
    app.setOrganizationName("BenchArc")
    app.setStyleSheet(
        "QGroupBox { font-weight: 600; margin-top: 8px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        "QPushButton { padding: 5px 8px; }"
    )
    window = BenchArcSECWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
