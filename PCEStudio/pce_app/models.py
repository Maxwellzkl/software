from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np


Direction = Literal["forward", "reverse"]
ScanPlan = Literal["forward", "reverse", "both"]
SourceMode = Literal["VOLT", "CURR"]
RangeMode = Literal["AUTO", "FIXED", "LIMITED"]
MeasureSpeed = Literal["AUTO", "SHORT", "MEDIUM", "NORMAL", "LONG", "MANUAL"]


@dataclass(frozen=True)
class SweepSettings:
    source_mode: SourceMode = "VOLT"
    start: float = -0.2
    stop: float = 1.2
    count: int = 71
    scan_plan: ScanPlan = "both"
    source_delay_s: float = 0.0
    compliance: float = 0.1
    source_range_auto: bool = True
    source_range: float = 2.0
    measure_voltage: bool = True
    voltage_range_auto: bool = True
    voltage_range_mode: RangeMode = "AUTO"
    voltage_range: float = 2.0
    measure_current: bool = True
    current_range_auto: bool = True
    current_range_mode: RangeMode = "AUTO"
    current_range: float = 0.1
    measure_delay_s: float = 0.0
    nplc_auto: bool = False
    measure_speed: MeasureSpeed = "NORMAL"
    nplc: float = 1.0
    irradiance_mw_cm2: float = 100.0

    @property
    def step(self) -> float:
        return (self.stop - self.start) / (self.count - 1)

    @property
    def directions(self) -> tuple[Direction, ...]:
        if self.scan_plan == "both":
            return ("forward", "reverse")
        return (self.scan_plan,)

    def levels(self, direction: Direction) -> np.ndarray:
        values = np.linspace(self.start, self.stop, self.count, dtype=float)
        return values if direction == "forward" else values[::-1].copy()

    def validate(self) -> None:
        if self.count < 2:
            raise ValueError("VAR1 Count 必须至少为 2。")
        if self.start == self.stop:
            raise ValueError("Start 和 Stop 不能相同。")
        if self.compliance <= 0:
            raise ValueError("Compliance 必须大于 0。")
        if self.measure_speed not in {"AUTO", "SHORT", "MEDIUM", "NORMAL", "LONG", "MANUAL"}:
            raise ValueError("Measure Speed 设置无效。")
        if self.measure_speed == "MANUAL" and not 0.0001 <= self.nplc <= 100.0:
            raise ValueError("Manual NPLC 必须在 0.0001 至 100 PLC 之间。")
        for mode, value, label in (
            (self.voltage_range_mode, self.voltage_range, "电压测量量程"),
            (self.current_range_mode, self.current_range, "电流测量量程"),
        ):
            if mode not in {"AUTO", "FIXED", "LIMITED"}:
                raise ValueError(f"{label}模式无效。")
            if value <= 0:
                raise ValueError(f"{label}必须大于 0。")
        if self.source_mode == "VOLT":
            if max(abs(self.start), abs(self.stop)) > 210.0:
                raise ValueError("B2902B 电压源扫描值不能超过 ±210 V。")
            if self.compliance > 3.03:
                raise ValueError("B2902B 电流 Compliance 不能超过 3.03 A。")
        else:
            if max(abs(self.start), abs(self.stop)) > 3.03:
                raise ValueError("B2902B 电流源扫描值不能超过 ±3.03 A。")
            if self.compliance > 210.0:
                raise ValueError("B2902B 电压 Compliance 不能超过 210 V。")
        if not self.source_range_auto:
            largest_source = max(abs(self.start), abs(self.stop))
            if largest_source > self.source_range * 1.05:
                unit = "V" if self.source_mode == "VOLT" else "A"
                raise ValueError(
                    f"固定 Source Range {self.source_range:g} {unit} 无法覆盖扫描值 "
                    f"{largest_source:g} {unit}。"
                )
        if self.irradiance_mw_cm2 <= 0:
            raise ValueError("光功率密度必须大于 0。")
        if self.source_mode == "VOLT" and not self.measure_current:
            raise ValueError("电压源扫描必须启用电流测量。")
        if self.source_mode == "CURR" and not self.measure_voltage:
            raise ValueError("电流源扫描必须启用电压测量。")
        for value, label in (
            (self.source_delay_s, "Source Delay"),
            (self.measure_delay_s, "Measure Delay"),
        ):
            if value < 0:
                raise ValueError(f"{label} 不能小于 0。")


@dataclass(frozen=True)
class ChannelDut:
    channel: int
    device_id: str
    point: str
    area_cm2: float
    condition: Literal["light", "dark"]

    def validate(self) -> None:
        if self.channel not in (1, 2):
            raise ValueError("通道只能是 CH1 或 CH2。")
        if not self.device_id.strip():
            raise ValueError(f"CH{self.channel} 的器件编号不能为空。")
        if not self.point.strip():
            raise ValueError(f"CH{self.channel} 的 Point 不能为空。")
        if self.area_cm2 <= 0:
            raise ValueError(f"CH{self.channel} 的面积必须大于 0。")


@dataclass
class CurveData:
    direction: Direction
    voltage_v: np.ndarray
    current_a: np.ndarray
    elapsed_s: np.ndarray

    def current_density(self, area_cm2: float) -> np.ndarray:
        return np.asarray(self.current_a, dtype=float) * 1000.0 / area_cm2


@dataclass(frozen=True)
class Metrics:
    pce_percent: float
    voc_v: float
    jsc_ma_cm2: float
    ff_percent: float
    pmax_mw_cm2: float


@dataclass
class ChannelRunResult:
    dut: ChannelDut
    settings: SweepSettings
    curves: dict[Direction, CurveData] = field(default_factory=dict)
    metrics: dict[Direction, Metrics] = field(default_factory=dict)
    average_metrics: Metrics | None = None
    raw_file: str = ""
    run_id: int | None = None
