from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QTimer

from .instrument import SIMULATOR_RESOURCE


def schedule_smoke_test(application, window) -> None:
    """Run a packaged end-to-end simulator check when explicitly enabled by env."""
    output_dir = Path(os.environ.get("PCE_STUDIO_SMOKE_DIR", "smoke_output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()

    def log(message: str) -> None:
        with (output_dir / "smoke-progress.log").open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")

    log("smoke helper entered")

    def start() -> None:
        try:
            log("start callback entered")
            window.channel_mode_combo.setCurrentIndex(1)
            window.device_panels[1].device_edit.setText("Smoke_CH1")
            window.device_panels[1].point_edit.setText("1")
            window.device_panels[1].area_spin.setValue(0.04)
            window.device_panels[2].device_edit.setText("Smoke_CH2")
            window.device_panels[2].point_edit.setText("2")
            window.device_panels[2].area_spin.setValue(0.052)
            window.output_edit.setText(str(output_dir))
            window.refresh_resources()
            log("resources refreshed")
            index = window.resource_combo.findData(SIMULATOR_RESOURCE)
            window.resource_combo.setCurrentIndex(index)
            window.connect_resource()
            log("simulator connected")
            window.start_measurement()
            log("measurement requested")
            QTimer.singleShot(100, check)
        except Exception as exc:
            fail(exc)

    def check() -> None:
        if window.thread is None and window.session_run_ids:
            try:
                log("measurement finished")
                summary = output_dir / "output_file_smoke.xlsx"
                window.database.export_summary(window.session_run_ids, summary)
                window.grab().save(str(output_dir / "packaged_ui.png"))
                log("artifacts written")
                (output_dir / "smoke-ok.txt").write_text(
                    "PCEStudio packaged simulator workflow completed.\n", encoding="utf-8"
                )
                window.close()
                application.quit()
                return
            except Exception as exc:
                fail(exc)
                return
        if time.monotonic() - started_at > 20.0:
            fail(TimeoutError("Packaged smoke test timed out."))
            return
        QTimer.singleShot(100, check)

    def fail(exc: Exception) -> None:
        log(f"failure: {type(exc).__name__}: {exc}")
        (output_dir / "smoke-failed.txt").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        application.quit()

    QTimer.singleShot(300, start)
