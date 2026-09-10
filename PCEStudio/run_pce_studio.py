import os
from pathlib import Path


_smoke_dir = os.environ.get("PCE_STUDIO_SMOKE_DIR")
if os.environ.get("PCE_STUDIO_SMOKE_TEST") == "1" and _smoke_dir:
    _smoke_path = Path(_smoke_dir)
    _smoke_path.mkdir(parents=True, exist_ok=True)
    (_smoke_path / "runner.log").write_text("runner entered\n", encoding="utf-8")

import PySide6.QtWidgets

from pce_app.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
