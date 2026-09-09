from __future__ import annotations

from loguru import logger
import numpy as np

from seqgen.rfsoc.rfsoc import RFSOCAdapter
from seqgen.rfsoc.sequences.base import (
    RFSocSequence,
    LASER,
    CAMERA,
    BOTH,
    PHASE_X,
    PHASE_Y,
    PHASE_NEG_X,
    PHASE_NEG_Y,
    even_ns as _even_ns,
    emit_cycle as _emit_cycle,
    strip_camera_ttl as _strip_camera_ttl,
)


class SpinlockSequence(RFSocSequence):
    """RFSoC Spin-locking sequence builder: pi/2(x) - lock(y, tau) - pi/2(x)."""

    sequence_name = "Spinlock"
    ch_names = ["laser", "camera"]

    def extra_log_info(self):
        return (
            f"\nFrequency: {self.frequency / 1e9:.4f} GHz"
            + f"\nPi/2 duration: {self.pi_2_dur} ns"
            + f"\nNumber of lock durations: {len(self.time_list)}"
            + f"\nNumber of loops: {self.num_loops}"
            + f"\nNumber of readout loops: {self.num_readout_loops}"
        )

    def load(
        self,
        ref_mode: str = "no_rf",
        exposure_time: float = 0,
        camera_trig_time: float = 0,
        sweep_x: np.ndarray = None,
        frequency: float = 0,
        rf_amplitude: int | None = None,
        pi_2_dur: float = 0,
        laser_dur: float = 0,
        laser_delay: float = 0,
        laser_to_rf_delay: float = 0,
        rf_delay: float = 0,
        **kwargs,
    ):
        seqgen: RFSOCAdapter = self.seqgen

        if sweep_x is None:
            logger.error("sweep_x (spin-lock durations) must be provided for the Spinlock sequence.")
            return

        self.frequency = frequency
        maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        laser_dur = _even_ns(laser_dur * 1e9)
        dark_wait = _even_ns((laser_to_rf_delay + rf_delay) * 1e9)
        self.pi_2_dur = _even_ns(pi_2_dur * 1e9)

        self.time_list = [_even_ns(t * 1e9) for t in np.asarray(sweep_x).tolist()]

        min_tau = min(self.time_list)
        loop_time = laser_dur + dark_wait + 2 * self.pi_2_dur + min_tau
        self.num_loops = int(np.ceil(self.exposure_time / loop_time)) + 1
        self.num_readout_loops = int(np.ceil(self.camera_trig_time / loop_time)) + 1

        self.log_sequence_info()

        seqgen.ub.add_instruction(LASER, frequency, 0, 0, self.exposure_time, resync=1)

        b_ref = bool(ref_mode)

        for tau in self.time_list:
            # pi/2(x) - lock(y, tau) - pi/2(x)
            sig_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
            sig_body = [
                (CAMERA, frequency, PHASE_X, 0, dark_wait, False),
                (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, True),
                (CAMERA, frequency, PHASE_Y, maxAmp, tau, False),
                (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, False),
            ]
            _emit_cycle(seqgen, sig_start, sig_body, self.num_loops)
            _emit_cycle(seqgen, *_strip_camera_ttl(sig_start, sig_body), self.num_readout_loops)

            if b_ref:
                if ref_mode == "no_rf":
                    ref_start = (BOTH, holdFreq, PHASE_X, 0, laser_dur, False)
                    ref_body = [
                        (CAMERA, holdFreq, PHASE_X, 0, dark_wait, False),
                        (CAMERA, holdFreq, PHASE_X, 0, self.pi_2_dur, True),
                        (CAMERA, holdFreq, PHASE_Y, 0, tau, False),
                        (CAMERA, holdFreq, PHASE_X, 0, self.pi_2_dur, False),
                    ]
                else:
                    # mirrors the PulseBlaster Spinlock reference, which
                    # always applies the lock pulse followed by a 3*pi/2
                    # readout pulse regardless of the specific ref_mode.
                    ref_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
                    ref_body = [
                        (CAMERA, frequency, PHASE_X, 0, dark_wait, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, True),
                        (CAMERA, frequency, PHASE_Y, maxAmp, tau, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, 3 * self.pi_2_dur, False),
                    ]
                _emit_cycle(seqgen, ref_start, ref_body, self.num_loops)
                _emit_cycle(seqgen, *_strip_camera_ttl(ref_start, ref_body), self.num_readout_loops)

        self.finish()
        return
