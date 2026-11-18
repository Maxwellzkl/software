import threading
import re

import numpy as np
import pytest

import pce_app.instrument as instrument_module
from pce_app.instrument import B2902BSession, InstrumentError
from pce_app.models import ChannelDut, SweepSettings


class FakeInstrument:
    def __init__(self) -> None:
        self.commands = []
        self.timeout = 0
        self.read_termination = None
        self.write_termination = None
        self.status_bytes = [0x20]
        self.stb_reads = 0
        self.stb_error: Exception | None = None
        self.list_points: dict[tuple[int, str], int] = {}
        self.reported_list_points: int | None = None
        self.fetch_count = 3
        self.fetch_voltage_values = None
        self.fetch_current_values = None

    def write(self, command: str) -> None:
        self.commands.append(command)
        match = re.fullmatch(
            r":SOUR(\d+):LIST:(VOLT|CURR)(:APP)? (.+)", command
        )
        if match:
            key = (int(match.group(1)), match.group(2))
            count = len(match.group(4).split(","))
            self.list_points[key] = (
                self.list_points.get(key, 0) + count if match.group(3) else count
            )

    def query(self, command: str) -> str:
        self.commands.append(command)
        if command == "*IDN?":
            return "Keysight Technologies,B2902B,MY00000000,1.0\n"
        if command == "*ESR?":
            return "1\n"
        if command == "*OPC?":
            return "1\n"
        match = re.fullmatch(r":SOUR(\d+):LIST:(VOLT|CURR):POIN\?", command)
        if match:
            if self.reported_list_points is not None:
                return f"{self.reported_list_points}\n"
            return f"{self.list_points.get((int(match.group(1)), match.group(2)), 0)}\n"
        return "0\n"

    def read_stb(self) -> int:
        self.stb_reads += 1
        if self.stb_error is not None:
            raise self.stb_error
        if len(self.status_bytes) > 1:
            return self.status_bytes.pop(0)
        return self.status_bytes[0]

    def query_ascii_values(self, command: str):
        self.commands.append(command)
        if "VOLT" in command and self.fetch_voltage_values is not None:
            return self.fetch_voltage_values
        if "CURR" in command and self.fetch_current_values is not None:
            return self.fetch_current_values
        if self.fetch_count != 3:
            if "VOLT" in command:
                return np.linspace(-0.2, 1.2, self.fetch_count)
            return np.linspace(-0.001, 0.0001, self.fetch_count)
        if "VOLT" in command:
            return [-0.2, 0.5, 1.2]
        return [-0.001, -0.0005, 0.0001]

    def close(self) -> None:
        return None


class FakeManager:
    def __init__(self, fake: FakeInstrument) -> None:
        self.fake = fake

    def open_resource(self, address: str) -> FakeInstrument:
        return self.fake

    def close(self) -> None:
        return None


def test_dual_channel_scpi_sequence(monkeypatch) -> None:
    fake = FakeInstrument()
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    settings = SweepSettings(
        start=-0.2,
        stop=1.2,
        count=3,
        scan_plan="forward",
        source_range_auto=False,
        source_range=2.0,
        current_range_mode="LIMITED",
        current_range=1e-6,
        measure_speed="NORMAL",
    )
    duts = [
        ChannelDut(1, "A", "1", 0.04, "light"),
        ChannelDut(2, "B", "2", 0.05, "light"),
    ]
    with B2902BSession("USB0::FAKE::INSTR") as session:
        curves = session.acquire_pass(
            settings, duts, "forward", threading.Event()
        )

    assert set(curves) == {1, 2}
    assert np.allclose(curves[1].voltage_v, [-0.2, 0.5, 1.2])
    assert ":SOUR1:LIST:VOLT -0.2,0.5,1.2" in fake.commands
    assert ":SOUR2:LIST:VOLT -0.2,0.5,1.2" in fake.commands
    assert ":TRIG1:COUN 3" in fake.commands
    assert ":TRIG2:COUN 3" in fake.commands
    assert "*CLS" in fake.commands
    assert "*ESE 1" in fake.commands
    assert ":SOUR1:VOLT:RANG:AUTO OFF" in fake.commands
    assert ":SOUR1:VOLT:RANG 2" in fake.commands
    assert ":SENS1:CURR:RANG:AUTO ON" in fake.commands
    assert ":SENS1:CURR:RANG:AUTO:LLIM 1e-06" in fake.commands
    assert ":SENS1:VOLT:RANG:AUTO OFF" in fake.commands
    assert ":SENS1:VOLT:RANG 2" in fake.commands
    assert ":SENS1:CURR:NPLC:AUTO OFF" in fake.commands
    assert ":SENS1:CURR:NPLC 1" in fake.commands
    assert ":TRIG1:SOUR AINT" in fake.commands
    assert not any(command.startswith(":TRIG1:TIM ") for command in fake.commands)
    assert ":INIT (@1,2)" in fake.commands
    assert ":OUTP1 OFF" in fake.commands
    assert ":OUTP2 OFF" in fake.commands


