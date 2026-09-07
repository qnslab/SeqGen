from __future__ import annotations

from typing import List
from loguru import logger
import numpy as np

from seqgen.pulse_kernel import PulseKernel

from seqgen.rfsoc.rfsoc import RFSOCAdapter


MHz = 1e6
GHz = 1e9

class ODMRSequence():
    """
    CW ODMR sequence builder.
    """

    sequence_name = "CW ODMR"
    ch_names = ["laser", "rf_x", "camera"]

    def __init__(
            self, 
            seqgen, 
        ):
        self.seqgen = seqgen
        self.sequence_params = seqgen.sequence_params
        self.ch_defs = seqgen.ch_defs


    def log_sequence_info(self, camera_on_time_ns: int, camera_readout_time_ns: int, ref_mode: str, f_pts: int):
        logger.info(f"Loaded {self.sequence_name} sequence \n"
                    + f"Channel names: {self.ch_names}"
                    + f"\nCamera on time: {camera_on_time_ns / 1e9:.3e} s"
                    + f"\nCamera readout time: {camera_readout_time_ns / 1e9:.3e} s"
                    + f"\nReference mode: {ref_mode}"
                    + f"\nNumber of frequency points: {f_pts}"
                    )


    def load(
        self,
        exposure_time: float,
        camera_trig_time: float,
        frequency_list: List[float],
        ref_mode: str = "no_rf",
        **kwargs,
    ):
        seqgen: RFSOCAdapter = self.seqgen

        # convert times to ns assuming the user inputs in s
        exposure_time = int(round(exposure_time * 1e9))  # s to ns
        camera_trig_time = int(round(camera_trig_time * 1e9))  # s to ns

        # for a ODMR sequence we need to interate of diferent frequencies that are 
        # directly synthesized by the RFSoC. The sweep_length is the number of frequencies 
        # that will be used in the sweep. 

        #enable the sinc filter to minimise rolloff from DAC
        seqgen.rfbuilder.sinc_filters = 1


        maxAmp = seqgen.ub.get_max_amp()
        holdFreq = seqgen.ub.get_max_freq() #setting frequency to this value will cause it to hold the frequency from the previous instruction


        seqgen.ub.add_instruction(0b0011,frequency_list[0],0,maxAmp,100)
        for f in frequency_list:
            # Signal pulse
            seqgen.ub.add_instruction(0b0011, f, 0, maxAmp, exposure_time, resync=1)
            seqgen.ub.add_instruction(0b0001, f, 0, maxAmp, camera_trig_time)
            # Reference pulse
            if ref_mode == "no_rf":
                seqgen.ub.add_instruction(0b0011, holdFreq, 0, 0, exposure_time, resync=1)
                seqgen.ub.add_instruction(0b0001, holdFreq, 0, 0, camera_trig_time)

        #set all ttl connections, and connect all blocks
        seqgen.rfbuilder.update()

        return
