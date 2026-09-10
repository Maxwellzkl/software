import numpy as np
import pytest

from pce_app.calculations import CalculationError, average_metrics, calculate_metrics
from pce_app.models import Metrics


def test_linear_curve_metrics() -> None:
    voltage = np.array([-1.0, 0.0, 1.0, 2.0])
    density = -20.0 + 10.0 * voltage
    current = density * 0.04 / 1000.0
    result = calculate_metrics(voltage, current, area_cm2=0.04, irradiance_mw_cm2=100.0)
    assert result.voc_v == pytest.approx(2.0)
    assert result.jsc_ma_cm2 == pytest.approx(20.0)
    assert result.pmax_mw_cm2 == pytest.approx(10.0)
    assert result.ff_percent == pytest.approx(25.0)
    assert result.pce_percent == pytest.approx(10.0)


def test_interpolates_voc_and_jsc() -> None:
    voltage = np.array([-0.1, 0.1, 0.7, 0.9])
    density = np.array([-22.0, -18.0, -2.0, 2.0])
    current = density * 0.05 / 1000.0
    result = calculate_metrics(voltage, current, area_cm2=0.05, irradiance_mw_cm2=100.0)
    assert result.jsc_ma_cm2 == pytest.approx(20.0)
    assert result.voc_v == pytest.approx(0.8)


def test_average_then_recalculate_pce() -> None:
    forward = Metrics(10.0, 1.0, 20.0, 50.0, 10.0)
    reverse = Metrics(12.0, 1.1, 22.0, 55.0, 12.0)
    result = average_metrics(forward, reverse, irradiance_mw_cm2=100.0)
    assert result.voc_v == pytest.approx(1.05)
    assert result.jsc_ma_cm2 == pytest.approx(21.0)
    assert result.ff_percent == pytest.approx(52.5)
    assert result.pce_percent == pytest.approx(11.57625)


def test_missing_zero_crossing_is_reported() -> None:
    with pytest.raises(CalculationError):
        calculate_metrics(
            np.array([0.1, 0.2, 0.3]),
            np.array([-0.001, -0.0008, -0.0005]),
            area_cm2=0.04,
            irradiance_mw_cm2=100.0,
        )
