from __future__ import annotations

import json
import os
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .instrument import (
    SIMULATOR_RESOURCE,
    InstrumentError,
    enumerate_usb_resources,
    identify_resource,
)
from .models import ChannelDut, ChannelRunResult, Metrics, SweepSettings
from .storage import (
    Database,
    default_output_dir,
    timestamped_summary_path,
    unique_raw_path,
    write_raw_csv,
)
from .worker import MeasurementWorker


APP_STYLE = """
QMainWindow, QWidget { background: #f4f7f9; color: #1b2a34; font-size: 13px; }
QGroupBox {
    background: #ffffff; border: 1px solid #cdd9e0; border-radius: 8px;
    margin-top: 12px; padding: 12px 8px 8px 8px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #245b78; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget {
    background: #ffffff; border: 1px solid #b9c8d1; border-radius: 4px; padding: 4px;
}
QPushButton { background: #e7eef2; border: 1px solid #aabdc8; border-radius: 5px; padding: 6px 12px; }
QPushButton:hover { background: #d8e7ef; }
QPushButton#startButton { background: #117864; color: white; border: 0; font-weight: 700; }
QPushButton#stopButton { background: #b03a2e; color: white; border: 0; font-weight: 700; }
QPushButton#finishButton { background: #245b78; color: white; border: 0; font-weight: 700; }
QPushButton:disabled { background: #d5dde1; color: #7b8a92; }
QHeaderView::section { background: #e2ebf0; padding: 5px; border: 0; border-right: 1px solid #c2d0d8; }
QProgressBar { border: 1px solid #b9c8d1; border-radius: 4px; text-align: center; background: white; }
QProgressBar::chunk { background: #2a8c78; }
QToolButton { background: #245b78; color: white; border: 0; border-radius: 10px; padding: 2px 8px; font-weight: 700; }
QToolButton:hover { background: #347da3; }
"""


GITHUB_URL = "https://github.com/Maxwellzkl/software"
VOLTAGE_RANGES = (
    (0.2, "0.2 V"),
    (2.0, "2 V"),
    (20.0, "20 V"),
    (200.0, "200 V"),
)
CURRENT_RANGES = (
    (1e-7, "100 nA"),
    (1e-6, "1 μA"),
    (1e-5, "10 μA"),
    (1e-4, "100 μA"),
    (1e-3, "1 mA"),
    (1e-2, "10 mA"),
    (1e-1, "100 mA"),
    (1.0, "1 A"),
    (1.5, "1.5 A"),
    (3.0, "3 A"),
)
MEASURE_SPEEDS = (
    ("Auto", "AUTO"),
    ("Short", "SHORT"),
    ("Medium", "MEDIUM"),
    ("Normal", "NORMAL"),
    ("Long", "LONG"),
    ("Manual", "MANUAL"),
)
SPEED_NPLC = {"SHORT": 0.01, "MEDIUM": 0.1, "NORMAL": 1.0, "LONG": 10.0}


def _double_spin(
    minimum: float,
    maximum: float,
    value: float,
    decimals: int = 6,
    suffix: str = "",
) -> QDoubleSpinBox:
    widget = NoWheelDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setSuffix(suffix)
    widget.setKeyboardTracking(False)
    return widget


class NoWheelComboBox(QComboBox):
    """A combo box whose closed value cannot be changed by the mouse wheel."""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """A spin box whose value cannot be changed by the mouse wheel."""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """A double spin box whose value cannot be changed by the mouse wheel."""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override
        event.ignore()


