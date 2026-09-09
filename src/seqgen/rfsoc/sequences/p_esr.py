from __future__ import annotations

from typing import List
from loguru import logger
import numpy as np

from seqgen.rfsoc.rfsoc import RFSOCAdapter
from seqgen.rfsoc.sequences.base import (
    RFSocSequence,
    LASER,
    CAMERA,
    BOTH,
    PHASE_X,
    even_ns as _even_ns,
    emit_cycle as _emit_cycle,
    strip_camera_ttl as _strip_camera_ttl,
)


class PulsedODMRSequence(RFSocSequence):
    """
    Pulsed ODMR sequence builder, sweeping RF frequency.
    """

    sequence_name = "Pulsed ODMR"
    ch_names = ["laser", "camera"]

    def extra_log_info(self):
        return (
            f"\nNumber of frequency points: {len(self.frequency_list)}"
            + f"\nLaser duration: {self.laser_dur} ns"
            + f"\nRF duration: {self.rf_dur} ns"
            + f"\nLaser delay: {self.laser_delay} ns"
            + f"\nLaser to RF delay: {self.laser_to_rf_delay} ns"
            + f"\nRF delay: {self.rf_delay} ns"
            + f"\nNumber of loops: {self.num_loops}"
            + f"\nNumber of readout loops: {self.num_readout_loops}"
        )

    def load(
        self,
        ref_mode: str = "no_rf",
        exposure_time: float = 0,
        camera_trig_time: float = 0,
        frequency_list: List[float] = None,
        rf_amplitude: int | None = None,  # percentage of the maximum RF amplitude, default zero power
        laser_dur: float = 0,
        rf_dur: float = 0,
        rf_delay: float = 0,
        laser_delay: float = 0,
        laser_to_rf_delay: float = 0,
        **kwargs,
    ):
        self.frequency_list = frequency_list
        maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        # convert times to ns assuming the user inputs in s
        self.laser_dur = _even_ns(laser_dur * 1e9)
        self.rf_dur = _even_ns(rf_dur * 1e9)
        self.rf_delay = _even_ns(rf_delay * 1e9)
        self.laser_delay = _even_ns(laser_delay * 1e9)
        self.laser_to_rf_delay = _even_ns(laser_to_rf_delay * 1e9)
        dark_wait = self.laser_to_rf_delay + self.rf_delay

        # determine the number of loops of the sequence
        # this shortest sequence is laser_dur + dark_wait + rf_dur
        # unless we wrap the pulse sequence which is not implemented yet
        loop_time = self.laser_dur + dark_wait + self.rf_dur
        self.num_loops = int(np.ceil(self.exposure_time / loop_time)) + 1
        self.num_readout_loops = int(np.ceil(self.camera_trig_time / loop_time)) + 1

        self.log_sequence_info()

        # initialisation of the quantum system
        self.seqgen.ub.add_instruction(LASER, frequency_list[0], 0, 0, self.exposure_time, resync=1)

        b_ref = bool(ref_mode)

        for f in frequency_list:
            sig_start = (BOTH, f, PHASE_X, 0, self.laser_dur, False)
            sig_body = [
                (CAMERA, f, PHASE_X, 0, dark_wait, False),
                (CAMERA, f, PHASE_X, maxAmp, self.rf_dur, True),
            ]
            _emit_cycle(self.seqgen, sig_start, sig_body, self.num_loops)
            _emit_cycle(self.seqgen, *_strip_camera_ttl(sig_start, sig_body), self.num_readout_loops)

            if b_ref and ref_mode == "no_rf":
                ref_start = (BOTH, holdFreq, PHASE_X, 0, self.laser_dur, False)
                ref_body = [
                    (CAMERA, holdFreq, PHASE_X, 0, dark_wait, False),
                    (CAMERA, holdFreq, PHASE_X, 0, self.rf_dur, True),
                ]
                _emit_cycle(self.seqgen, ref_start, ref_body, self.num_loops)
                _emit_cycle(self.seqgen, *_strip_camera_ttl(ref_start, ref_body), self.num_readout_loops)

        self.finish()

        return

