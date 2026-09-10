from PySide6.QtCore import QCoreApplication

from pce_app.instrument import SIMULATOR_RESOURCE
from pce_app.models import ChannelDut, SweepSettings
from pce_app.worker import MeasurementWorker


def test_dual_channel_simulated_measurement() -> None:
    application = QCoreApplication.instance() or QCoreApplication([])
    settings = SweepSettings(start=-0.2, stop=1.2, count=71, scan_plan="both")
    duts = [
        ChannelDut(1, "D01", "1", 0.04, "light"),
        ChannelDut(2, "D02", "4", 0.052, "dark"),
    ]
    completed = []
    failures = []
    worker = MeasurementWorker(SIMULATOR_RESOURCE, settings, duts)
    worker.finished.connect(completed.append)
    worker.failed.connect(failures.append)
    worker.run()
    application.processEvents()

    assert failures == []
    assert len(completed) == 1
    results = completed[0]
    assert len(results) == 2
    light = next(result for result in results if result.dut.channel == 1)
    dark = next(result for result in results if result.dut.channel == 2)
    assert set(light.curves) == {"forward", "reverse"}
    assert set(light.metrics) == {"forward", "reverse"}
    assert light.average_metrics is not None
    assert dark.metrics == {}
    assert dark.average_metrics is None

