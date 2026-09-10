from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable

import numpy as np
import pyvisa as visa

from .models import ChannelDut, CurveData, Direction, SweepSettings


SIMULATOR_RESOURCE = "SIM::B2902B::INSTR"
MEASURE_SPEED_NPLC = {
    "SHORT": 0.01,
    "MEDIUM": 0.1,
    "NORMAL": 1.0,
    "LONG": 10.0,
}


class InstrumentError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisaResourceInfo:
    address: str
    label: str


def enumerate_usb_resources() -> list[VisaResourceInfo]:
    """Enumerate USB VISA resources without opening output channels."""
    try:
        manager = visa.ResourceManager()
        try:
            resources = manager.list_resources("USB?*::INSTR")
        finally:
            manager.close()
    except Exception as exc:
        raise InstrumentError(
            "无法加载 VISA 或枚举 USB 设备。请安装 Keysight IO Libraries Suite。"
        ) from exc
    return [VisaResourceInfo(address=value, label=value) for value in resources]


def identify_resource(address: str) -> str:
    if address == SIMULATOR_RESOURCE:
        return "PCE Studio Simulator, B2902B, SIM0001, 1.0"
    try:
        manager = visa.ResourceManager()
        resource = manager.open_resource(address)
        try:
            resource.timeout = 5000
            resource.read_termination = "\n"
            resource.write_termination = "\n"
            return str(resource.query("*IDN?")).strip()
        finally:
            resource.close()
            manager.close()
    except Exception as exc:
        raise InstrumentError(f"无法连接 VISA 设备：{address}") from exc


