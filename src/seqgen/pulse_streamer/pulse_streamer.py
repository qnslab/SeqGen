from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from seqgen.pulse_kernel import ChannelType

from pulsestreamer import OutputState, PulseStreamer


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

    def __init__(
        self,
        ch_defs: dict[str, int],
        address: str | None = None,
        ch_types: dict[str, "ChannelType | str"] | None = None,
        n_runs: int = 1,
        device_id: str | None = None,
        *args,
        **kwargs
    ):
        # ch_defs maps channel name -> hardware channel index:
        #   digital channels: 0-7, analog channels: 0-1
        self.ch_defs = ch_defs or {}
        self.ip_address = address
        self.device_id = device_id
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
        self.loaded_sequence = None
        self.sequence = None
        self.digital_patterns: dict[str, list[tuple[int, int]]] = {}
        self.analog_patterns: dict[str, list[tuple[int, float]]] = {}

    def connect(self):
        self.open()

    def open(self) -> tuple[bool, str]:
        if self.ip_address is None:
            self.connected = True
            return True, "Pulse Streamer adapter ready in offline mode"

        if PulseStreamer is None:
            return False, "pulsestreamer package not available: install device adapter dependencies"

        try:
            self._ps = PulseStreamer(self.ip_address)
            self.connected = True
            logger.info("Connected to Pulse Streamer at %s", self.ip_address)
            return True, f"Connected to Pulse Streamer at {self.ip_address}"
        except Exception:
            logger.exception("Error connecting to Pulse Streamer")
            self.connected = False
            self._ps = None
            return False, "Error connecting to Pulse Streamer"

    def disconnect(self):
        self.close()

    def close(self):
        self.stop()
        self._ps = None
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def start_sequence(self):
        self.start()

    def start(self):
        if self._ps is not None and self.sequence is not None:
            final_state = OutputState.ZERO()
            self._ps.stream(self.sequence, self.n_runs, final_state)
        self.running = True

    def reset(self):
        self._program = []
        self._loop_stack = []
        self.loaded_sequence = None
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
        from seqgen.pulse_streamer.sequences.rabi import RabiSequence
        from seqgen.pulse_streamer.sequences.cw_odmr import ODMRSequence
        from seqgen.pulse_streamer.sequences.pulsed_odmr import PulsedODMRSequence

        return {
            "rabi": RabiSequence,
            "cw_odmr": ODMRSequence,
            "pulsed_odmr": PulsedODMRSequence,
        }

    def load_sequence(self, seq_name, **seq_kwargs):
        logger.info("Loading %s sequence", seq_name)
        sequences = self.get_available_sequences()
        sequence_spec = sequences[seq_name]
        if isinstance(sequence_spec, type):
            loaded_sequence = sequence_spec(self)
            result = loaded_sequence.load(**seq_kwargs)
            self.loaded_sequence = loaded_sequence
        else:
            self.loaded_sequence = None
            result = sequence_spec(self, **seq_kwargs)
        logger.info("Loaded %s sequence", seq_name)
        return result

    def get_loaded_sequence_info(self):
        if self.loaded_sequence is None:
            return {}
        if hasattr(self.loaded_sequence, "describe"):
            return self.loaded_sequence.describe()
        return {}

    def start_programming(self):
        self.reset()

    def stop_programming(self):
        self.sequence = self.build_sequence()

    def end_sequence(self, dur):
        # do nothing
        return

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

        if self._program:
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
        else:
            for ch in digital_chs:
                digital_patterns[ch] = list(self.digital_patterns.get(ch, []))
            for ch in analog_chs:
                analog_patterns[ch] = list(self.analog_patterns.get(ch, []))

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
