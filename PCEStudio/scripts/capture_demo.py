from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
SCREENSHOT_DIR = PROJECT_ROOT / "output" / "screenshots"
DEMO_DIR = PROJECT_ROOT / "output" / "demo"
os.environ["PCE_STUDIO_DATA_DIR"] = str(DEMO_DIR / "appdata_visual_qa_v2")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QMessageBox, QScrollArea

from pce_app.instrument import SIMULATOR_RESOURCE
from pce_app.main_window import MainWindow, create_application


def main() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    application = create_application()
    QMessageBox.critical = staticmethod(
        lambda _parent, title, message, *args, **kwargs: print(f"CRITICAL {title}: {message}")
    )
    QMessageBox.warning = staticmethod(
        lambda _parent, title, message, *args, **kwargs: print(f"WARNING {title}: {message}")
    )
    QMessageBox.information = staticmethod(
        lambda _parent, title, message, *args, **kwargs: print(f"INFO {title}: {message}")
    )
    window = MainWindow()
    window.channel_mode_combo.setCurrentIndex(1)
    window.device_panels[1].device_edit.setText("Device_A")
    window.device_panels[1].point_edit.setText("1")
    window.device_panels[1].area_spin.setValue(0.04)
    window.device_panels[2].device_edit.setText("Device_B")
    window.device_panels[2].point_edit.setText("2")
    window.device_panels[2].area_spin.setValue(0.052)
    window.output_edit.setText(str(DEMO_DIR))
    window.refresh_resources()
    simulator_index = window.resource_combo.findData(SIMULATOR_RESOURCE)
    window.resource_combo.setCurrentIndex(simulator_index)
    window.show()
    application.processEvents()
    simulator_index = window.resource_combo.findData(SIMULATOR_RESOURCE)
    window.resource_combo.setCurrentIndex(simulator_index)
    window.connect_resource()

    window.start_measurement()
    event_loop = QEventLoop()
    if window.thread is not None:
        window.thread.finished.connect(event_loop.quit)
    QTimer.singleShot(10000, event_loop.quit)
    event_loop.exec()
    application.processEvents()
    if window.thread is not None:
        raise RuntimeError("模拟测量未在 10 秒内完成。")
    if not window.session_run_ids:
        raise RuntimeError("模拟测量没有生成结果。")

    summary_path = DEMO_DIR / "output_file_demo.xlsx"
    window.database.export_summary(window.session_run_ids, summary_path)
    screenshot_path = SCREENSHOT_DIR / "PCEStudio_UI.png"
    if not window.grab().save(str(screenshot_path)):
        raise RuntimeError("界面截图保存失败。")
    scroll = window.findChild(QScrollArea)
    if scroll is not None:
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        application.processEvents()
    settings_screenshot_path = SCREENSHOT_DIR / "PCEStudio_Output_Settings_UI.png"
    if not window.grab().save(str(settings_screenshot_path)):
        raise RuntimeError("输出设置界面截图保存失败。")
    print(screenshot_path)
    print(settings_screenshot_path)
    print(summary_path)
    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
