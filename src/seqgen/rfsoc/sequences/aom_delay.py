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
    even_ns as _even_ns,
    emit_cycle as _emit_cycle,
    strip_camera_ttl as _strip_camera_ttl,
)


class AomDelaySequence(RFSocSequence):
    """RFSoC AOM delay-calibration sequence builder.

    Same pulse structure as :class:`~seqgen.rfsoc.sequences.rabi.RabiSequence`
    (laser pulse followed by a single RF pulse) but with the roles of the
    swept/fixed durations reversed: ``laser_dur`` and ``rf_dur`` are held
    constant while the dark wait between the end of the laser pulse and the
    start of the RF pulse (``sweep_x``) is swept. Scanning this delay and
    looking for where the RF-induced contrast turns on/off calibrates the
    AOM's response delay relative to the RF/MW timing.
    """

    sequence_name = "AOM Delay"
    ch_names = ["laser", "camera"]

    def extra_log_info(self):
        return (
            f"\nFrequency: {self.frequency / 1e9:.4f} GHz"
            + f"\nLaser duration: {self.laser_dur} ns"
            + f"\nRF duration: {self.rf_dur} ns"
            + f"\nRF frequency: {self.frequency / 1e9:.4f} GHz"
            + f"\nRF amplitude: {self.rf_amplitude}"
            + f"\nNumber of delay points: {len(self.time_list)}"
            + f"\nNumber of loops: {self.num_loops}"
            + f"\nNumber of readout loops: {self.num_readout_loops}"
        )

    def load(
        self,
        ref_mode: str = "no_rf",
        exposure_time: float = 0,
        camera_trig_time: float = 0,
        sweep_x: np.ndarray = None,  # laser-to-RF delay sweep, in seconds
        frequency: float = 0,
        rf_amplitude: int | None = None,
        laser_dur: float = 0,
        rf_dur: float = 0,
        rf_delay: float = 0,
        **kwargs,
    ):
        if sweep_x is None:
            logger.error("sweep_x (laser-to-RF delays) must be provided for the AOM Delay sequence.")
            return

        self.frequency = frequency
        maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        self.laser_dur = _even_ns(laser_dur * 1e9)
        self.rf_dur = _even_ns(rf_dur * 1e9)
        # extra fixed dark wait tacked on to every swept delay point
        extra_wait = _even_ns(rf_delay * 1e9)

        self.time_list = [_even_ns(t * 1e9) for t in np.asarray(sweep_x).tolist()]

        min_delay = min(self.time_list)
        loop_time = self.laser_dur + extra_wait + min_delay + self.rf_dur
        self.num_loops = int(np.ceil(self.exposure_time / loop_time)) + 1
        self.num_readout_loops = int(np.ceil(self.camera_trig_time / loop_time)) + 1

        self.log_sequence_info()

        # initial laser pulse to put the system in a known state
        self.seqgen.ub.add_instruction(LASER, frequency, 0, 0, self.exposure_time, resync=1)

        for delay in self.time_list:
            sig_start = (BOTH, frequency, PHASE_X, 0, self.laser_dur, False)
            sig_body = [
                (CAMERA, frequency, PHASE_X, 0, extra_wait + delay, False),
                (CAMERA, frequency, PHASE_X, maxAmp, self.rf_dur, True),
            ]
            _emit_cycle(self.seqgen, sig_start, sig_body, self.num_loops)
            _emit_cycle(self.seqgen, *_strip_camera_ttl(sig_start, sig_body), self.num_readout_loops)

            if ref_mode == "no_rf":
                ref_start = (BOTH, holdFreq, PHASE_X, 0, self.laser_dur, False)
                ref_body = [
                    (CAMERA, holdFreq, PHASE_X, 0, extra_wait + delay, False),
                    (CAMERA, holdFreq, PHASE_X, 0, self.rf_dur, True),
                ]
                _emit_cycle(self.seqgen, ref_start, ref_body, self.num_loops)
                _emit_cycle(self.seqgen, *_strip_camera_ttl(ref_start, ref_body), self.num_readout_loops)

        self.finish()
        return
