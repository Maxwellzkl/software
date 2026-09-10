from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot

from .calculations import CalculationError, average_metrics, calculate_metrics
from .instrument import B2902BSession, SIMULATOR_RESOURCE, SimulatedB2902BSession
from .models import ChannelDut, ChannelRunResult, SweepSettings


class MeasurementWorker(QObject):
    status = Signal(str)
    progress = Signal(int)
    pass_finished = Signal(int, str, object, object, float)
    warning = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    stopped = Signal(str)
    done = Signal()

    def __init__(
        self,
        resource_address: str,
        settings: SweepSettings,
        duts: list[ChannelDut],
    ) -> None:
        super().__init__()
        self.resource_address = resource_address
        self.settings = settings
        self.duts = duts
        self.cancel_event = threading.Event()

    def request_stop(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        results = {
            dut.channel: ChannelRunResult(dut=dut, settings=self.settings)
            for dut in self.duts
        }
        session_type = (
            SimulatedB2902BSession
            if self.resource_address == SIMULATOR_RESOURCE
            else B2902BSession
        )
        try:
            self.settings.validate()
            for dut in self.duts:
                dut.validate()
            session_args = () if session_type is SimulatedB2902BSession else (self.resource_address,)
            with session_type(*session_args) as session:
                directions = self.settings.directions
                for pass_index, direction in enumerate(directions):
                    if self.cancel_event.is_set():
                        raise InterruptedError("测量已由用户停止。")
                    direction_text = "正扫" if direction == "forward" else "反扫"
                    self.status.emit(f"正在执行{direction_text}…")

                    def report(value: int, index: int = pass_index) -> None:
                        aggregate = int((index * 100 + value) / len(directions))
                        self.progress.emit(aggregate)

                    curves = session.acquire_pass(
                        self.settings,
                        self.duts,
                        direction,
                        self.cancel_event,
                        report,
                    )
                    for dut in self.duts:
                        curve = curves[dut.channel]
                        results[dut.channel].curves[direction] = curve
                        self.pass_finished.emit(
                            dut.channel,
                            direction,
                            curve.voltage_v,
                            curve.current_a,
                            dut.area_cm2,
                        )
                        if dut.condition == "light":
                            try:
                                results[dut.channel].metrics[direction] = calculate_metrics(
                                    curve.voltage_v,
                                    curve.current_a,
                                    dut.area_cm2,
                                    self.settings.irradiance_mw_cm2,
                                )
                            except CalculationError as exc:
                                self.warning.emit(
                                    f"CH{dut.channel} {direction_text}性能参数未计算：{exc}"
                                )

            if self.settings.scan_plan == "both":
                for result in results.values():
                    if result.dut.condition != "light":
                        continue
                    forward = result.metrics.get("forward")
                    reverse = result.metrics.get("reverse")
                    if forward and reverse:
                        result.average_metrics = average_metrics(
                            forward,
                            reverse,
                            self.settings.irradiance_mw_cm2,
                        )
            self.progress.emit(100)
            self.status.emit("测量完成，正在保存数据…")
            self.finished.emit(list(results.values()))
        except InterruptedError as exc:
            self.stopped.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.done.emit()
