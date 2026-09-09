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


def _build_dd_body(frequency, dark_wait, pi_2_dur, pi_dur, tau_half, tau, phases, amp, ref_mode = None):
    """Build the (ttl, freq, phase, amp, delay, resync) body list common to
    the CPMG/XY dynamical-decoupling sequences: an initial pi/2(x) pulse,
    ``len(phases)`` pi pulses (one per entry of ``phases``, in degrees)
    separated by free evolution periods (``tau_half`` at each end, ``tau``
    in between), and a final pi/2(x) pulse.
    """
    if ref_mode == "no_rf":
        amp = 0
    body = [(CAMERA, frequency, PHASE_X, 0, dark_wait, False)]
    body.append((CAMERA, frequency, PHASE_X, amp, pi_2_dur, True))
    n = len(phases)
    for i, phase in enumerate(phases):
        gap = tau_half if (i == 0 or i == n - 1) else tau
        body.append((CAMERA, frequency, PHASE_X, 0, gap, False))
        body.append((CAMERA, frequency, phase, amp, pi_dur, False))
    body.append((CAMERA, frequency, PHASE_X, 0, tau_half, False))
    if ref_mode is not None:
        if ref_mode == "3π/2 at end":
            body.append((CAMERA, frequency, PHASE_X, amp, 3 * pi_2_dur, False))
        else:
            # default: "-π/2 at end"
            body.append((CAMERA, frequency, PHASE_NEG_X, amp, pi_2_dur, False))
    else:
        body.append((CAMERA, frequency, PHASE_X, amp, pi_2_dur, False))
    return body




class CPMGSequence(RFSocSequence):
    """RFSoC CPMG dynamical-decoupling sequence builder.

    pi/2(x) - tau/2 - [pi(y) - tau]*(n_pulses-1) - pi(y) - tau/2 - pi/2(x),
    sweeping the total free precession time ``sweep_x`` (the interpulse
    spacing is ``sweep_x / n_pulses``).
    """

    sequence_name = "CPMG"
    ch_names = ["laser", "camera"]

    def extra_log_info(self):
        return (
            f"\nFrequency: {self.frequency / 1e9:.4f} GHz"
            + f"\nNumber of pi pulses: {self.n_pulses}"
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
        n_pulses: int = 1,
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
            logger.error("sweep_x (total free precession times) must be provided for the CPMG sequence.")
            return
        if n_pulses < 1:
            logger.error("n_pulses must be at least 1 for the CPMG sequence.")
            return

        self.frequency = frequency
        self.n_pulses = int(n_pulses)
        maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        laser_dur = _even_ns(laser_dur * 1e9)
        dark_wait = _even_ns((laser_to_rf_delay + rf_delay) * 1e9)
        self.pi_dur = _even_ns(pi_dur * 1e9)
        self.pi_2_dur = _even_ns(pi_2_dur * 1e9)

        total_ns = [t * 1e9 for t in np.asarray(sweep_x).tolist()]
        self.time_list = [_even_ns(t) for t in total_ns]
        # per-pulse spacing and half-spacing at the two ends of the sequence
        tau_list = [_even_ns(t / self.n_pulses) for t in total_ns]
        tau_half_list = [_even_ns(t / (2 * self.n_pulses)) for t in total_ns]

        # all pi pulses on the y axis (standard CPMG refocusing phase)
        phases = [PHASE_X] * self.n_pulses

        min_tau_half = min(tau_half_list)
        min_tau = min(tau_list)
        loop_time = (
            laser_dur + dark_wait + 2 * self.pi_2_dur + self.n_pulses * self.pi_dur
            + 2 * min_tau_half + max(self.n_pulses - 1, 0) * min_tau
        )
        self.num_loops = int(np.ceil(self.exposure_time / loop_time)) + 1
        self.num_readout_loops = int(np.ceil(self.camera_trig_time / loop_time)) + 1

        self.log_sequence_info()

        seqgen.ub.add_instruction(LASER, frequency, 0, 0, self.exposure_time, resync=1)



        b_ref = bool(ref_mode)

        for tau, tau_half in zip(tau_list, tau_half_list):
            sig_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
            sig_body = _build_dd_body(frequency, dark_wait, self.pi_2_dur, self.pi_dur, tau_half, tau, phases, maxAmp)
            _emit_cycle(seqgen, sig_start, sig_body, self.num_loops)
            _emit_cycle(seqgen, *_strip_camera_ttl(sig_start, sig_body), self.num_readout_loops)

            if b_ref:
                ref_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
                ref_body = _build_dd_body(frequency, dark_wait, self.pi_2_dur, self.pi_dur, tau_half, tau, phases, maxAmp, ref_mode=ref_mode)
                _emit_cycle(seqgen, ref_start, ref_body, self.num_loops)
                _emit_cycle(seqgen, *_strip_camera_ttl(ref_start, ref_body), self.num_readout_loops)

        self.finish()
        return
