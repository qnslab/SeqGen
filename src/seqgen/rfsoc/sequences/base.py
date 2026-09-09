from __future__ import annotations

from typing import Any
from loguru import logger

from seqgen.rfsoc.rfsoc import RFSOCAdapter


MHz = 1e6
GHz = 1e9
us = 1e-6
ns = 1e-9

# MicroBlaster TTL flag bits (bit0 = laser, bit1 = camera/measurement-window
# marker). The RF itself is synthesized directly by the DDS core and gated
# on/off via the amplitude field of each instruction, rather than a TTL bit.
LASER = 0b01
CAMERA = 0b10
BOTH = LASER | CAMERA

# phase (in degrees) for each pulse axis, leveraging the MicroBlaster's
# native per-instruction phase field instead of separate rf_x/rf_y/rf_-x/
# rf_-y TTL channels like the PulseBlaster sequences use.
PHASE_X = 0
PHASE_Y = 90
PHASE_NEG_X = 180
PHASE_NEG_Y = 270


def even_ns(value: float, minimum: int = 4) -> int:
    """Round to the nearest even integer number of ns (MicroBlaster delay
    fields must be an integer multiple of 2), with a floor of ``minimum``.
    """
    return max(int(round(value / 2.0)) * 2, minimum)


def emit_cycle(seqgen, start, body, loops: int):
    """Emit one repeated program cycle using the MicroBlaster's hardware
    LOOP/END_LOOP opcodes: ``start`` is re-executed at the top of every
    iteration, each entry of ``body[:-1]`` runs once per iteration, and
    ``body[-1]`` is the END_LOOP instruction that either jumps back to
    ``start`` or falls through once ``loops`` iterations have completed.

    ``start`` and each entry of ``body`` are ``(ttl, freq, phase, amp,
    delay, resync)`` tuples.
    """
    ttl, freq, phase, amp, delay, resync = start
    seqgen.ub.start_loop(ttl, freq, phase, amp, delay, loops=loops, resync=resync)
    for ttl, freq, phase, amp, delay, resync in body[:-1]:
        seqgen.ub.add_instruction(ttl, freq, phase, amp, delay, resync=resync)
    ttl, freq, phase, amp, delay, resync = body[-1]
    seqgen.ub.end_loop(ttl, freq, phase, amp, delay, resync=resync)


def strip_camera_ttl(start, body):
    """Return ``(start, body)`` with the ``CAMERA`` TTL bit cleared from
    every instruction's ttl field.

    Used for the readout-loop repeats of a sequence cycle (the pass that
    pads out ``camera_trig_time``): the camera trigger must not be
    re-asserted while the camera is still reading out the previous frame,
    so this strips the CAMERA bit while leaving the rest of the pulse
    pattern (laser pulse, RF timing/amplitude/phase) unchanged.
    """
    def _clear(entry):
        ttl, freq, phase, amp, delay, resync = entry
        return (ttl & ~CAMERA, freq, phase, amp, delay, resync)

    return _clear(start), [_clear(entry) for entry in body]


class RFSocSequence:
    """Base class for RFSoC MicroBlaster sequence builders.

    Holds the ``__init__``/metadata plumbing and the setup/teardown steps
    common to every sequence (unit conversion helpers, clearing any
    previously loaded program, enabling the sinc filter for GHz-range
    output, computing the RF amplitude/hold-frequency values, and closing
    out the program), so that individual sequence files only need to
    describe the pulse pattern itself.
    """

    sequence_name = "Sequence"
    ch_names: list[str] = ["laser", "camera"]

    def __init__(self, seqgen, *args, **kwargs):
        self.seqgen = seqgen
        self.sequence_params = seqgen.sequence_params
        self.ch_defs = seqgen.ch_defs

    def extra_log_info(self) -> str:
        """Override in subclasses to append sequence-specific details
        (frequency, pulse durations, number of sweep points, loop counts,
        etc.) to the standard :meth:`log_sequence_info` output.
        """
        return ""

    def log_sequence_info(self):
        logger.info(
            f"Loaded {self.sequence_name} sequence \n"
            + f"Channel names: {self.ch_names}"
            + f"\nCamera on time: {self.exposure_time / 1e9:.3e} s"
            + f"\nCamera readout time: {self.camera_trig_time / 1e9:.3e} s"
            + f"\nReference mode: {self.ref_mode}"
            + self.extra_log_info()
        )

    def prepare(self, exposure_time: float, camera_trig_time: float, ref_mode: str, rf_amplitude: int | None):
        """Common sequence setup.

        Converts the exposure/camera-trigger times to ns, clears any
        previously loaded MicroBlaster program (the priming halt
        instruction added in ``RFSOCAdapter.open()``, or a previously
        loaded sequence -- without this the new instructions would be
        appended after an existing STOP instruction at index 0, which the
        MicroBlaster never advances past), enables the sinc filter (to
        minimise DAC rolloff at the multi-GHz frequencies these sequences
        synthesize), and computes the RF amplitude and hold-frequency
        values. Returns ``(maxAmp, holdFreq)``.
        """
        seqgen: RFSOCAdapter = self.seqgen
        self.ref_mode = ref_mode
        self.rf_amplitude = rf_amplitude
        self.exposure_time = int(round(exposure_time * 1e9))
        self.camera_trig_time = int(round(camera_trig_time * 1e9))

        seqgen.ub.clean_program()
        seqgen.rfbuilder.sinc_filters = 1

        maxAmp = seqgen.ub.get_max_amp()
        if rf_amplitude is not None:
            maxAmp = maxAmp * rf_amplitude // 100
        else:
            maxAmp = 0
        # setting frequency to this value will cause it to hold the
        # frequency from the previous instruction
        holdFreq = seqgen.ub.get_max_freq()
        return maxAmp, holdFreq

    def finish(self):
        """Close out the program: append the final STOP instruction and
        push the built program (plus TTL/block wiring) to hardware.
        """
        seqgen: RFSOCAdapter = self.seqgen
        seqgen.ub.end_program(0, 0, 0, 0, 4)
        seqgen.rfbuilder.update()