class DevicePanel(QGroupBox):
    profiles_changed = Signal()

    def __init__(self, channel: int, database: Database) -> None:
        super().__init__(f"CH{channel} 器件 / 像素")
        self.channel = channel
        self.database = database
        self.profile_combo = NoWheelComboBox()
        self.profile_combo.currentIndexChanged.connect(self._profile_selected)
        self.device_edit = QLineEdit()
        self.device_edit.setPlaceholderText("例如 Device01")
        self.point_edit = QLineEdit("1")
        self.point_edit.setPlaceholderText("例如 1")
        self.area_spin = _double_spin(0.000001, 10000.0, 0.04, 6, " cm²")
        self.condition_combo = NoWheelComboBox()
        self.condition_combo.addItem("Light", "light")
        self.condition_combo.addItem("Dark", "dark")

        save_button = QPushButton("保存/更新器件")
        delete_button = QPushButton("删除器件")
        save_button.clicked.connect(self._save_profile)
        delete_button.clicked.connect(self._delete_profile)
        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addWidget(save_button)
        buttons_layout.addWidget(delete_button)

        layout = QGridLayout(self)
        layout.setContentsMargins(8, 10, 8, 6)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)
        layout.addWidget(QLabel("已保存器件"), 0, 0)
        layout.addWidget(self.profile_combo, 0, 1, 1, 3)
        layout.addWidget(QLabel("器件编号"), 1, 0)
        layout.addWidget(self.device_edit, 1, 1)
        layout.addWidget(QLabel("Point"), 1, 2)
        layout.addWidget(self.point_edit, 1, 3)
        layout.addWidget(QLabel("面积"), 2, 0)
        layout.addWidget(self.area_spin, 2, 1)
        layout.addWidget(QLabel("类型"), 2, 2)
        layout.addWidget(self.condition_combo, 2, 3)
        layout.addWidget(buttons, 3, 0, 1, 4)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(3, 2)
        self.setMaximumHeight(175)
        self.reload_profiles()

    def reload_profiles(self, keep_device: str | None = None) -> None:
        keep_device = keep_device if keep_device is not None else self.device_edit.text()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("-- 新建/手动输入 --", None)
        selected = 0
        for index, (device_id, area) in enumerate(self.database.list_devices(), start=1):
            self.profile_combo.addItem(f"{device_id}  ({area:g} cm²)", (device_id, area))
            if device_id == keep_device:
                selected = index
        self.profile_combo.setCurrentIndex(selected)
        self.profile_combo.blockSignals(False)

    def _profile_selected(self, index: int) -> None:
        payload = self.profile_combo.itemData(index)
        if payload:
            self.device_edit.setText(payload[0])
            self.area_spin.setValue(float(payload[1]))

    def _save_profile(self) -> None:
        try:
            self.database.save_device(self.device_edit.text(), self.area_spin.value())
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存器件", str(exc))
            return
        self.profiles_changed.emit()

    def _delete_profile(self) -> None:
        device_id = self.device_edit.text().strip()
        if not device_id:
            return
        answer = QMessageBox.question(
            self,
            "删除器件配置",
            f"删除器件配置“{device_id}”？历史测试数据不会被删除。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.database.delete_device(device_id)
        self.device_edit.clear()
        self.profiles_changed.emit()

    def dut(self) -> ChannelDut:
        return ChannelDut(
            channel=self.channel,
            device_id=self.device_edit.text().strip(),
            point=self.point_edit.text().strip(),
            area_cm2=self.area_spin.value(),
            condition=str(self.condition_combo.currentData()),
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PCE Studio - Keysight B2902B")
        self.setMinimumSize(820, 560)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(
            min(1600, max(self.minimumWidth(), available.width() - 64)),
            min(980, max(self.minimumHeight(), available.height() - 64)),
        )
        self.setStyleSheet(APP_STYLE)

        self.database = Database()
        self.app_settings = QSettings("OpenAI", "PCEStudio")
        self.connected_address: str | None = None
        self.thread: QThread | None = None
        self.worker: MeasurementWorker | None = None
        self.session_run_ids: list[int] = []
        self.temporary_curves: dict[tuple[int, str], tuple[object, object, float]] = {}
        self.selected_history: dict[int, ChannelRunResult] = {}

        self._build_ui()
        self._restore_settings()
        self._reload_history()
        self._update_mode_visibility()
        self._update_step()
        QTimer.singleShot(0, self.refresh_resources)

    def _build_ui(self) -> None:
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_panel = self._build_left_panel()
        self.left_panel.setMinimumWidth(350)
        self.left_panel.setMaximumWidth(420)
        main_panel = self._build_main_panel()
        main_panel.setMinimumWidth(450)
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(main_panel)
        self.main_splitter.setSizes([400, 1200])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.setCentralWidget(self.main_splitter)
        self.statusBar().showMessage("就绪")
        author = QLabel(
            f'created by ZKL&nbsp;&nbsp;·&nbsp;&nbsp;<a href="{GITHUB_URL}">GitHub</a>'
        )
        author.setOpenExternalLinks(True)
        author.setToolTip(GITHUB_URL)
        self.statusBar().addPermanentWidget(author)

    def _build_left_panel(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self._connection_group())
        layout.addWidget(self._mode_group())
        layout.addWidget(self._sweep_group())
        layout.addWidget(self._output_group())
        layout.addWidget(self._actions_group())
        layout.addStretch(1)

        scroll = QScrollArea()
        self.parameter_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(4, 4, 4, 4)
        wrapper_layout.addWidget(scroll)
        return wrapper

    def _connection_group(self) -> QGroupBox:
        group = QGroupBox("USB VISA 连接")
        self.resource_combo = NoWheelComboBox()
        self.resource_combo.currentIndexChanged.connect(self._resource_changed)
        self.refresh_button = QPushButton("自动枚举")
        self.connect_button = QPushButton("连接并识别")
        self.refresh_button.clicked.connect(self.refresh_resources)
        self.connect_button.clicked.connect(self.connect_resource)
        self.idn_label = QLabel("未连接")
        self.idn_label.setWordWrap(True)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.refresh_button)
        row_layout.addWidget(self.connect_button)
        layout = QFormLayout(group)
        layout.addRow("VISA Resource", self.resource_combo)
        layout.addRow(row)
        layout.addRow("设备", self.idn_label)
        return group

    def _mode_group(self) -> QGroupBox:
        group = QGroupBox("通道模式")
        self.channel_mode_combo = NoWheelComboBox()
        self.channel_mode_combo.addItem("单通道", "single")
        self.channel_mode_combo.addItem("双通道同步", "dual")
        self.single_channel_combo = NoWheelComboBox()
        self.single_channel_combo.addItem("CH1", 1)
        self.single_channel_combo.addItem("CH2", 2)
        self.channel_mode_combo.currentIndexChanged.connect(self._update_mode_visibility)
        self.single_channel_combo.currentIndexChanged.connect(self._update_mode_visibility)
        layout = QFormLayout(group)
        layout.addRow("测量模式", self.channel_mode_combo)
        layout.addRow("单通道选择", self.single_channel_combo)
        return group

    def _sweep_group(self) -> QGroupBox:
        group = QGroupBox("共享扫描参数（CH1 / CH2）")
        layout = QFormLayout(group)
        self.source_function_combo = NoWheelComboBox()
        self.source_function_combo.addItem("VAR1")
        self.source_mode_combo = NoWheelComboBox()
        self.source_mode_combo.addItem("V - 电压源", "VOLT")
        self.source_mode_combo.addItem("I - 电流源", "CURR")
        self.source_mode_combo.currentIndexChanged.connect(self._source_mode_changed)
        self.shape_combo = NoWheelComboBox()
        self.shape_combo.addItem("DC")
        self.source_delay_spin = _double_spin(0.0, 1000.0, 0.0, 6, " s")
        self.scan_plan_combo = NoWheelComboBox()
        self.scan_plan_combo.addItem("正扫", "forward")
        self.scan_plan_combo.addItem("反扫", "reverse")
        self.scan_plan_combo.addItem("正扫 + 反扫", "both")
        self.scan_plan_combo.setCurrentIndex(2)
        self.start_spin = _double_spin(-210.0, 210.0, -0.2, 6)
        self.stop_spin = _double_spin(-210.0, 210.0, 1.2, 6)
        self.count_spin = NoWheelSpinBox()
        self.count_spin.setRange(2, 100000)
        self.count_spin.setValue(71)
        self.step_label = QLabel()
        self.step_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for widget in (self.start_spin, self.stop_spin, self.count_spin):
            widget.valueChanged.connect(self._update_step)
        self.compliance_label = QLabel("电流 Compliance")
        self.compliance_spin = _double_spin(1e-9, 210.0, 0.1, 9)

        self.source_range_combo = NoWheelComboBox()

        self.measure_voltage_check = QCheckBox("启用")
        self.measure_voltage_check.setChecked(True)
        self.voltage_range_combo = NoWheelComboBox()
        self._populate_measure_range(self.voltage_range_combo, VOLTAGE_RANGES)
        voltage_row = self._measure_range_row(
            self.measure_voltage_check, self.voltage_range_combo
        )

        self.measure_current_check = QCheckBox("启用")
        self.measure_current_check.setChecked(True)
        self.current_range_combo = NoWheelComboBox()
        self._populate_measure_range(self.current_range_combo, CURRENT_RANGES)
        current_row = self._measure_range_row(
            self.measure_current_check, self.current_range_combo
        )
        self.measure_delay_spin = _double_spin(0.0, 1000.0, 0.0, 6, " s")
        self.measure_speed_combo = NoWheelComboBox()
        for label, value in MEASURE_SPEEDS:
            self.measure_speed_combo.addItem(label, value)
        self.measure_speed_combo.setCurrentIndex(
            self.measure_speed_combo.findData("NORMAL")
        )
        self.measure_speed_combo.currentIndexChanged.connect(self._measure_speed_changed)
        self.nplc_spin = _double_spin(0.0001, 100.0, 1.0, 4, " PLC")
        speed_row = QWidget()
        speed_layout = QHBoxLayout(speed_row)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.addWidget(self.measure_speed_combo, 1)
        speed_layout.addWidget(self.nplc_spin, 1)
        self.irradiance_spin = _double_spin(0.000001, 100000.0, 100.0, 6, " mW/cm²")

        self.measure_voltage_check.toggled.connect(self._update_measure_range_enabled)
        self.measure_current_check.toggled.connect(self._update_measure_range_enabled)

        info_button = QToolButton()
        info_button.setText("i  参数说明")
        info_button.setToolTip("查看扫描、量程、速度和单位说明")
        info_button.clicked.connect(self._show_parameter_help)

        layout.addRow("帮助", info_button)
        layout.addRow("Source Function", self.source_function_combo)
        layout.addRow("Mode", self.source_mode_combo)
        layout.addRow("Shape", self.shape_combo)
        layout.addRow("Source Delay", self.source_delay_spin)
        layout.addRow("Sweep", self.scan_plan_combo)
        layout.addRow("Start", self.start_spin)
        layout.addRow("Stop", self.stop_spin)
        layout.addRow("VAR1 Count", self.count_spin)
        layout.addRow("计算步长", self.step_label)
        layout.addRow(self.compliance_label, self.compliance_spin)
        layout.addRow("Source Range", self.source_range_combo)
        layout.addRow("Voltage Measure", voltage_row)
        layout.addRow("Current Measure", current_row)
        layout.addRow("Measure Delay", self.measure_delay_spin)
        layout.addRow("Measure Speed", speed_row)
        layout.addRow("光功率密度", self.irradiance_spin)
        self._source_mode_changed()
        self._measure_speed_changed()
        return group

    @staticmethod
    def _range_key(mode: str, value: float) -> str:
        return f"{mode}:{value:.12g}"

    def _populate_measure_range(
        self, combo: QComboBox, ranges: tuple[tuple[float, str], ...]
    ) -> None:
        combo.clear()
        combo.addItem("Auto", self._range_key("AUTO", ranges[0][0]))
        for value, label in ranges:
            combo.addItem(f"Fixed {label}", self._range_key("FIXED", value))
        for value, label in ranges:
            combo.addItem(f"Limited {label}", self._range_key("LIMITED", value))

    def _populate_source_range(self) -> None:
        previous = self.source_range_combo.currentData()
        ranges = (
            VOLTAGE_RANGES
            if self.source_mode_combo.currentData() == "VOLT"
            else CURRENT_RANGES
        )
        self.source_range_combo.blockSignals(True)
        self.source_range_combo.clear()
        self.source_range_combo.addItem("Auto", self._range_key("AUTO", ranges[0][0]))
        for value, label in ranges:
            self.source_range_combo.addItem(label, self._range_key("FIXED", value))
        index = self.source_range_combo.findData(previous)
        self.source_range_combo.setCurrentIndex(index if index >= 0 else 0)
        self.source_range_combo.blockSignals(False)

    @staticmethod
    def _range_selection(combo: QComboBox) -> tuple[str, float]:
        mode, raw_value = str(combo.currentData()).split(":", 1)
        return mode, float(raw_value)

    def _measure_range_row(
        self, enabled: QCheckBox, range_combo: QComboBox
    ) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(enabled)
        layout.addWidget(range_combo, 1)
        return row

    def _output_group(self) -> QGroupBox:
        group = QGroupBox("数据输出")
        self.output_edit = QLineEdit(str(default_output_dir()))
        self.output_browse_button = QPushButton("选择…")
        self.output_browse_button.setToolTip("打开系统目录选择窗口")
        self.output_browse_button.setFixedWidth(72)
        self.output_browse_button.clicked.connect(self._browse_output)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.output_edit.setMinimumWidth(0)
        row_layout.addWidget(self.output_edit, 1)
        row_layout.addWidget(self.output_browse_button)
        layout = QFormLayout(group)
        layout.addRow("目录", row)
        filename_hint = QLabel("文件名：器件编号_light或dark_Point.csv；重名自动加序号")
        filename_hint.setWordWrap(True)
        layout.addRow(filename_hint)
        return group

    def _actions_group(self) -> QGroupBox:
        group = QGroupBox("测量控制")
        self.start_button = QPushButton("开始测量")
        self.start_button.setObjectName("startButton")
        self.stop_button = QPushButton("停止测量")
        self.stop_button.setObjectName("stopButton")
        self.finish_button = QPushButton("结束并导出统计")
        self.finish_button.setObjectName("finishButton")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_measurement)
        self.stop_button.clicked.connect(self.stop_measurement)
        self.finish_button.clicked.connect(self.export_session)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout = QGridLayout(group)
        layout.addWidget(self.start_button, 0, 0)
        layout.addWidget(self.stop_button, 0, 1)
        layout.addWidget(self.finish_button, 1, 0, 1, 2)
        layout.addWidget(self.progress_bar, 2, 0, 1, 2)
        return group

    def _build_main_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        dut_row = QWidget()
        dut_layout = QHBoxLayout(dut_row)
        dut_layout.setContentsMargins(0, 0, 0, 0)
        dut_layout.setSpacing(6)
        self.device_panels = {
            1: DevicePanel(1, self.database),
            2: DevicePanel(2, self.database),
        }
        for device_panel in self.device_panels.values():
            device_panel.profiles_changed.connect(self._reload_profiles)
            dut_layout.addWidget(device_panel)
        dut_row.setMaximumHeight(175)
        layout.addWidget(dut_row, 0)

        self.figure = Figure(figsize=(10, 6.5), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(340)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_xlabel("Voltage (V)")
        self.axes.set_ylabel("Current Density (mA/cm²)")
        self.axes.grid(True, alpha=0.25)
        layout.addWidget(self.canvas, 10)

        result_page = QWidget()
        result_layout = QVBoxLayout(result_page)
        result_layout.setContentsMargins(4, 4, 4, 4)
        self.result_table = QTableWidget(0, 7)
        self.result_table.setHorizontalHeaderLabels(
            ["通道", "结果", "PCE (%)", "Voc (V)", "Jsc (mA/cm²)", "FF (%)", "Pmax (mW/cm²)"]
        )
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self.result_table.horizontalHeader().setStretchLastSection(True)
        result_layout.addWidget(self.result_table)

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(4, 4, 4, 4)
        history_layout.addWidget(QLabel("勾选测试记录后，可将历史 IV 曲线叠加到主图进行比较。"))
        self.history_list = QListWidget()
        self.history_list.itemChanged.connect(self._history_item_changed)
        history_layout.addWidget(self.history_list)

        self.details_tabs = QTabWidget()
        self.details_tabs.addTab(result_page, "当前测试结果")
        self.details_tabs.addTab(history_page, "历史曲线")
        self.details_tabs.setMinimumHeight(155)
        self.details_tabs.setMaximumHeight(190)
        layout.addWidget(self.details_tabs, 0)
        return panel

    def _reload_profiles(self) -> None:
        for panel in self.device_panels.values():
            panel.reload_profiles()

    def _update_mode_visibility(self) -> None:
        if not hasattr(self, "device_panels"):
            return
        dual = self.channel_mode_combo.currentData() == "dual"
        self.single_channel_combo.setEnabled(not dual)
        selected = int(self.single_channel_combo.currentData())
        for channel, panel in self.device_panels.items():
            panel.setVisible(dual or channel == selected)

    def _source_mode_changed(self) -> None:
        source_mode = self.source_mode_combo.currentData()
        unit = "V" if source_mode == "VOLT" else "A"
        source_limit = 210.0 if source_mode == "VOLT" else 3.03
        compliance_limit = 3.03 if source_mode == "VOLT" else 210.0
        self.start_spin.setRange(-source_limit, source_limit)
        self.stop_spin.setRange(-source_limit, source_limit)
        self.compliance_spin.setMaximum(compliance_limit)
        self.start_spin.setSuffix(f" {unit}")
        self.stop_spin.setSuffix(f" {unit}")
        self.compliance_spin.setSuffix(" A" if source_mode == "VOLT" else " V")
        self.compliance_label.setText(
            "电流 Compliance" if source_mode == "VOLT" else "电压 Compliance"
        )
        self._populate_source_range()
        self._update_measure_range_enabled()
        self._update_step()

    def _update_measure_range_enabled(self) -> None:
        source_mode = self.source_mode_combo.currentData()
        self.voltage_range_combo.setEnabled(
            self.measure_voltage_check.isChecked() and source_mode != "VOLT"
        )
        self.current_range_combo.setEnabled(
            self.measure_current_check.isChecked() and source_mode != "CURR"
        )

    def _measure_speed_changed(self) -> None:
        manual = self.measure_speed_combo.currentData() == "MANUAL"
        self.nplc_spin.setEnabled(manual)
        if manual:
            self.nplc_spin.setToolTip("Manual 模式的积分时间，单位为 PLC。")
        else:
            speed = str(self.measure_speed_combo.currentData())
            value = "量程自动决定" if speed == "AUTO" else f"{SPEED_NPLC[speed]:g} PLC"
            self.nplc_spin.setToolTip(f"当前档位对应：{value}")

    def _show_parameter_help(self) -> None:
        QMessageBox.information(
            self,
            "扫描参数说明",
            "Source Delay / Measure Delay：每个扫描点的源延迟和测量延迟，单位 s。\n\n"
            "Start / Stop / 步长：电压源模式单位 V，电流源模式单位 A；步长由 "
            "(Stop-Start)/(VAR1 Count-1) 计算。\n\n"
            "Compliance：电压源模式为限流 A；电流源模式为限压 V。\n\n"
            "Source Range：Auto 自动选择；固定档必须覆盖 Start 和 Stop。\n\n"
            "Measure Range：Auto 自动选择；Fixed 固定量程；Limited 为自动量程，"
            "但不会切换到低于所选值的量程。源量对应的测量 Range 由 Source Range 决定。\n\n"
            "Measure Speed：Auto 由量程决定；Short=0.01 PLC，Medium=0.1 PLC，"
            "Normal=1 PLC，Long=10 PLC；Manual 可自定义 0.0001-100 PLC。\n\n"
            "光功率密度：Light 数据计算 PCE 时使用，单位 mW/cm²。",
        )

    def _update_step(self) -> None:
        if not hasattr(self, "step_label"):
            return
        count = self.count_spin.value()
        step = (self.stop_spin.value() - self.start_spin.value()) / (count - 1)
        unit = "V" if self.source_mode_combo.currentData() == "VOLT" else "A"
        self.step_label.setText(f"正扫 {step:.9g} {unit} / 反扫 {-step:.9g} {unit}")

    def _browse_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "选择原始数据输出目录", self.output_edit.text()
        )
        if selected:
            self.output_edit.setText(selected)

    def refresh_resources(self) -> None:
        previous = self.resource_combo.currentData()
        self.resource_combo.blockSignals(True)
        self.resource_combo.clear()
        error_message = ""
        try:
            resources = enumerate_usb_resources()
        except InstrumentError as exc:
            resources = []
            error_message = str(exc)
        for resource in resources:
            self.resource_combo.addItem(resource.label, resource.address)
        self.resource_combo.addItem("模拟器 - B2902B（不连接源表）", SIMULATOR_RESOURCE)
        index = self.resource_combo.findData(previous)
        self.resource_combo.setCurrentIndex(index if index >= 0 else 0)
        self.resource_combo.blockSignals(False)
        self._resource_changed()
        if error_message:
            self.statusBar().showMessage(error_message, 10000)
        elif resources:
            self.statusBar().showMessage(f"已枚举到 {len(resources)} 个 USB VISA 资源", 5000)
        else:
            self.statusBar().showMessage("未发现 USB VISA 设备，可使用模拟器验证软件", 5000)

    def _resource_changed(self) -> None:
        self.connected_address = None
        if hasattr(self, "idn_label"):
            self.idn_label.setText("未连接")

    def connect_resource(self) -> None:
        address = self.resource_combo.currentData()
        if not address:
            QMessageBox.warning(self, "没有设备", "未找到可连接的 VISA 资源。")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            identity = identify_resource(str(address))
            if "B2902B" not in identity.upper():
                raise InstrumentError(f"设备型号不是 B2902B：{identity}")
            self.connected_address = str(address)
            self.idn_label.setText(identity)
            self.statusBar().showMessage("源表连接成功", 5000)
        except Exception as exc:
            self.connected_address = None
            self.idn_label.setText("连接失败")
            QMessageBox.critical(self, "连接失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _sweep_settings(self) -> SweepSettings:
        source_range_mode, source_range = self._range_selection(self.source_range_combo)
        voltage_range_mode, voltage_range = self._range_selection(
            self.voltage_range_combo
        )
        current_range_mode, current_range = self._range_selection(
            self.current_range_combo
        )
        measure_speed = str(self.measure_speed_combo.currentData())
        nplc = SPEED_NPLC.get(measure_speed, self.nplc_spin.value())
        settings = SweepSettings(
            source_mode=str(self.source_mode_combo.currentData()),
            start=self.start_spin.value(),
            stop=self.stop_spin.value(),
            count=self.count_spin.value(),
            scan_plan=str(self.scan_plan_combo.currentData()),
            source_delay_s=self.source_delay_spin.value(),
            compliance=self.compliance_spin.value(),
            source_range_auto=source_range_mode == "AUTO",
            source_range=source_range,
            measure_voltage=self.measure_voltage_check.isChecked(),
            voltage_range_auto=voltage_range_mode != "FIXED",
            voltage_range_mode=voltage_range_mode,
            voltage_range=voltage_range,
            measure_current=self.measure_current_check.isChecked(),
            current_range_auto=current_range_mode != "FIXED",
            current_range_mode=current_range_mode,
            current_range=current_range,
            measure_delay_s=self.measure_delay_spin.value(),
            nplc_auto=measure_speed == "AUTO",
            measure_speed=measure_speed,
            nplc=nplc,
            irradiance_mw_cm2=self.irradiance_spin.value(),
        )
        settings.validate()
        return settings

    def _active_duts(self) -> list[ChannelDut]:
        if self.channel_mode_combo.currentData() == "dual":
            channels = (1, 2)
        else:
            channels = (int(self.single_channel_combo.currentData()),)
        duts = [self.device_panels[channel].dut() for channel in channels]
        for dut in duts:
            dut.validate()
        return duts

    def start_measurement(self) -> None:
        if self.thread is not None:
            return
        if not self.connected_address:
            QMessageBox.warning(self, "尚未连接", "请先选择 VISA 资源并点击“连接并识别”。")
            return
        try:
            settings = self._sweep_settings()
            duts = self._active_duts()
            output_dir = Path(self.output_edit.text()).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return

        self._save_settings()
        self.result_table.setRowCount(0)
        self.temporary_curves.clear()
        self._redraw_plot()
        self.progress_bar.setValue(0)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.finish_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.connect_button.setEnabled(False)

        self.thread = QThread(self)
        self.worker = MeasurementWorker(self.connected_address, settings, duts)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.pass_finished.connect(self._pass_finished)
        self.worker.warning.connect(lambda message: self.statusBar().showMessage(message, 15000))
        self.worker.finished.connect(self._measurement_finished)
        self.worker.failed.connect(self._measurement_failed)
        self.worker.stopped.connect(self._measurement_stopped)
        self.worker.done.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    def stop_measurement(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()
            self.stop_button.setEnabled(False)
            self.statusBar().showMessage("正在安全停止并关闭输出…")

    def _pass_finished(
        self, channel: int, direction: str, voltage: object, current: object, area: float
    ) -> None:
        self.temporary_curves[(channel, direction)] = (voltage, current, area)
        self._redraw_plot()

    def _measurement_finished(self, results_object: object) -> None:
        results: list[ChannelRunResult] = list(results_object)
        output_dir = Path(self.output_edit.text()).expanduser()
        errors: list[str] = []
        for result in results:
            try:
                raw_path = unique_raw_path(output_dir, result.dut)
                result.raw_file = str(raw_path)
                write_raw_csv(raw_path, result)
                run_id = self.database.save_run(result)
                self.session_run_ids.append(run_id)
                self._add_history_item(self.database.list_runs(1)[0], checked=True)
                self._append_result_rows(result)
            except Exception as exc:
                errors.append(f"CH{result.dut.channel}: {exc}")
        self.temporary_curves.clear()
        self._redraw_plot()
        if errors:
            QMessageBox.critical(self, "部分数据保存失败", "\n".join(errors))
        else:
            self.statusBar().showMessage("测量与原始数据保存完成", 8000)

    def _append_result_rows(self, result: ChannelRunResult) -> None:
        if result.dut.condition == "dark":
            self._append_metric_row(result.dut.channel, "Dark（不计算）", None)
            return
        labels = {"forward": "正扫", "reverse": "反扫"}
        for direction in result.settings.directions:
            self._append_metric_row(
                result.dut.channel, labels[direction], result.metrics.get(direction)
            )
        if result.average_metrics is not None:
            self._append_metric_row(result.dut.channel, "正反扫平均", result.average_metrics)

    def _append_metric_row(self, channel: int, label: str, metrics: Metrics | None) -> None:
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        values = [f"CH{channel}", label]
        if metrics is None:
            values.extend(["—"] * 5)
        else:
            values.extend(
                [
                    f"{metrics.pce_percent:.5f}",
                    f"{metrics.voc_v:.6g}",
                    f"{metrics.jsc_ma_cm2:.6g}",
                    f"{metrics.ff_percent:.5f}",
                    f"{metrics.pmax_mw_cm2:.6g}",
                ]
            )
        for column, value in enumerate(values):
            self.result_table.setItem(row, column, QTableWidgetItem(value))
        self.result_table.resizeColumnsToContents()

    def _measurement_failed(self, message: str) -> None:
        self.progress_bar.setValue(0)
        QMessageBox.critical(self, "测量失败", message)
        self.statusBar().showMessage("测量失败，源表输出已关闭", 10000)

    def _measurement_stopped(self, message: str) -> None:
        self.progress_bar.setValue(0)
        self.statusBar().showMessage(message, 8000)

    def _thread_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.finish_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.connect_button.setEnabled(True)

    def export_session(self) -> None:
        if not self.session_run_ids:
            QMessageBox.information(self, "没有结果", "当前软件会话还没有完成的测试。")
            return
        try:
            output_dir = Path(self.output_edit.text()).expanduser()
            output_path = timestamped_summary_path(output_dir)
            self.database.export_summary(self.session_run_ids, output_path)
        except Exception as exc:
            QMessageBox.critical(self, "统计导出失败", str(exc))
            return
        QMessageBox.information(
            self,
            "统计导出完成",
            f"已生成：\n{output_path}\n\n源表输出保持关闭。",
        )
        self.statusBar().showMessage(f"已导出 {output_path.name}", 10000)

    def _reload_history(self) -> None:
        self.history_list.blockSignals(True)
        self.history_list.clear()
        for row in self.database.list_runs():
            self._add_history_item(row, checked=False, block_signal=False)
        self.history_list.blockSignals(False)

    def _history_label(self, row: dict) -> str:
        metric_payload = json.loads(row["metrics_json"])
        metric = metric_payload.get("average") or metric_payload.get("forward") or metric_payload.get("reverse")
        pce = "Dark" if row["condition"] == "dark" else (
            f"PCE {metric['pce_percent']:.3f}%" if metric else "PCE —"
        )
        return (
            f"{row['created_at']}  |  CH{row['channel']}  |  "
            f"{row['device_id']}_{row['condition']}_{row['point_name']}  |  {pce}"
        )

    def _add_history_item(
        self, row: dict, checked: bool, block_signal: bool = True
    ) -> None:
        previous = self.history_list.blockSignals(True) if block_signal else False
        item = QListWidgetItem(self._history_label(row))
        item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.history_list.insertItem(0, item)
        if checked:
            try:
                self.selected_history[int(row["id"])] = self.database.load_run(int(row["id"]))
            except Exception:
                item.setCheckState(Qt.CheckState.Unchecked)
        if block_signal:
            self.history_list.blockSignals(previous)

    def _history_item_changed(self, item: QListWidgetItem) -> None:
        run_id = int(item.data(Qt.ItemDataRole.UserRole))
        if item.checkState() == Qt.CheckState.Checked:
            try:
                self.selected_history[run_id] = self.database.load_run(run_id)
            except Exception as exc:
                QMessageBox.warning(self, "无法加载历史曲线", str(exc))
                item.setCheckState(Qt.CheckState.Unchecked)
                return
        else:
            self.selected_history.pop(run_id, None)
        self._redraw_plot()

    def _redraw_plot(self) -> None:
        self.axes.clear()
        colors = {1: "#176b87", 2: "#d35400"}
        line_styles = {"forward": "-", "reverse": "--"}
        for result in reversed(list(self.selected_history.values())):
            for direction, curve in result.curves.items():
                density = curve.current_density(result.dut.area_cm2)
                label = (
                    f"{result.dut.device_id}-{result.dut.point} CH{result.dut.channel} "
                    f"{'正扫' if direction == 'forward' else '反扫'}"
                )
                self.axes.plot(
                    curve.voltage_v,
                    density,
                    line_styles[direction],
                    linewidth=1.5,
                    alpha=0.72,
                    label=label,
                )
        for (channel, direction), (voltage, current, area) in self.temporary_curves.items():
            density = current * 1000.0 / area
            self.axes.plot(
                voltage,
                density,
                line_styles[direction],
                color=colors[channel],
                linewidth=2.5,
                label=f"当前 CH{channel} {'正扫' if direction == 'forward' else '反扫'}",
            )
        self.axes.axhline(0.0, color="#80919b", linewidth=0.8)
        self.axes.axvline(0.0, color="#80919b", linewidth=0.8)
        self.axes.set_xlabel("Voltage (V)")
        self.axes.set_ylabel("Current Density (mA/cm²)")
        self.axes.grid(True, alpha=0.25)
        if self.axes.lines[2:]:
            self.axes.legend(loc="best", fontsize=8)
        self.canvas.draw_idle()

    def _save_settings(self) -> None:
        values = {
            "output_dir": self.output_edit.text(),
            "channel_mode": self.channel_mode_combo.currentData(),
            "single_channel": self.single_channel_combo.currentData(),
            "source_mode": self.source_mode_combo.currentData(),
            "start": self.start_spin.value(),
            "stop": self.stop_spin.value(),
            "count": self.count_spin.value(),
            "scan_plan": self.scan_plan_combo.currentData(),
            "source_delay": self.source_delay_spin.value(),
            "measure_delay": self.measure_delay_spin.value(),
            "compliance": self.compliance_spin.value(),
            "irradiance": self.irradiance_spin.value(),
            "source_range_choice": self.source_range_combo.currentData(),
            "voltage_range_choice": self.voltage_range_combo.currentData(),
            "current_range_choice": self.current_range_combo.currentData(),
            "measure_voltage": self.measure_voltage_check.isChecked(),
            "measure_current": self.measure_current_check.isChecked(),
            "measure_speed": self.measure_speed_combo.currentData(),
            "manual_nplc": self.nplc_spin.value(),
        }
        for key, value in values.items():
            self.app_settings.setValue(key, value)
        self.app_settings.sync()

    def _restore_settings(self) -> None:
        self.output_edit.setText(
            str(self.app_settings.value("output_dir", str(default_output_dir())))
        )
        mappings = (
            (self.channel_mode_combo, "channel_mode"),
            (self.single_channel_combo, "single_channel"),
            (self.source_mode_combo, "source_mode"),
            (self.scan_plan_combo, "scan_plan"),
        )
        for combo, key in mappings:
            value = self.app_settings.value(key)
            if value is not None:
                index = combo.findData(int(value) if key == "single_channel" else value)
                if index >= 0:
                    combo.setCurrentIndex(index)
        for combo, key in (
            (self.source_range_combo, "source_range_choice"),
            (self.voltage_range_combo, "voltage_range_choice"),
            (self.current_range_combo, "current_range_choice"),
            (self.measure_speed_combo, "measure_speed"),
        ):
            value = self.app_settings.value(key)
            if value is not None:
                index = combo.findData(value)
                if index >= 0:
                    combo.setCurrentIndex(index)
        for checkbox, key in (
            (self.measure_voltage_check, "measure_voltage"),
            (self.measure_current_check, "measure_current"),
        ):
            value = self.app_settings.value(key)
            if value is not None:
                checkbox.setChecked(str(value).casefold() in {"1", "true", "yes"})
        for spin, key, default in (
            (self.start_spin, "start", -0.2),
            (self.stop_spin, "stop", 1.2),
            (self.count_spin, "count", 71),
            (self.source_delay_spin, "source_delay", 0.0),
            (self.measure_delay_spin, "measure_delay", 0.0),
            (self.compliance_spin, "compliance", 0.1),
            (self.irradiance_spin, "irradiance", 100.0),
            (self.nplc_spin, "manual_nplc", 1.0),
        ):
            value = self.app_settings.value(key, default)
            spin.setValue(float(value) if isinstance(spin, QDoubleSpinBox) else int(value))
        self._source_mode_changed()
        self._measure_speed_changed()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None:
            self.worker.request_stop()
        if self.thread is not None:
            self.thread.quit()
            if not self.thread.wait(5000):
                self.statusBar().showMessage("源表仍在安全停止，请稍后再次关闭软件。")
                event.ignore()
                return
        self._save_settings()
        self.database.close()
        event.accept()


def create_application() -> QApplication:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    application = QApplication.instance() or QApplication([])
    application.setApplicationName("PCE Studio")
    application.setOrganizationName("OpenAI")
    font_candidates = (
        ("C:/Windows/Fonts/msyh.ttc", "Microsoft YaHei"),
        ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
        ("C:/Windows/Fonts/Deng.ttf", "DengXian"),
    )
    selected_family = "Arial"
    for font_path, fallback_family in font_candidates:
        if not Path(font_path).exists():
            continue
        font_id = QFontDatabase.addApplicationFont(font_path)
        families = QFontDatabase.applicationFontFamilies(font_id)
        selected_family = families[0] if families else fallback_family
        break
    application.setFont(QFont(selected_family, 9))
    import matplotlib

    matplotlib.rcParams["font.sans-serif"] = [selected_family, "Microsoft YaHei", "SimHei"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return application