class B2902BSession:
    """One short-lived VISA session used by a background measurement worker."""

    def __init__(self, address: str) -> None:
        self.address = address
        self._manager = None
        self._instrument = None

    def __enter__(self) -> "B2902BSession":
        try:
            self._manager = visa.ResourceManager()
            self._instrument = self._manager.open_resource(self.address)
            self._instrument.timeout = 5000
            self._instrument.read_termination = "\n"
            self._instrument.write_termination = "\n"
            identity = str(self._instrument.query("*IDN?")).strip()
            if "B2902B" not in identity.upper():
                raise InstrumentError(f"检测到的设备不是 B2902B：{identity}")
            self._instrument.write("*RST")
            self._instrument.write("*CLS")
            self._instrument.write(":FORM:DATA ASC")
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.safe_output_off((1, 2))
        self.close()

    @property
    def instrument(self):
        if self._instrument is None:
            raise InstrumentError("VISA 会话尚未打开。")
        return self._instrument

    def close(self) -> None:
        if self._instrument is not None:
            try:
                self._instrument.close()
            except Exception:
                pass
            self._instrument = None
        if self._manager is not None:
            try:
                self._manager.close()
            except Exception:
                pass
            self._manager = None

    def safe_output_off(self, channels: Iterable[int]) -> None:
        if self._instrument is None:
            return
        try:
            self._instrument.write(":ABOR")
        except Exception:
            pass
        for channel in channels:
            try:
                self._instrument.write(f":OUTP{channel} OFF")
            except Exception:
                pass

    def _configure_channel(
        self,
        channel: int,
        settings: SweepSettings,
        levels: np.ndarray,
    ) -> None:
        instrument = self.instrument
        source = settings.source_mode
        complementary = "CURR" if source == "VOLT" else "VOLT"
        list_values = ",".join(f"{value:.12g}" for value in levels)

        instrument.write(f":SOUR{channel}:FUNC:MODE {source}")
        instrument.write(f":SOUR{channel}:FUNC:SHAP DC")
        instrument.write(f":SOUR{channel}:{source}:MODE LIST")
        instrument.write(f":SOUR{channel}:{source} {levels[0]:.12g}")
        instrument.write(f":SOUR{channel}:LIST:{source} {list_values}")

        if settings.source_range_auto:
            instrument.write(f":SOUR{channel}:{source}:RANG:AUTO ON")
        else:
            instrument.write(f":SOUR{channel}:{source}:RANG:AUTO OFF")
            instrument.write(f":SOUR{channel}:{source}:RANG {settings.source_range:.12g}")

        instrument.write(f":SENS{channel}:FUNC:OFF:ALL")
        functions: list[str] = []
        if settings.measure_voltage:
            functions.append('"VOLT"')
        if settings.measure_current:
            functions.append('"CURR"')
        instrument.write(f":SENS{channel}:FUNC {','.join(functions)}")

        for function, range_mode, range_value, enabled in (
            (
                "VOLT",
                settings.voltage_range_mode,
                settings.voltage_range,
                settings.measure_voltage,
            ),
            (
                "CURR",
                settings.current_range_mode,
                settings.current_range,
                settings.measure_current,
            ),
        ):
            if not enabled:
                continue
            if range_mode == "AUTO":
                instrument.write(f":SENS{channel}:{function}:RANG:AUTO ON")
            elif range_mode == "LIMITED":
                instrument.write(f":SENS{channel}:{function}:RANG:AUTO ON")
                instrument.write(
                    f":SENS{channel}:{function}:RANG:AUTO:LLIM {range_value:.12g}"
                )
            else:
                instrument.write(f":SENS{channel}:{function}:RANG:AUTO OFF")
                instrument.write(f":SENS{channel}:{function}:RANG {range_value:.12g}")

            if settings.measure_speed == "AUTO":
                instrument.write(f":SENS{channel}:{function}:NPLC:AUTO ON")
            else:
                nplc = MEASURE_SPEED_NPLC.get(settings.measure_speed, settings.nplc)
                instrument.write(f":SENS{channel}:{function}:NPLC:AUTO OFF")
                instrument.write(f":SENS{channel}:{function}:NPLC {nplc:.12g}")

        instrument.write(f":SENS{channel}:{complementary}:PROT {settings.compliance:.12g}")
        instrument.write(f":TRIG{channel}:SOUR AINT")
        instrument.write(f":TRIG{channel}:COUN {len(levels)}")
        instrument.write(f":TRIG{channel}:TRAN:DEL {settings.source_delay_s:.12g}")
        instrument.write(f":TRIG{channel}:ACQ:DEL {settings.measure_delay_s:.12g}")

    def _wait_for_complete(
        self,
        cancel_event: threading.Event,
        timeout_s: float,
    ) -> None:
        instrument = self.instrument
        instrument.write("*OPC")
        started = time.monotonic()
        while True:
            if cancel_event.is_set():
                raise InterruptedError("测量已由用户停止。")
            try:
                event_status = int(float(instrument.query("*ESR?").strip()))
            except Exception as exc:
                raise InstrumentError("等待源表完成扫描时通信失败。") from exc
            if event_status & 1:
                return
            if time.monotonic() - started > timeout_s:
                raise InstrumentError("源表扫描超时。请检查延迟、NPLC 和 VISA 连接。")
            time.sleep(0.05)

    def _fetch(self, command: str, expected_count: int) -> np.ndarray:
        try:
            values = np.asarray(self.instrument.query_ascii_values(command), dtype=float)
        except Exception as exc:
            raise InstrumentError(f"读取源表数据失败：{command}") from exc
        if values.size != expected_count:
            raise InstrumentError(
                f"源表返回 {values.size} 个点，预期 {expected_count} 个点。"
            )
        return values

    def acquire_pass(
        self,
        settings: SweepSettings,
        duts: list[ChannelDut],
        direction: Direction,
        cancel_event: threading.Event,
        progress: Callable[[int], None] | None = None,
    ) -> dict[int, CurveData]:
        channels = [dut.channel for dut in duts]
        levels = settings.levels(direction)
        for channel in channels:
            self._configure_channel(channel, settings, levels)

        channel_list = ",".join(str(channel) for channel in channels)
        try:
            for channel in channels:
                self.instrument.write(f":OUTP{channel} ON")
            if progress:
                progress(10)
            self.instrument.write(f":INIT (@{channel_list})")
            dwell = settings.source_delay_s + settings.measure_delay_s
            if settings.measure_speed != "AUTO":
                dwell += MEASURE_SPEED_NPLC.get(settings.measure_speed, settings.nplc) / 50.0
            timeout_s = max(15.0, len(levels) * (dwell + 0.2) + 10.0)
            self._wait_for_complete(cancel_event, timeout_s)
            if progress:
                progress(80)

            curves: dict[int, CurveData] = {}
            for channel in channels:
                if settings.measure_voltage:
                    voltage = self._fetch(
                        f":FETC:ARR:VOLT? (@{channel})", len(levels)
                    )
                elif settings.source_mode == "VOLT":
                    voltage = levels.copy()
                else:
                    raise InstrumentError("没有可用的电压数据。")

                if settings.measure_current:
                    current = self._fetch(
                        f":FETC:ARR:CURR? (@{channel})", len(levels)
                    )
                elif settings.source_mode == "CURR":
                    current = levels.copy()
                else:
                    raise InstrumentError("没有可用的电流数据。")

                total = max(dwell, 0.001) * max(len(levels) - 1, 1)
                elapsed = np.linspace(0.0, total, len(levels), dtype=float)
                curves[channel] = CurveData(direction, voltage, current, elapsed)
            if progress:
                progress(100)
            return curves
        finally:
            self.safe_output_off(channels)


