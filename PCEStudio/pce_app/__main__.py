from __future__ import annotations

import os
import sys
from pathlib import Path

from .main_window import MainWindow, create_application


def main() -> int:
    smoke_dir_value = os.environ.get("PCE_STUDIO_SMOKE_DIR")
    smoke_log = None
    if os.environ.get("PCE_STUDIO_SMOKE_TEST") == "1" and smoke_dir_value:
        smoke_dir = Path(smoke_dir_value)
        smoke_dir.mkdir(parents=True, exist_ok=True)
        smoke_log = smoke_dir / "startup.log"
        smoke_log.write_text("main entered\n", encoding="utf-8")
    application = create_application()
    if smoke_log:
        with smoke_log.open("a", encoding="utf-8") as handle:
            handle.write("application created\n")
    window = MainWindow()
    if smoke_log:
        with smoke_log.open("a", encoding="utf-8") as handle:
            handle.write("window created\n")
    window.show()
    if os.environ.get("PCE_STUDIO_SMOKE_TEST") == "1":
        from .smoke import schedule_smoke_test

        schedule_smoke_test(application, window)
        if smoke_log:
            with smoke_log.open("a", encoding="utf-8") as handle:
                handle.write("smoke scheduled\n")
    return application.exec()


if __name__ == "__main__":
    sys.exit(main())
