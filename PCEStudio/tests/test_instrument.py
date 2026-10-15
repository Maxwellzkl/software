import threading

import numpy as np
import pytest

import pce_app.instrument as instrument_module
from pce_app.instrument import B2902BSession
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

    def write(self, command: str) -> None:
        self.commands.append(command)

    def query(self, command: str) -> str:
        self.commands.append(command)
        if command == "*IDN?":
            return "Keysight Technologies,B2902B,MY00000000,1.0\n"
        if command == "*ESR?":
            return "1\n"
        if command == "*OPC?":
            return "1\n"
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
    assert ":SENS1:CURR:NPLC:AUTO OFF" in fake.commands
    assert ":SENS1:CURR:NPLC 1" in fake.commands
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
