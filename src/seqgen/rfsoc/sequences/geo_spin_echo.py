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
    PHASE_NEG_X,
    even_ns as _even_ns,
    emit_cycle as _emit_cycle,
    strip_camera_ttl as _strip_camera_ttl,
)


class GeodesicSpinEchoSequence(RFSocSequence):
    """Spin echo with the central pi rotation defined by a frequency sweep."""

    sequence_name = "Geodesic Spin Echo"
    ch_names = ["laser", "camera"]

    def extra_log_info(self):
        return (
            f"\nFrequency: {self.frequency / 1e9:.4f} GHz"
            + f"\nGeodesic pi duration: {self.geo_pi_dur} ns"
            + f"\nPi/2 duration: {self.pi_2_dur} ns"
            + f"\nNumber of tau points: {len(self.time_list)}"
            + f"\nGeodesic frequency width: {self.geo_frequency_width} Hz"
            + f"\nGeodesic number of points: {self.geo_num_points}"
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
        geo_frequency_width: float = 0,
        geo_num_points: int = 0,
        rf_dur: float = 0,
        rf_amplitude: int | None = None,
        pi_2_dur: float = 0,
        pi_dur: float = 0,
        laser_dur: float = 0,
        laser_delay: float = 0,
        laser_to_rf_delay: float = 0,
        rf_delay: float = 0,
        **kwargs,
    ):
        seqgen: RFSOCAdapter = self.seqgen

        if sweep_x is None:
            logger.error("sweep_x (total free evolution times) must be provided for the Geodesic Spin Echo sequence.")
            return
        if geo_num_points < 2:
            raise ValueError("geo_num_points must be at least 2 for a frequency sweep.")
        if pi_dur <= 0:
            raise ValueError("pi_dur must be greater than zero.")

        self.frequency = frequency
        maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        laser_dur = _even_ns(laser_dur * 1e9)
        dark_wait = _even_ns((laser_to_rf_delay + rf_delay) * 1e9)
        self.pi_2_dur = _even_ns(pi_2_dur * 1e9)
        geo_segment_dur = _even_ns(pi_dur * 1e9)
        self.geo_frequency_width = geo_frequency_width
        self.geo_num_points = geo_num_points
        self.geo_pi_dur = geo_segment_dur * geo_num_points

        tau_ns = [t * 1e9 for t in np.asarray(sweep_x).tolist()]
        if not tau_ns:
            raise ValueError("sweep_x must contain at least one total evolution time.")
        self.time_list = [_even_ns(t) for t in tau_ns]
        if min(self.time_list) < self.geo_pi_dur:
            raise ValueError("Every sweep_x value must be at least the geodesic pi duration.")
        tau1_list = [_even_ns(np.ceil((t - self.geo_pi_dur) / 2)) for t in tau_ns]
        tau2_list = [_even_ns(np.floor((t - self.geo_pi_dur) / 2)) for t in tau_ns]

        min_tau = min(self.time_list)
        loop_time = laser_dur + dark_wait + 2 * self.pi_2_dur + self.geo_pi_dur + min_tau
        self.num_loops = int(np.ceil(self.exposure_time / loop_time)) + 1
        self.num_readout_loops = int(np.ceil(self.camera_trig_time / loop_time)) + 1

        self.log_sequence_info()
        seqgen.ub.add_instruction(LASER, frequency, 0, 0, self.exposure_time, resync=1)

        # The swept segments together form the central pi rotation.
        geo_frequencies = np.linspace(
            frequency - geo_frequency_width / 2,
            frequency + geo_frequency_width / 2,
            geo_num_points,
        )
        b_ref = bool(ref_mode)

        for tau1, tau2 in zip(tau1_list, tau2_list):
            sig_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
            sig_body = [
                (CAMERA, frequency, PHASE_X, 0, dark_wait, False),
                (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, True),
                (CAMERA, frequency, PHASE_X, 0, tau1, False),
            ]
            sig_body.extend(
                (CAMERA, float(freq), PHASE_X, maxAmp, geo_segment_dur, False)
                for freq in geo_frequencies
            )
            sig_body.extend(
                [
                    (CAMERA, frequency, PHASE_X, 0, tau2, False),
                    (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, False),
                ]
            )
            _emit_cycle(seqgen, sig_start, sig_body, self.num_loops)
            _emit_cycle(seqgen, *_strip_camera_ttl(sig_start, sig_body), self.num_readout_loops)

            if b_ref:
                if ref_mode == "no_rf":
                    ref_start = (BOTH, holdFreq, PHASE_X, 0, laser_dur, False)
                    ref_body = [
                        (CAMERA, holdFreq, PHASE_X, 0, dark_wait, False),
                        (CAMERA, holdFreq, PHASE_X, 0, self.pi_2_dur, True),
                        (CAMERA, holdFreq, PHASE_X, 0, tau1, False),
                        *[
                            (CAMERA, holdFreq, PHASE_X, 0, geo_segment_dur, False)
                            for _ in geo_frequencies
                        ],
                        (CAMERA, holdFreq, PHASE_X, 0, tau2, False),
                        (CAMERA, holdFreq, PHASE_X, 0, self.pi_2_dur, False),
                    ]
                elif ref_mode == "3π/2 at end":
                    ref_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
                    ref_body = [
                        (CAMERA, frequency, PHASE_X, 0, dark_wait, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, True),
                        (CAMERA, frequency, PHASE_X, 0, tau1, False),
                        *[
                            (CAMERA, float(freq), PHASE_X, maxAmp, geo_segment_dur, False)
                            for freq in geo_frequencies
                        ],
                        (CAMERA, frequency, PHASE_X, 0, tau2, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, 3 * self.pi_2_dur, False),
                    ]
                else:
                    ref_start = (BOTH, frequency, PHASE_X, 0, laser_dur, False)
                    ref_body = [
                        (CAMERA, frequency, PHASE_X, 0, dark_wait, False),
                        (CAMERA, frequency, PHASE_X, maxAmp, self.pi_2_dur, True),
                        (CAMERA, frequency, PHASE_X, 0, tau1, False),
                        *[
                            (CAMERA, float(freq), PHASE_X, maxAmp, geo_segment_dur, False)
                            for freq in geo_frequencies
                        ],
                        (CAMERA, frequency, PHASE_X, 0, tau2, False),
                        (CAMERA, frequency, PHASE_NEG_X, maxAmp, self.pi_2_dur, False),
                    ]
                _emit_cycle(seqgen, ref_start, ref_body, self.num_loops)
                _emit_cycle(seqgen, *_strip_camera_ttl(ref_start, ref_body), self.num_readout_loops)

        self.finish()
        return
