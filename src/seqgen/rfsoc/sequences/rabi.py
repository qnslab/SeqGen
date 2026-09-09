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


class RabiSequence(RFSocSequence):
    """RFSoC Rabi sequence builder: sweeps the RF pulse duration."""

    sequence_name = "Rabi"
    ch_names = ["laser", "camera"]

    def extra_log_info(self):
        return (
            f"\nFrequency: {self.frequency / 1e9:.4f} GHz"
            + f"\nNumber of RF pulse durations: {len(self.time_list)}"
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
        laser_dur: float = 0,
        laser_delay: float = 0,
        laser_to_rf_delay: float = 0,
        rf_delay: float = 0,
        **kwargs,
    ):
        seqgen: RFSOCAdapter = self.seqgen

        if sweep_x is None:
            logger.error("sweep_x (RF pulse durations) must be provided for the Rabi sequence.")
            return

        self.frequency = frequency
        maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        laser_dur = _even_ns(laser_dur * 1e9)
        dark_wait = _even_ns((laser_to_rf_delay + rf_delay) * 1e9)

        self.time_list = [_even_ns(t * 1e9) for t in np.asarray(sweep_x).tolist()]

        # conservative loop count computed from the shortest possible RF
        # pulse in the sweep (larger tau values just give a bit more
        # exposure than requested, never less)
        min_tau = min(self.time_list)
        loop_time = laser_dur + dark_wait + min_tau
        self.num_loops = int(np.ceil(self.exposure_time / loop_time)) + 1
        self.num_readout_loops = int(np.ceil(self.camera_trig_time / loop_time)) + 1

        self.log_sequence_info()

        # initial laser pulse to put the system in a known state
        seqgen.ub.add_instruction(LASER, self.frequency, 0, 0, self.exposure_time, resync=1)

        for tau in self.time_list:
            sig_start = (BOTH, self.frequency, PHASE_X, 0, laser_dur, False)
            sig_body = [
                (CAMERA, self.frequency, PHASE_X, 0, dark_wait, False),
                (CAMERA, self.frequency, PHASE_X, maxAmp, tau, True),
            ]
            _emit_cycle(seqgen, sig_start, sig_body, self.num_loops)
            _emit_cycle(seqgen, *_strip_camera_ttl(sig_start, sig_body), self.num_readout_loops)

            # if ref_mode == "no_rf":
            # default is no RF reference.
            ref_start = (BOTH, holdFreq, PHASE_X, 0, laser_dur, False)
            ref_body = [
                (CAMERA, holdFreq, PHASE_X, 0, dark_wait, False),
                (CAMERA, holdFreq, PHASE_X, 0, tau, True),
            ]
            _emit_cycle(seqgen, ref_start, ref_body, self.num_loops)
            _emit_cycle(seqgen, *_strip_camera_ttl(ref_start, ref_body), self.num_readout_loops)

        self.finish()
        return
