from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox

import pce_app.main_window as main_window_module
from pce_app.main_window import (
    MainWindow,
    NoWheelComboBox,
    NoWheelDoubleSpinBox,
    NoWheelSpinBox,
    create_application,
)


def test_parameter_controls_and_output_directory_picker(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PCE_STUDIO_DATA_DIR", str(tmp_path / "appdata"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    application = create_application()
    window = MainWindow()
    try:
        speeds = [
            window.measure_speed_combo.itemData(index)
            for index in range(window.measure_speed_combo.count())
        ]
        assert speeds == ["AUTO", "SHORT", "MEDIUM", "NORMAL", "LONG", "MANUAL"]

        window.measure_speed_combo.setCurrentIndex(
            window.measure_speed_combo.findData("NORMAL")
        )
        window.current_range_combo.setCurrentIndex(
            window.current_range_combo.findData("LIMITED:1e-06")
        )
        window.source_range_combo.setCurrentIndex(
            window.source_range_combo.findData("FIXED:20")
        )
        settings = window._sweep_settings()
        assert settings.measure_speed == "NORMAL"
        assert settings.nplc == 1.0
        assert settings.current_range_mode == "LIMITED"
        assert settings.current_range == 1e-6
        assert settings.voltage_range_mode == "FIXED"
        assert settings.voltage_range == 20.0
        assert not window.voltage_range_combo.isEnabled()
        assert window.compliance_spin.suffix() == " A"
        assert window.output_browse_button.text() == "选择…"

        selected_dir = tmp_path / "selected-output"
        monkeypatch.setattr(
            main_window_module.QFileDialog,
            "getExistingDirectory",
            lambda *_args, **_kwargs: str(selected_dir),
        )
        window.output_browse_button.click()
        application.processEvents()
        assert window.output_edit.text() == str(selected_dir)
    finally:
        window.close()


def test_voltage_measure_range_follows_source_range_and_trigger_is_adjustable(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("PCE_STUDIO_DATA_DIR", str(tmp_path / "appdata"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    application = create_application()
    window = MainWindow()
    try:
        assert window.source_mode_combo.currentData() == "VOLT"
        assert not window.voltage_range_combo.isEnabled()
        window.source_range_combo.setCurrentIndex(
            window.source_range_combo.findData("FIXED:20")
        )
        assert window.voltage_range_combo.currentData() == "FIXED:20"

        window.source_mode_combo.setCurrentIndex(
            window.source_mode_combo.findData("CURR")
        )
        assert window.voltage_range_combo.isEnabled()
        assert not window.current_range_combo.isEnabled()
        window.voltage_range_combo.setCurrentIndex(
            window.voltage_range_combo.findData("LIMITED:2")
        )
        settings = window._sweep_settings()
        assert settings.voltage_range_mode == "LIMITED"
        assert settings.voltage_range == 2.0

        window.measure_voltage_check.setChecked(False)
        assert not window.voltage_range_combo.isEnabled()
        window.measure_voltage_check.setChecked(True)
        assert window.voltage_range_combo.isEnabled()

        assert window.trigger_mode_combo.currentData() == "AUTO"
        assert not window.minimum_auto_trigger_check.isChecked()
        assert not window.trigger_period_spin.isEnabled()

        window.minimum_auto_trigger_check.setChecked(True)
        assert window.trigger_period_spin.isEnabled()
        auto_min_settings = window._sweep_settings()
        assert auto_min_settings.trigger_mode == "AUTO"
        assert auto_min_settings.minimum_auto_trigger_period_enabled
        assert auto_min_settings.trigger_period_s == 0.1
        window.trigger_period_spin.setValue(1.0)
        assert "有效下限 ≈ 1" in window.estimated_period_label.text()
        window.trigger_period_spin.setValue(0.1)

        window.trigger_mode_combo.setCurrentIndex(
            window.trigger_mode_combo.findData("TIMER")
        )
        assert not window.minimum_auto_trigger_check.isEnabled()
        assert not window.minimum_auto_trigger_check.isChecked()
        assert window.trigger_period_spin.isEnabled()
        window.trigger_period_spin.setValue(0.25)
        timer_settings = window._sweep_settings()
        assert timer_settings.trigger_mode == "TIMER"
        assert timer_settings.trigger_period_s == 0.25
        assert "预计点周期" in window.estimated_period_label.text()
    finally:
        window.close()


def test_requested_startup_defaults_override_previous_scan_settings(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("PCE_STUDIO_DATA_DIR", str(tmp_path / "appdata"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    previous = QSettings("OpenAI", "PCEStudio")
    previous.setValue("source_mode", "CURR")
    previous.setValue("count", 71)
    previous.setValue("source_delay", 1.5)
    previous.setValue("measure_delay", 0.0)
    previous.setValue("source_range_choice", "AUTO:1e-07")
    previous.setValue("voltage_range_choice", "AUTO:0.2")
    previous.setValue("current_range_choice", "FIXED:0.1")
    previous.setValue("measure_speed", "SHORT")
    previous.setValue("measure_voltage", False)
    previous.setValue("measure_current", False)
    previous.setValue("trigger_mode", "TIMER")
    previous.setValue("minimum_auto_trigger_period", True)
    previous.setValue("trigger_period", 5.0)
    previous.sync()

    application = create_application()
    window = MainWindow()
    try:
        settings = window._sweep_settings()
        assert settings.source_mode == "VOLT"
        assert settings.count == 801
        assert settings.source_delay_s == 0.0
        assert settings.measure_delay_s == 0.05
        assert not settings.source_range_auto
        assert settings.source_range == 2.0
        assert settings.voltage_range_mode == "FIXED"
        assert settings.voltage_range == 2.0
        assert settings.current_range_mode == "AUTO"
        assert settings.current_range == 1e-7
        assert settings.measure_speed == "NORMAL"
        assert settings.nplc == 1.0
        assert settings.measure_voltage
        assert settings.measure_current
        assert settings.trigger_mode == "AUTO"
        assert not settings.minimum_auto_trigger_period_enabled
        assert settings.trigger_period_s == 0.1
        assert not window.trigger_period_spin.isEnabled()
        assert not window.windowIcon().isNull()
        assert not application.windowIcon().isNull()
    finally:
        window.close()


def test_parameter_panel_can_collapse_and_expand(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PCE_STUDIO_DATA_DIR", str(tmp_path / "appdata"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    application = create_application()
    window = MainWindow()
    try:
        window.resize(1200, 760)
        window.show()
        application.processEvents()
        assert window.left_panel.isVisible()

        window.parameter_toggle_button.click()
        application.processEvents()
        assert not window.left_panel.isVisible()
        assert window.compact_actions.isVisible()
        assert window.compact_start_button.isVisible()
        assert window.compact_stop_button.isVisible()
        assert window.compact_finish_button.isVisible()
        assert "展开参数" in window.parameter_toggle_button.text()

        window._set_progress(37)
        window._set_measurement_running(True)
        assert window.progress_bar.value() == 37
        assert window.compact_progress_bar.value() == 37
        assert not window.start_button.isEnabled()
        assert not window.compact_start_button.isEnabled()
        assert window.stop_button.isEnabled()
        assert window.compact_stop_button.isEnabled()
        assert not window.finish_button.isEnabled()
        assert not window.compact_finish_button.isEnabled()
        window._set_measurement_running(False)

        window.parameter_toggle_button.click()
        application.processEvents()
        assert window.left_panel.isVisible()
        assert not window.compact_actions.isVisible()
        assert "收起参数" in window.parameter_toggle_button.text()
        assert 350 <= window.left_panel.width() <= 400
    finally:
        window.close()


def test_parameter_wheels_are_ignored_and_small_screen_layout_stays_compact(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("PCE_STUDIO_DATA_DIR", str(tmp_path / "appdata"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    application = create_application()
    window = MainWindow()

    class FakeWheelEvent:
        def __init__(self) -> None:
            self.ignored = False

        def ignore(self) -> None:
            self.ignored = True

    try:
        assert all(
            isinstance(widget, NoWheelComboBox)
            for widget in window.findChildren(QComboBox)
        )
        assert all(
            isinstance(widget, (NoWheelSpinBox, NoWheelDoubleSpinBox))
            for widget in window.findChildren(QSpinBox)
        )
        assert all(
            isinstance(widget, NoWheelDoubleSpinBox)
            for widget in window.findChildren(QDoubleSpinBox)
        )

        for widget in (
            window.measure_speed_combo,
            window.count_spin,
            window.start_spin,
            window.device_panels[1].area_spin,
        ):
            wheel_event = FakeWheelEvent()
            value_before = (
                widget.currentIndex()
                if isinstance(widget, QComboBox)
                else widget.value()
            )
            widget.wheelEvent(wheel_event)
            value_after = (
                widget.currentIndex()
                if isinstance(widget, QComboBox)
                else widget.value()
            )
            assert wheel_event.ignored
            assert value_after == value_before

        window.resize(1000, 650)
        window.show()
        application.processEvents()
        assert window.minimumSize().width() == 820
        assert window.minimumSize().height() == 560
        assert 350 <= window.left_panel.width() <= 420

        parameter_scrollbar = window.parameter_scroll.verticalScrollBar()
        parameter_scrollbar.setValue(0)
        start_value = window.start_spin.value()
        wheel_position = window.start_spin.mapTo(
            window, window.start_spin.rect().center()
        )
        QTest.wheelEvent(
            window.windowHandle(),
            QPointF(wheel_position),
            QPoint(0, -120),
        )
        application.processEvents()
        assert window.start_spin.value() == start_value
        assert parameter_scrollbar.value() > 0

        width_before = window.left_panel.width()
        window.start_button.setEnabled(False)
        window.stop_button.setEnabled(True)
        window._append_metric_row(1, "正反扫平均", None)
        application.processEvents()
        assert 350 <= window.left_panel.width() <= 420
        assert window.left_panel.width() == width_before
    finally:
        window.close()


def test_old_database_runs_are_not_loaded_into_new_session_history(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("PCE_STUDIO_DATA_DIR", str(tmp_path / "appdata"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    previous_row = {
        "id": 42,
        "created_at": "2026-01-01T12:00:00",
        "channel": 1,
        "device_id": "OLD",
        "point_name": "1",
        "condition": "light",
        "metrics_json": '{"average": null, "forward": null, "reverse": null}',
    }
    monkeypatch.setattr(
        main_window_module.Database,
        "list_runs",
        lambda _database, _limit=200: [previous_row],
    )
    application = create_application()
    window = MainWindow()
    try:
        application.processEvents()
        assert window.history_list.count() == 0
        assert window.details_tabs.tabText(1) == "本次运行曲线"

        window._add_history_item(previous_row, checked=False)
        assert window.history_list.count() == 1
    finally:
        window.close()


def test_light_history_label_keeps_all_primary_metrics(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PCE_STUDIO_DATA_DIR", str(tmp_path / "appdata"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    application = create_application()
    window = MainWindow()
    row = {
        "id": 7,
        "created_at": "2026-11-18T12:00:00",
        "channel": 2,
        "device_id": "D61",
        "point_name": "3",
        "condition": "light",
        "metrics_json": (
            '{"average":{"pce_percent":12.3456,"voc_v":0.9876,'
            '"jsc_ma_cm2":21.234,"ff_percent":58.765},'
            '"forward":null,"reverse":null}'
        ),
    }
    try:
        label = window._history_label(row)
        assert "PCE 12.346%" in label
        assert "Jsc 21.23 mA/cm²" in label
        assert "Voc 0.9876 V" in label
        assert "FF 58.765%" in label
    finally:
        window.close()


def test_plot_uses_linear_and_absolute_log_current_density_axes(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("PCE_STUDIO_DATA_DIR", str(tmp_path / "appdata"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    application = create_application()
    window = MainWindow()
    try:
        voltage = np.asarray([-0.2, 0.0, 0.8])
        current = np.asarray([-4e-4, 0.0, 2e-4])
        window.temporary_curves[(1, "forward")] = (voltage, current, 0.04)
        window._redraw_plot()
        application.processEvents()

        assert len(window.figure.axes) == 2
        assert window.linear_axes.get_yscale() == "linear"
        assert window.log_axes.get_yscale() == "log"
        assert np.allclose(window.linear_axes.lines[0].get_ydata(), [-10.0, 0.0, 5.0])
        log_values = window.log_axes.lines[0].get_ydata()
        assert np.allclose(log_values[[0, 2]], [10.0, 5.0])
        assert np.isnan(log_values[1])
    finally:
        window.close()
