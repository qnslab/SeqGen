from __future__ import annotations

from loguru import logger
import numpy as np

from seqgen.rfsoc.rfsoc import RFSOCAdapter
from seqgen.rfsoc.sequences.base import (
    RFSocSequence,
    LASER,
    CAMERA,
    NONE,
    BOTH,
    PHASE_X,
    even_ns as _even_ns,
)


class GeodesicRabiSequence(RFSocSequence):
    """Rabi sequence made from low-to-high and high-to-low frequency sweeps."""

    sequence_name = "Geodesic Rabi"
    ch_names = ["laser", "camera"]

    def extra_log_info(self):
        return (
            f"\nFrequency: {self.frequency / 1e9:.4f} GHz"
            + f"\nGeodesic frequency width: {self.geo_frequency_width} Hz"
            + f"\nGeodesic points per direction: {self.geo_num_points}"
            + f"\nRF step duration: {self.rf_dur} ns"
            + f"\nNumber of loops: {self.num_loops}"
            + f"\nNumber of readout loops: {self.num_readout_loops}"
        )

    def get_geo_frequency_list(self, points: int) -> np.ndarray:
        """Return the list of frequencies for a geodesic sweep based on the number of points."""
        freq_list =[]
        if points <= self.geo_num_points:
            freq_list.append(self.up_frequencies[:points].tolist())
        elif points > self.geo_num_points:
            # need to interleave the up and down frequencies to create a geodesic sweep until the desired number of points is reached
            i = points
            while len(freq_list) < points:
                # if the number of points is greater than twice the number of geodesic points, we can add the full up and down frequencies to the list
                if i >= 2 * self.geo_num_points:
                    freq_list.append(self.up_frequencies)
                    freq_list.append(self.down_frequencies)
                    i -= 2 * self.geo_num_points
                # if the number of points is less than just the up frequencies, we can add the up frequencies to the list and then add the down frequencies until we reach the desired number of points
                elif i < self.geo_num_points:
                    freq_list.append(self.up_frequencies[:i])
                    i = 0
                # if the number of points is in between the up and down frequencies, we can add the up frequencies to the list and then add the down frequencies until we reach the desired number of points
                elif i < 2 * self.geo_num_points:
                    freq_list.append(self.up_frequencies)
                    freq_list.append(self.down_frequencies[:(i - self.geo_num_points)])
                    i = 0
                if i <= 0:
                    break

        freq_list = [item for sublist in freq_list for item in sublist]

        return freq_list


    def load(
        self,
        ref_mode: str = "no_rf",
        exposure_time: float = 0,
        camera_trig_time: float = 0,
        sweep_x: np.ndarray = None,
        frequency: float = 0,
        geo_frequency_width: float = 0,
        geo_num_points: int = 0,
        pi_dur: float = 0,
        rf_amplitude: int | None = None,
        laser_dur: float = 0,
        laser_delay: float = 0,
        laser_to_rf_delay: float = 0,
        rf_delay: float = 0,
        **kwargs,
    ):
        seqgen: RFSOCAdapter = self.seqgen

        if sweep_x is None:
            if geo_num_points is None or np.isscalar(geo_num_points) and geo_num_points < 2:
                logger.error(
                    "sweep_x (geodesic points per direction) or geo_num_points must be provided "
                    "for the Geodesic Rabi sequence."
                )
                return
            sweep_x = np.atleast_1d(geo_num_points)
            # Make sure sweep_x is an array of integers
            sweep_x = np.asarray(sweep_x, dtype=int)
        if pi_dur <= 0:
            raise ValueError("pi_dur must be greater than zero.")
        if geo_frequency_width < 0:
            raise ValueError("geo_frequency_width must not be negative.")

        self.frequency = frequency
        maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        laser_dur = _even_ns(laser_dur * 1e9)
        dark_wait = _even_ns((laser_to_rf_delay + rf_delay) * 1e9)
        self.rf_dur = _even_ns(pi_dur * 1e9)
        self.geo_frequency_width = geo_frequency_width
        self.geo_num_points = geo_num_points
        self.up_frequencies = np.linspace(
            frequency - geo_frequency_width / 2,
            frequency + geo_frequency_width / 2,
            geo_num_points,
        )
        self.down_frequencies = self.up_frequencies[::-1]


        min_tau = self.rf_dur
        loop_time = laser_dur + dark_wait + min_tau
        self.num_loops = int(np.ceil(self.exposure_time / loop_time)) + 1
        self.num_readout_loops = int(np.ceil(self.camera_trig_time / loop_time)) + 1

        self.log_sequence_info()
        seqgen.ub.add_instruction(LASER, self.frequency, 0, 0, self.exposure_time, resync=1)


        b_ref = bool(ref_mode)
        for num_points in sweep_x:
            geo_f_list = self.get_geo_frequency_list(int(num_points))
            # logger.info(f"Geodesic frequency list for {num_points} points: {geo_f_list}")

            # Signal with camera
            seqgen.ub.start_loop(BOTH, frequency, PHASE_X, 0, laser_dur, loops=self.num_loops, resync=False) 
            seqgen.ub.add_instruction(CAMERA, frequency, PHASE_X, 0, dark_wait, resync=True)
             
            # Calculate the number of up and down full subroutines that can fit in the desired number of points
            num_subroutines = int(np.floor(num_points / (2*len(self.up_frequencies))))
            logger.info(f"Number of full subroutines for {num_points} points: {num_subroutines}")
            if num_subroutines >= 1:
                for _ in range(num_subroutines):
                    seqgen.ub.jump_subroutine(CAMERA, frequency, PHASE_X, 0, 4,"geo_sig")
            
                geo_f_list_sub = geo_f_list[2*num_subroutines * len(self.up_frequencies):]  # Remaining frequencies after full subroutines
            else:
                geo_f_list_sub = geo_f_list  # Use the entire list if not enough for full subroutines
            logger.info(f"Geodesic frequency list for {num_points} points: {geo_f_list_sub}")
            if len(geo_f_list_sub) > 0:
                for index, freq in enumerate(geo_f_list_sub):
                    seqgen.ub.add_instruction(CAMERA, float(freq), PHASE_X, maxAmp, self.rf_dur, resync=False)
            seqgen.ub.end_loop(BOTH, frequency, PHASE_X, 0, laser_dur, resync=False)
            
            # Camera readout loop without camera trigger
            seqgen.ub.start_loop(LASER, frequency, PHASE_X, 0, laser_dur, loops=self.num_readout_loops, resync=False)
            seqgen.ub.add_instruction(NONE, frequency, PHASE_X, 0, dark_wait, resync=False)
            if num_subroutines >= 1:
                for _ in range(num_subroutines):
                    seqgen.ub.jump_subroutine(NONE, frequency, PHASE_X, 0, 4,"geo_sig_no_camera")
            if len(geo_f_list_sub) > 0:
                for index, freq in enumerate(geo_f_list_sub):
                    seqgen.ub.add_instruction(NONE, float(freq), PHASE_X, maxAmp, self.rf_dur, resync=False)
            seqgen.ub.end_loop(LASER, frequency, PHASE_X, 0, laser_dur, resync=False)


            if b_ref:
                # NO RF
                # Reference with camera 
                seqgen.ub.start_loop(BOTH, frequency, PHASE_X, 0, laser_dur, loops=self.num_loops, resync=False) 
                seqgen.ub.add_instruction(CAMERA, frequency, PHASE_X, 0, dark_wait, resync=False)
                if num_subroutines >= 1:
                    for _ in range(num_subroutines):
                        seqgen.ub.jump_subroutine(CAMERA, frequency, PHASE_X, 0, 4,"geo_ref")
                
                if len(geo_f_list_sub) > 0:
                    for index, freq in enumerate(geo_f_list_sub):
                        seqgen.ub.add_instruction(CAMERA, float(freq), PHASE_X, 0, self.rf_dur, resync=False)
                seqgen.ub.end_loop(BOTH, frequency, PHASE_X, 0, laser_dur, resync=False)

                # Camera readout loop without camera trigger
                seqgen.ub.start_loop(LASER, frequency, PHASE_X, 0, laser_dur, loops=self.num_readout_loops, resync=False)
                seqgen.ub.add_instruction(NONE, frequency, PHASE_X, 0, dark_wait, resync=False)
                if num_subroutines >= 1:
                    for _ in range(num_subroutines):
                        seqgen.ub.jump_subroutine(NONE, frequency, PHASE_X, 0, 4,"geo_ref_no_camera")
                if len(geo_f_list_sub) > 0:
                    for index, freq in enumerate(geo_f_list_sub):
                        seqgen.ub.add_instruction(NONE, float(freq), PHASE_X, 0, self.rf_dur, resync=False)
                seqgen.ub.end_loop(LASER, frequency, PHASE_X, 0, laser_dur, resync=False)


        # SUBROUTINES



        # Up frequency scan sub routine
        seqgen.ub.add_instruction(CAMERA, self.up_frequencies[0], PHASE_X, maxAmp, self.rf_dur, resync=False, label="geo_sig")
        for index, freq in enumerate(self.up_frequencies[1:-1]):
            seqgen.ub.add_instruction(CAMERA, float(freq), PHASE_X, maxAmp, self.rf_dur, resync=False)
        for index, freq in enumerate(self.down_frequencies[1:-2]):
            seqgen.ub.add_instruction(CAMERA, float(freq), PHASE_X, maxAmp, self.rf_dur, resync=False)
        seqgen.ub.return_subroutine(CAMERA, float(self.down_frequencies[-1]), PHASE_X, maxAmp, self.rf_dur, resync=False)
     
        # SIGNAL WITH NO CAMERA TRIGGER
        seqgen.ub.add_instruction(NONE, self.up_frequencies[0], PHASE_X, maxAmp, self.rf_dur, resync=False, label="geo_sig_no_camera")
        for index, freq in enumerate(self.up_frequencies[1:-1]):
            seqgen.ub.add_instruction(NONE, float(freq), PHASE_X, maxAmp, self.rf_dur, resync=False)
        for index, freq in enumerate(self.down_frequencies[1:-2]):
            seqgen.ub.add_instruction(NONE, float(freq), PHASE_X, maxAmp, self.rf_dur, resync=False)
        seqgen.ub.return_subroutine(NONE, float(self.down_frequencies[-1]), PHASE_X, maxAmp, self.rf_dur, resync=False)
     

        
        # Down frequency scan sub routine
        # seqgen.ub.add_instruction(CAMERA, self.down_frequencies[0], PHASE_X, maxAmp, self.rf_dur, resync=False, label="geo_down")
        # for index, freq in enumerate(self.down_frequencies[1:-2]):
        #     seqgen.ub.add_instruction(CAMERA, float(freq), PHASE_X, maxAmp, self.rf_dur, resync=False)
        # seqgen.ub.return_subroutine(CAMERA, float(self.down_frequencies[-1]), PHASE_X, maxAmp, self.rf_dur, resync=False)

        # seqgen.ub.add_instruction(NONE, self.down_frequencies[0], PHASE_X, maxAmp, self.rf_dur, resync=False, label="geo_down_no_camera")
        # for index, freq in enumerate(self.down_frequencies[1:-2]):
        #     seqgen.ub.add_instruction(NONE, float(freq), PHASE_X, maxAmp, self.rf_dur, resync=False)
        # seqgen.ub.return_subroutine(NONE, float(self.down_frequencies[-1]), PHASE_X, maxAmp, self.rf_dur, resync=False)


        # Up frequency scan sub routine
        seqgen.ub.add_instruction(CAMERA, self.up_frequencies[0], PHASE_X, 0, self.rf_dur, resync=False, label="geo_ref")
        for index, freq in enumerate(self.up_frequencies[1:-1]):
            seqgen.ub.add_instruction(CAMERA, float(freq), PHASE_X, 0, self.rf_dur, resync=False)
        for index, freq in enumerate(self.down_frequencies[1:-2]):
            seqgen.ub.add_instruction(CAMERA, float(freq), PHASE_X, 0, self.rf_dur, resync=False)
        seqgen.ub.return_subroutine(CAMERA, float(self.down_frequencies[-1]), PHASE_X, 0, self.rf_dur, resync=False)

        seqgen.ub.add_instruction(NONE, self.up_frequencies[0], PHASE_X, 0, self.rf_dur, resync=False, label="geo_ref_no_camera")
        for index, freq in enumerate(self.up_frequencies[1:-1]):
            seqgen.ub.add_instruction(NONE, float(freq), PHASE_X, 0, self.rf_dur, resync=False)
        for index, freq in enumerate(self.down_frequencies[1:-2]):
            seqgen.ub.add_instruction(NONE, float(freq), PHASE_X, 0, self.rf_dur, resync=False)
        seqgen.ub.return_subroutine(NONE, float(self.down_frequencies[-1]), PHASE_X, 0, self.rf_dur, resync=False)

        self.finish()
        return