def test_auto_measure_speed_enables_instrument_nplc_auto(monkeypatch) -> None:
    fake = FakeInstrument()
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    settings = SweepSettings(
        start=-0.2,
        stop=1.2,
        count=3,
        scan_plan="forward",
        measure_speed="AUTO",
    )
    dut = ChannelDut(1, "A", "1", 0.04, "light")

    with B2902BSession("USB0::FAKE::INSTR") as session:
        session.acquire_pass(settings, [dut], "forward", threading.Event())

    assert ":SENS1:VOLT:NPLC:AUTO ON" in fake.commands
    assert ":SENS1:CURR:NPLC:AUTO ON" in fake.commands
    assert not any(command.startswith(":SENS1:CURR:NPLC ") for command in fake.commands)


@pytest.mark.parametrize(
    ("settings", "expected_period"),
    [
        (
            SweepSettings(
                start=-0.2,
                stop=1.2,
                count=3,
                trigger_mode="TIMER",
                trigger_period_s=0.25,
            ),
            0.25,
        ),
        (
            SweepSettings(
                start=-0.2,
                stop=1.2,
                count=3,
                trigger_mode="AUTO",
                minimum_auto_trigger_period_enabled=True,
                trigger_period_s=0.1,
            ),
            0.1,
        ),
    ],
)
def test_timer_and_auto_minimum_period_trigger_scpi(
    monkeypatch, settings, expected_period
) -> None:
    fake = FakeInstrument()
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    dut = ChannelDut(1, "A", "1", 0.04, "light")

    with B2902BSession("USB0::FAKE::INSTR") as session:
        session.acquire_pass(settings, [dut], "forward", threading.Event())

    assert ":TRIG1:SOUR TIM" in fake.commands
    assert f":TRIG1:TIM {expected_period:.12g}" in fake.commands
    assert ":TRIG1:SOUR AINT" not in fake.commands


def test_auto_minimum_period_keeps_aint_when_auto_is_already_slower(
    monkeypatch,
) -> None:
    fake = FakeInstrument()
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    settings = SweepSettings(
        start=-0.2,
        stop=1.2,
        count=3,
        trigger_mode="AUTO",
        minimum_auto_trigger_period_enabled=True,
        trigger_period_s=0.01,
    )
    dut = ChannelDut(1, "A", "1", 0.04, "light")

    with B2902BSession("USB0::FAKE::INSTR") as session:
        session.acquire_pass(settings, [dut], "forward", threading.Event())

    assert ":TRIG1:SOUR AINT" in fake.commands
    assert not any(command.startswith(":TRIG1:TIM ") for command in fake.commands)


def test_long_timer_period_is_included_in_scan_timeout(monkeypatch) -> None:
    fake = FakeInstrument()
    fake.fetch_count = 20
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    settings = SweepSettings(
        start=-0.2,
        stop=1.2,
        count=20,
        trigger_mode="TIMER",
        trigger_period_s=1.0,
    )
    dut = ChannelDut(1, "A", "1", 0.04, "light")
    captured = {}

    with B2902BSession("USB0::FAKE::INSTR") as session:
        session._wait_for_complete = (  # type: ignore[method-assign]
            lambda _cancel_event, timeout_s: captured.update(timeout_s=timeout_s)
        )
        session.acquire_pass(settings, [dut], "forward", threading.Event())

    assert captured["timeout_s"] >= 20.0 + 10.0


def test_trigger_period_validation() -> None:
    with pytest.raises(ValueError, match="20 μs"):
        SweepSettings(trigger_period_s=1e-6).validate()
    with pytest.raises(ValueError, match="Trigger 模式"):
        SweepSettings(trigger_mode="BUS").validate()  # type: ignore[arg-type]


def test_long_scan_wait_uses_serial_poll_instead_of_repeated_esr_queries(
    monkeypatch,
) -> None:
    fake = FakeInstrument()
    fake.status_bytes = [0, 0, 0x20]
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )

    with B2902BSession("USB0::FAKE::INSTR") as session:
        session._wait_for_complete(threading.Event(), timeout_s=5.0)

    assert fake.stb_reads == 3
    assert fake.commands.count("*ESR?") == 1
    assert "*OPC" in fake.commands