class SimulatedB2902BSession:
    """Deterministic two-channel simulator for UI and calculation verification."""

    def __enter__(self) -> "SimulatedB2902BSession":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def safe_output_off(self, channels: Iterable[int]) -> None:
        return None

    def acquire_pass(
        self,
        settings: SweepSettings,
        duts: list[ChannelDut],
        direction: Direction,
        cancel_event: threading.Event,
        progress: Callable[[int], None] | None = None,
    ) -> dict[int, CurveData]:
        levels = settings.levels(direction)
        curves: dict[int, CurveData] = {}
        for percent in (10, 35, 60, 85):
            if cancel_event.is_set():
                raise InterruptedError("测量已由用户停止。")
            if progress:
                progress(percent)
            time.sleep(0.02)

        for dut in duts:
            if settings.source_mode == "VOLT":
                voltage = levels.copy()
                if dut.condition == "light":
                    voc = 0.98 + 0.015 * (dut.channel - 1)
                    jsc = 23.0 - 0.8 * (dut.channel - 1)
                    hysteresis = 1.02 if direction == "reverse" else 0.98
                    ratio = np.clip(voltage / voc, -2.0, 2.0)
                    density = -jsc * hysteresis * (1.0 - np.power(np.clip(ratio, 0.0, 1.2), 7))
                    above = voltage > voc
                    density[above] = jsc * 2.0 * (np.exp((voltage[above] - voc) * 4.0) - 1.0)
                else:
                    density = 0.01 * (np.exp(np.clip(voltage, -1.0, 1.4) * 5.0) - 1.0)
                current = density * dut.area_cm2 / 1000.0
            else:
                current = levels.copy()
                density = current * 1000.0 / dut.area_cm2
                voltage = 0.98 * np.sign(density + 23.0) * np.power(
                    np.clip(1.0 + density / 23.0, 0.0, None), 1.0 / 7.0
                )
            phase = np.linspace(0.0, 2.0 * math.pi, len(levels))
            current = current + np.sin(phase) * max(np.max(np.abs(current)), 1e-9) * 0.0008
            elapsed = np.linspace(0.0, 0.05, len(levels), dtype=float)
            curves[dut.channel] = CurveData(direction, voltage, current, elapsed)
        if progress:
            progress(100)
        return curves
