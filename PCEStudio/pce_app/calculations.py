from __future__ import annotations

import math

import numpy as np

from .models import Metrics


class CalculationError(ValueError):
    """Raised when an I-V curve cannot yield a physical photovoltaic metric."""


def _finite_xy(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape or x.ndim != 1:
        raise CalculationError("电压和电流数据必须是一维且长度相同。")
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if x.size < 2:
        raise CalculationError("有效数据点少于 2 个。")
    return x, y


def interpolate_y_at_zero(x: np.ndarray, y: np.ndarray) -> float:
    """Linearly interpolate y where x=0, choosing the nearest sign crossing."""
    x, y = _finite_xy(x, y)
    exact = np.flatnonzero(np.isclose(x, 0.0, rtol=0.0, atol=1e-15))
    if exact.size:
        return float(np.mean(y[exact]))

    candidates: list[tuple[float, int]] = []
    for index in range(x.size - 1):
        if x[index] * x[index + 1] < 0:
            candidates.append((abs(x[index]) + abs(x[index + 1]), index))
    if not candidates:
        raise CalculationError("数据没有跨越零点，无法进行线性插值。")

    _, index = min(candidates)
    x0, x1 = x[index], x[index + 1]
    y0, y1 = y[index], y[index + 1]
    return float(y0 + (0.0 - x0) * (y1 - y0) / (x1 - x0))


def calculate_metrics(
    voltage_v: np.ndarray,
    current_a: np.ndarray,
    area_cm2: float,
    irradiance_mw_cm2: float,
) -> Metrics:
    """Calculate Voc, Jsc, FF and PCE from one forward or reverse scan."""
    if area_cm2 <= 0:
        raise CalculationError("器件面积必须大于 0。")
    if irradiance_mw_cm2 <= 0:
        raise CalculationError("光功率密度必须大于 0。")

    voltage, current = _finite_xy(voltage_v, current_a)
    density = current * 1000.0 / area_cm2
    jsc_signed = interpolate_y_at_zero(voltage, density)
    voc_signed = interpolate_y_at_zero(density, voltage)

    lower, upper = sorted((0.0, voc_signed))
    in_power_quadrant = (voltage >= lower) & (voltage <= upper)
    candidate_v = np.concatenate((voltage[in_power_quadrant], [0.0, voc_signed]))
    candidate_j = np.concatenate((density[in_power_quadrant], [jsc_signed, 0.0]))
    pmax = float(np.max(np.abs(candidate_v * candidate_j)))

    voc = abs(voc_signed)
    jsc = abs(jsc_signed)
    denominator = voc * jsc
    if math.isclose(denominator, 0.0, abs_tol=1e-15):
        raise CalculationError("Voc 或 Jsc 为零，无法计算填充因子。")
    ff = pmax / denominator * 100.0
    pce = pmax / irradiance_mw_cm2 * 100.0
    return Metrics(
        pce_percent=pce,
        voc_v=voc,
        jsc_ma_cm2=jsc,
        ff_percent=ff,
        pmax_mw_cm2=pmax,
    )


def average_metrics(
    forward: Metrics,
    reverse: Metrics,
    irradiance_mw_cm2: float,
) -> Metrics:
    """Average Voc/Jsc/FF first, then calculate PCE as requested."""
    voc = (forward.voc_v + reverse.voc_v) / 2.0
    jsc = (forward.jsc_ma_cm2 + reverse.jsc_ma_cm2) / 2.0
    ff = (forward.ff_percent + reverse.ff_percent) / 2.0
    pmax = abs(voc * jsc) * ff / 100.0
    pce = pmax / irradiance_mw_cm2 * 100.0
    return Metrics(
        pce_percent=pce,
        voc_v=voc,
        jsc_ma_cm2=jsc,
        ff_percent=ff,
        pmax_mw_cm2=pmax,
    )