def test_wait_can_be_cancelled_without_queuing_a_scpi_query(monkeypatch) -> None:
    fake = FakeInstrument()
    fake.status_bytes = [0]
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    cancelled = threading.Event()
    cancelled.set()

    with B2902BSession("USB0::FAKE::INSTR") as session:
        with pytest.raises(InterruptedError):
            session._wait_for_complete(cancelled, timeout_s=5.0)

    assert fake.stb_reads == 0
    assert "*ESR?" not in fake.commands


def test_wait_falls_back_to_long_timeout_opc_query(monkeypatch) -> None:
    fake = FakeInstrument()
    fake.timeout = 5000
    fake.stb_error = NotImplementedError("serial poll unavailable")
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )

    with B2902BSession("USB0::FAKE::INSTR") as session:
        session._wait_for_complete(threading.Event(), timeout_s=30.0)

    assert fake.stb_reads == 1
    assert "*OPC?" in fake.commands
    assert fake.timeout == 5000


def test_801_point_list_is_written_in_chunks_and_verified(monkeypatch) -> None:
    fake = FakeInstrument()
    fake.fetch_count = 801
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    settings = SweepSettings(
        start=-0.2,
        stop=1.2,
        count=801,
        scan_plan="forward",
        measure_speed="NORMAL",
    )
    dut = ChannelDut(1, "A", "1", 0.04, "light")

    with B2902BSession("USB0::FAKE::INSTR") as session:
        curves = session.acquire_pass(settings, [dut], "forward", threading.Event())

    list_commands = [
        command for command in fake.commands if command.startswith(":SOUR1:LIST:VOLT")
    ]
    write_commands = [command for command in list_commands if not command.endswith("POIN?")]
    assert len(write_commands) == 9
    assert write_commands[0].startswith(":SOUR1:LIST:VOLT ")
    assert all(
        command.startswith(":SOUR1:LIST:VOLT:APP ")
        for command in write_commands[1:]
    )
    assert max(map(len, write_commands)) < 2000
    assert ":SOUR1:LIST:VOLT:POIN?" in fake.commands
    assert fake.list_points[(1, "VOLT")] == 801
    assert curves[1].voltage_v.size == 801
    assert curves[1].current_a.size == 801


def test_list_point_mismatch_stops_before_scan(monkeypatch) -> None:
    fake = FakeInstrument()
    fake.reported_list_points = 1
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    settings = SweepSettings(start=-0.2, stop=1.2, count=801, scan_plan="forward")
    dut = ChannelDut(1, "A", "1", 0.04, "light")

    with B2902BSession("USB0::FAKE::INSTR") as session:
        with pytest.raises(InstrumentError, match="扫描列表仅装载 1 个点"):
            session.acquire_pass(settings, [dut], "forward", threading.Event())

    assert ":INIT (@1)" not in fake.commands


def test_double_sweep_uses_one_continuous_list_and_shares_turnaround(
    monkeypatch,
) -> None:
    fake = FakeInstrument()
    fake.fetch_voltage_values = np.asarray([-2.0, 0.0, 2.0, 0.0, -2.0])
    fake.fetch_current_values = np.asarray([-2e-4, -1e-4, 1e-5, -9e-5, -1.9e-4])
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    settings = SweepSettings(start=-2.0, stop=2.0, count=3, scan_plan="both")
    dut = ChannelDut(1, "A", "1", 0.04, "light")

    with B2902BSession("USB0::FAKE::INSTR") as session:
        curves = session.acquire_double(settings, [dut], threading.Event())

    assert fake.list_points[(1, "VOLT")] == 5
    assert ":SOUR1:LIST:VOLT -2,0,2,0,-2" in fake.commands
    assert ":TRIG1:COUN 5" in fake.commands
    assert fake.commands.count(":INIT (@1)") == 1
    assert np.allclose(curves[1]["forward"].voltage_v, [-2.0, 0.0, 2.0])
    assert np.allclose(curves[1]["reverse"].voltage_v, [2.0, 0.0, -2.0])
    assert curves[1]["forward"].current_a[-1] == curves[1]["reverse"].current_a[0]
    assert curves[1]["reverse"].elapsed_s[0] == 0.0


def test_double_sweep_rejects_combined_list_over_instrument_limit(
    monkeypatch,
) -> None:
    fake = FakeInstrument()
    monkeypatch.setattr(
        instrument_module.visa, "ResourceManager", lambda: FakeManager(fake)
    )
    settings = SweepSettings(start=-2.0, stop=2.0, count=50001, scan_plan="both")
    dut = ChannelDut(1, "A", "1", 0.04, "light")

    with B2902BSession("USB0::FAKE::INSTR") as session:
        with pytest.raises(InstrumentError, match="100000 点上限"):
            session.acquire_double(settings, [dut], threading.Event())

    assert ":INIT (@1)" not in fake.commands
