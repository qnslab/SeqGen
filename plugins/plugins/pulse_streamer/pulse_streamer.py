from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from seqgen.pulse_kernel import ChannelType

try:
    from pulsestreamer import OutputState, PulseStreamer
except Exception:  # pragma: no cover - optional dependency
    PulseStreamer = None
    OutputState = None

try:
    from loguru import logger
except Exception:  # pragma: no cover - optional dependency
    logger = logging.getLogger(__name__)


class PulseStreamerAdapter:
    """SeqGen adapter for the Swabian Instruments Pulse Streamer 8/2.

    The Pulse Streamer 8/2 exposes 8 synchronous digital outputs (0/1 V TTL,
    1 ns resolution) and 2 analog outputs (-1.0 to 1.0 V, 8 ns resolution).
    This adapter accepts the same sequence-building API as the PulseBlaster
    and Keysight AWG adapters, so existing ``camera_sequences`` builders work
    unmodified. Channels are declared as either digital or analog via
    ``ch_types`` (see ``seqgen.ChannelType``); analog channel levels are
    carried through the ``PulseKernel`` -> instruction -> hardware pipeline
    using each instruction's ``levels`` dict.

    If no ``ip_address`` is given (or the ``pulsestreamer`` client library is
    not installed) the adapter runs in offline mode: sequences are still
    built and compiled into ``digital_patterns``/``analog_patterns`` for
    inspection, plotting, or export, but nothing is streamed to hardware.
    """

    connected: bool = False
    ch_defs: dict[str, int]
    sequence_params: dict[str, float]

    def __init__(
        self,
        ch_defs: dict[str, int],
        sequence_params: dict[str, float] | None = None,
        ip_address: str | None = None,
        ch_types: dict[str, "ChannelType | str"] | None = None,
        n_runs: int = 1,
    ):
        # ch_defs maps channel name -> hardware channel index:
        #   digital channels: 0-7, analog channels: 0-1
        self.ch_defs = ch_defs or {}
        self.sequence_params = sequence_params or {}
        self.ip_address = ip_address
        self.n_runs = n_runs
        self.ch_types = {
            ch: ChannelType.coerce(ch_types[ch]) if ch_types and ch in ch_types else ChannelType.DIGITAL
            for ch in self.ch_defs
        }
        # PS 8/2 digital resolution is 1 ns (2 ns minimum pulse width).
        self.shortest_dur = 1
        self.connected = False
        self.running = False
        self._ps = None
        self._program: list[dict[str, Any]] = []
        self._loop_stack: list[dict[str, Any]] = []
        self.sequence = None
        self.digital_patterns: dict[str, list[tuple[int, int]]] = {}
        self.analog_patterns: dict[str, list[tuple[int, float]]] = {}

    def open(self) -> tuple[bool, str]:
        if self.ip_address is None:
            self.connected = True
            return True, "Pulse Streamer adapter ready in offline mode"

        if PulseStreamer is None:
            return False, "pulsestreamer package not available: install device adapter dependencies"

        try:
            self._ps = PulseStreamer(self.ip_address)
            self.connected = True
            logger.info("Connected to Pulse Streamer at {}", self.ip_address)
            return True, f"Connected to Pulse Streamer at {self.ip_address}"
        except Exception:
            logger.exception("Error connecting to Pulse Streamer")
            self.connected = False
            self._ps = None
            return False, "Error connecting to Pulse Streamer"

    def close(self):
        self.stop()
        self._ps = None
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def start(self):
        if self._ps is not None and self.sequence is not None:
            final_state = OutputState.ZERO() if OutputState is not None else None
            self._ps.stream(self.sequence, self.n_runs, final_state)
        self.running = True

    def reset(self):
        self._program = []
        self._loop_stack = []
        self.sequence = None
        self.digital_patterns = {}
        self.analog_patterns = {}
        self.running = False

    def stop(self):
        if self._ps is not None:
            try:
                self._ps.reset()
            except Exception:
                logger.exception("Error resetting Pulse Streamer")
        self.running = False

    def is_finished(self):
        if self._ps is not None:
            try:
                return bool(self._ps.hasFinished())
            except Exception:
                return True
        return not self.running

    def get_status(self):
        return {
            "connected": self.connected,
            "running": self.running,
            "ip_address": self.ip_address,
            "instructions": len(self._program),
        }

    def get_available_sequences(self):
        from ..pulseblaster.camera_sequences.cw_esr import seq_cw_esr
        from ..pulseblaster.camera_sequences.p_esr import seq_p_esr
        from ..pulseblaster.camera_sequences.rabi import seq_rabi
        from ..pulseblaster.camera_sequences.ramsey import seq_ramsey
        from ..pulseblaster.camera_sequences.spin_echo import seq_spin_echo
        from ..pulseblaster.camera_sequences.t1 import seq_t1

        return {
            "MockSGAndorCWESR": seq_cw_esr,
            "SGAndorCWESR": seq_cw_esr,
            "SGAndorPESR": seq_p_esr,
            "SGAndorRabi": seq_rabi,
            "SGAndorT1": seq_t1,
            "SGAndorRamsey": seq_ramsey,
            "SGAndorSpinEcho": seq_spin_echo,
        }

    def load_seq(self, seq_name, **seq_kwargs):
        logger.info("Loading {} sequence", seq_name)
        sequences = self.get_available_sequences()
        sequences[seq_name](self, self.sequence_params, **seq_kwargs)
        logger.info("Loaded {} sequence", seq_name)

    def start_programming(self):
        self.reset()

    def stop_programming(self):
        self.sequence = self.build_sequence()

    def _normalize_instruction(
        self,
        active_chs,
        dur=0,
        delay=None,
        loop=None,
        num=0,
        inst=None,
        const_chs=(),
        levels=None,
        **kwargs,
    ):
        return {
            "active_chs": list(active_chs) if active_chs else [],
            "dur": max(0, int(round(dur))),
            "const_chs": list(const_chs) if const_chs else [],
            "levels": dict(levels) if levels else {},
            "loop": loop,
            "num": int(num) if isinstance(num, (int, float)) else num,
            "loop_anchor": inst,
        }

    def add_instruction(
        self,
        active_chs,
        dur=0,
        delay=None,
        loop=None,
        num=0,
        inst=None,
        const_chs=(),
        levels=None,
        **kwargs,
    ):
        instruction = self._normalize_instruction(
            active_chs,
            dur=dur,
            delay=delay,
            loop=loop,
            num=num,
            inst=inst,
            const_chs=const_chs,
            levels=levels,
            **kwargs,
        )

        if loop == "start":
            self._loop_stack.append({"num": max(1, int(instruction["num"] or 1)), "buffer": []})
            return len(self._program)

        if loop == "end":
            if not self._loop_stack:
                logger.warning("Encountered loop end without a matching loop start")
                self._program.append(instruction)
                return len(self._program) - 1

            frame = self._loop_stack.pop()
            repeated = frame["buffer"] * frame["num"]
            if self._loop_stack:
                self._loop_stack[-1]["buffer"].extend(repeated)
            else:
                self._program.extend(repeated)
            return len(self._program) - 1 if self._program else None

        target = self._loop_stack[-1]["buffer"] if self._loop_stack else self._program
        target.append(instruction)
        return len(target) - 1

    def add_kernel(self, pulse_kernel, num_loop, const_chs=None, **kwargs):
        if const_chs is None:
            const_chs = []
        pulse_kernel.convert_to_instructions(const_chs=const_chs)
        for _ in range(int(num_loop)):
            for inst in pulse_kernel.insts:
                self.add_instruction(**inst)

    def end_sequence(self, dur):
        self.add_instruction([], dur=dur)

    def build_sequence(self):
        """Compile the materialized instruction program into digital/analog
        patterns and, if connected, a ``pulsestreamer.Sequence``.
        """
        if self._loop_stack:
            raise RuntimeError("Unclosed loop detected while building the Pulse Streamer sequence")

        digital_chs = [ch for ch, t in self.ch_types.items() if t == ChannelType.DIGITAL]
        analog_chs = [ch for ch, t in self.ch_types.items() if t == ChannelType.ANALOG]

        digital_patterns: dict[str, list[tuple[int, int]]] = {ch: [] for ch in digital_chs}
        analog_patterns: dict[str, list[tuple[int, float]]] = {ch: [] for ch in analog_chs}

        for instruction in self._program:
            dur = instruction["dur"]
            if dur <= 0:
                continue
            active = set(instruction["active_chs"]) | set(instruction["const_chs"])
            levels = instruction.get("levels", {})
            for ch in digital_chs:
                digital_patterns[ch].append((dur, 1 if ch in active else 0))
            for ch in analog_chs:
                analog_patterns[ch].append((dur, float(levels.get(ch, 0.0))))

        self.digital_patterns = digital_patterns
        self.analog_patterns = analog_patterns

        if PulseStreamer is None or self._ps is None:
            # Offline mode: patterns are available for inspection/export, but
            # nothing is compiled into a device-native Sequence object.
            return None

        sequence = self._ps.createSequence()
        for ch in digital_chs:
            sequence.setDigital(self.ch_defs[ch], digital_patterns[ch])
        for ch in analog_chs:
            sequence.setAnalog(self.ch_defs[ch], analog_patterns[ch])
        return sequence

    def save_patterns(self, save_path: str | Path):
        """Export the compiled digital/analog patterns to an ``.npz`` file
        for offline inspection, independent of hardware availability.
        """
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {}
        for ch, pattern in self.digital_patterns.items():
            arr = np.array(pattern, dtype=float) if pattern else np.zeros((0, 2))
            payload[f"digital__{ch}"] = arr
        for ch, pattern in self.analog_patterns.items():
            arr = np.array(pattern, dtype=float) if pattern else np.zeros((0, 2))
            payload[f"analog__{ch}"] = arr
        np.savez_compressed(save_path, **payload)
        return save_path
