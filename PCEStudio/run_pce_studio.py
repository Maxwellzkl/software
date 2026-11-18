import os
import traceback
from pathlib import Path


_smoke_dir = os.environ.get("PCE_STUDIO_SMOKE_DIR")
if os.environ.get("PCE_STUDIO_SMOKE_TEST") == "1" and _smoke_dir:
    _smoke_path = Path(_smoke_dir)
    _smoke_path.mkdir(parents=True, exist_ok=True)
    (_smoke_path / "runner.log").write_text("runner entered\n", encoding="utf-8")

try:
    import PySide6.QtCore

    if os.environ.get("PCE_STUDIO_SMOKE_TEST") == "1" and _smoke_dir:
        with (_smoke_path / "runner.log").open("a", encoding="utf-8") as handle:
            handle.write("QtCore imported\n")

    import PySide6.QtGui

    if os.environ.get("PCE_STUDIO_SMOKE_TEST") == "1" and _smoke_dir:
        with (_smoke_path / "runner.log").open("a", encoding="utf-8") as handle:
            handle.write("QtGui imported\n")

    import PySide6.QtWidgets

    if os.environ.get("PCE_STUDIO_SMOKE_TEST") == "1" and _smoke_dir:
        with (_smoke_path / "runner.log").open("a", encoding="utf-8") as handle:
            handle.write("QtWidgets imported\n")

    from pce_app.__main__ import main
except Exception:
    if os.environ.get("PCE_STUDIO_SMOKE_TEST") == "1" and _smoke_dir:
        with (_smoke_path / "runner.log").open("a", encoding="utf-8") as handle:
            handle.write(traceback.format_exc())
    raise


if __name__ == "__main__":
    raise SystemExit(main())
