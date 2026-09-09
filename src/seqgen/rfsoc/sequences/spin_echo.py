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


class SpinEchoSequence(RFSocSequence):
    """RFSoC Spin Echo sequence builder: pi/2 - tau/2 - pi - tau/2 - pi/2."""

    sequence_name = "Spin Echo"
    ch_names = ["laser", "camera"]

    def extra_log_info(self):
        return (
            f"\nFrequency: {self.frequency / 1e9:.4f} GHz"
            + f"\nPi duration: {self.pi_dur} ns"
            + f"\nPi/2 duration: {self.pi_2_dur} ns"
            + f"\nNumber of tau points: {len(self.time_list)}"
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
        pi_dur: float = 0,
        pi_2_dur: float = 0,
        laser_dur: float = 0,
        laser_delay: float = 0,
        laser_to_rf_delay: float = 0,
        rf_delay: float = 0,
        **kwargs,
    ):
        seqgen: RFSOCAdapter = self.seqgen

        if sweep_x is None:
            logger.error("sweep_x (total free evolution times) must be provided for the Spin Echo sequence.")
            return

        self.frequency = frequency
        maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        laser_dur = _even_ns(laser_dur * 1e9)
        dark_wait = _even_ns((laser_to_rf_delay + rf_delay) * 1e9)
        self.pi_dur = _even_ns(pi_dur * 1e9)
        self.pi_2_dur = _even_ns(pi_2_dur * 1e9)

        # split tau evenly between the two evolution periods, same
        # convention as the PulseBlaster spin echo sequence
        tau_ns = [t * 1e9 for t in np.asarray(sweep_x).tolist()]
        self.time_list = [_even_ns(t) for t in tau_ns]
        tau1_list = [_even_ns(np.ceil(t / 2)) for t in tau_ns]
        tau2_list = [_even_ns(np.floor(t / 2)) for t in tau_ns]

        min_tau = min(self.time_list)
        loop_time = laser_dur + dark_wait + 2 * self.pi_2_dur + self.pi_dur + min_tau
        self.num_loops = int(np.ceil(self.exposure_time / loop_time)) + 1
        self.num_readout_loops = int(np.ceil(self.camera_trig_time / loop_time)) + 1

        self.log_sequence_info()

        seqgen.ub.add_instruction(LASER, frequency, 0, 0, self.exposure_time, resync=1)

        b_ref = bool(ref_mode)

        for tau1, tau2 in zip(tau1_list, tau2_list):
            sig_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
            sig_body = [
                (CAMERA, frequency, PHASE_X, 0, dark_wait, False),
                (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, True),
                (CAMERA, frequency, PHASE_X, 0, tau1, False),
                (CAMERA, frequency, PHASE_X, maxAmp, self.pi_dur, False),
                (CAMERA, frequency, PHASE_X, 0, tau2, False),
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
                        (CAMERA, holdFreq, PHASE_X, 0, tau1, False),
                        (CAMERA, holdFreq, PHASE_X, 0, self.pi_dur, False),
                        (CAMERA, holdFreq, PHASE_X, 0, tau2, False),
                        (CAMERA, holdFreq, PHASE_X, 0, self.pi_2_dur, False),
                    ]
                elif ref_mode == "3π/2 at end":
                    ref_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
                    ref_body = [
                        (CAMERA, frequency, PHASE_X, 0, dark_wait, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, True),
                        (CAMERA, frequency, PHASE_X, 0, tau1, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, self.pi_dur, False),
                        (CAMERA, frequency, PHASE_X, 0, tau2, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, 3 * self.pi_2_dur, False),
                    ]
                else:  # "-π/2 at end" (default alternative)
                    ref_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
                    ref_body = [
                        (CAMERA, frequency, PHASE_X, 0, dark_wait, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, True),
                        (CAMERA, frequency, PHASE_X, 0, tau1, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, self.pi_dur, False),
                        (CAMERA, frequency, PHASE_X, 0, tau2, False),
                        (CAMERA, frequency, PHASE_NEG_X, maxAmp, self.pi_2_dur, False),
                    ]
                _emit_cycle(seqgen, ref_start, ref_body, self.num_loops)
                _emit_cycle(seqgen, *_strip_camera_ttl(ref_start, ref_body), self.num_readout_loops)

        self.finish()
        return
