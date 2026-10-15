from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
        settings = window._sweep_settings()
        assert settings.measure_speed == "NORMAL"
        assert settings.nplc == 1.0
        assert settings.current_range_mode == "LIMITED"
        assert settings.current_range == 1e-6
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
