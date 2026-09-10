from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings

import pce_app.main_window as main_window_module
from pce_app.main_window import MainWindow, create_application


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
