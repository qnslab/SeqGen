from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging

import numpy as np

try:
    import pyvisa
except Exception:  # pragma: no cover - optional dependency
    pyvisa = None

try:
    from loguru import logger
except Exception:  # pragma: no cover - optional dependency
    logger = logging.getLogger(__name__)


@dataclass
class WaveformBundle:
    time_ns: np.ndarray
    waveforms: dict[str, np.ndarray]
    sample_rate: float


class Keysight9336A:
    """SeqGen adapter for Keysight 9336A-style AWG playback.

    The adapter accepts the same sequence-building API as the PulseBlaster
    example, but compiles instructions into per-channel marker waveforms.
    Hardware upload is intentionally lightweight: if a VISA resource name is
    provided, the class opens a connection, otherwise it operates offline and
    can still export or inspect generated waveforms.
    """

    connected: bool = False
    board_num: str
    ch_defs: dict[str, str]
    sequence_params: dict[str, float]

    def __init__(
        self,
        board_num: str = "0",
        ch_defs: dict[str, str] | None = None,
        sequence_params: dict[str, float] | None = None,
        resource_name: str | None = None,
        sample_rate: float = 1e9,
        channel_levels: dict[str, tuple[float, float]] | None = None,
    ):
        self.board_num = board_num
        self.ch_defs = ch_defs or {}
        self.sequence_params = sequence_params or {}
        self.resource_name = resource_name
        self.sample_rate = float(sample_rate)
        self.channel_levels = channel_levels or {}
        self.shortest_dur = 1
        self.connected = False
        self.running = False
        self._visa_resource = None
        self._program: list[dict[str, Any]] = []
        self._loop_stack: list[dict[str, Any]] = []
        self.waveform_bundle: WaveformBundle | None = None

    def open(self) -> tuple[bool, str]:
        if self.resource_name is None:
            self.connected = True
            return True, "Keysight AWG adapter ready in offline mode"

        if pyvisa is None:
            return False, "pyvisa not available: install device adapter dependencies"

        try:
            rm = pyvisa.ResourceManager()
            self._visa_resource = rm.open_resource(self.resource_name)
            self.connected = True
            logger.info("Opened Keysight AWG resource {}", self.resource_name)
            return True, f"Opened Keysight AWG resource {self.resource_name}"
        except Exception:
            logger.exception("Error opening Keysight AWG resource")
            self.connected = False
            self._visa_resource = None
            return False, "Error opening Keysight AWG resource"

    def close(self):
        if self._visa_resource is not None:
            try:
                self._visa_resource.close()
            except Exception:
                logger.exception("Error closing Keysight AWG resource")
        self._visa_resource = None
        self.connected = False
        self.running = False

    def is_connected(self) -> bool:
        return self.connected

    def start(self):
        self.running = True

    def reset(self):
        self._program = []
        self._loop_stack = []
        self.waveform_bundle = None
        self.running = False

    def stop(self):
        self.running = False

    def is_finished(self):
        return not self.running

    def get_status(self):
        return {
            "connected": self.connected,
            "running": self.running,
            "resource_name": self.resource_name,
            "sample_rate": self.sample_rate,
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
        self.waveform_bundle = self.build_waveforms()

    def _normalize_instruction(
        self,
        active_chs,
        dur=0,
        delay=None,
        loop=None,
        num=0,
        inst=None,
        const_chs=(),
        **kwargs,
    ):
        return {
            "active_chs": list(active_chs) if active_chs else [],
            "dur": max(0, int(round(dur))),
            "const_chs": list(const_chs) if const_chs else [],
            "loop": loop,
            "num": int(num) if isinstance(num, (int, float)) else num,
            "loop_anchor": inst,
        }

    def add_instruction(self, active_chs, dur=0, delay=None, loop=None, num=0, inst=None, const_chs=(), **kwargs):
        instruction = self._normalize_instruction(
            active_chs,
            dur=dur,
            delay=delay,
            loop=loop,
            num=num,
            inst=inst,
            const_chs=const_chs,
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

    def _instruction_to_sample_count(self, duration_ns: int) -> int:
        if duration_ns <= 0:
            return 0
        samples = int(round(duration_ns * self.sample_rate * 1e-9))
        return max(1, samples)

    def build_waveforms(self) -> WaveformBundle:
        if self._loop_stack:
            raise RuntimeError("Unclosed loop detected while building waveforms")

        channel_names = list(self.ch_defs.keys())
        if not self._program:
            empty = np.zeros(0, dtype=float)
            bundle = WaveformBundle(time_ns=empty, waveforms={ch: empty.copy() for ch in channel_names}, sample_rate=self.sample_rate)
            self.waveform_bundle = bundle
            return bundle

        segments: list[tuple[dict[str, Any], int]] = []
        total_samples = 0
        for instruction in self._program:
            sample_count = self._instruction_to_sample_count(instruction["dur"])
            if sample_count == 0:
                continue
            segments.append((instruction, sample_count))
            total_samples += sample_count

        time_ns = np.arange(total_samples, dtype=float) * (1e9 / self.sample_rate)
        waveforms = {ch: np.zeros(total_samples, dtype=float) for ch in channel_names}

        cursor = 0
        for instruction, sample_count in segments:
            active_channels = set(instruction["active_chs"])
            const_channels = set(instruction["const_chs"])
            segment_slice = slice(cursor, cursor + sample_count)
            for ch in channel_names:
                low, high = self.channel_levels.get(ch, (0.0, 1.0))
                if ch in active_channels or ch in const_channels:
                    waveforms[ch][segment_slice] = high
                else:
                    waveforms[ch][segment_slice] = low
            cursor += sample_count

        bundle = WaveformBundle(time_ns=time_ns, waveforms=waveforms, sample_rate=self.sample_rate)
        self.waveform_bundle = bundle
        return bundle

    def save_waveforms(self, save_path: str | Path):
        bundle = self.waveform_bundle or self.build_waveforms()
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        channel_names = np.array(list(bundle.waveforms.keys()), dtype=object)
        waveform_stack = np.vstack([bundle.waveforms[ch] for ch in channel_names]) if len(channel_names) > 0 else np.zeros((0, 0))
        np.savez_compressed(
            save_path,
            time_ns=bundle.time_ns,
            channel_names=channel_names,
            waveforms=waveform_stack,
            sample_rate=bundle.sample_rate,
        )
        return save_path
