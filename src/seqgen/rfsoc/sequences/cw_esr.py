from __future__ import annotations

from typing import List
from loguru import logger
import numpy as np

import seqgen
from seqgen.pulse_kernel import PulseKernel

from seqgen.rfsoc.rfsoc import RFSOCAdapter


MHz = 1e6
GHz = 1e9
us = 1e-6
ns = 1e-9

class ODMRSequence():
    """
    CW ODMR sequence builder.
    """

    sequence_name = "CW ODMR"
    ch_names = ["laser", "rf_x", "camera"]

    def __init__(
            self, 
            seqgen, 
            *args, 
            **kwargs
        ):
        self.seqgen = seqgen
        self.sequence_params = seqgen.sequence_params
        self.ch_defs = seqgen.ch_defs


    def log_sequence_info(self, 
                        ):
        logger.info(f"Loaded {self.sequence_name} sequence \n"
                    + f"Channel names: {self.ch_names}"
                    + f"\nCamera on time: {self.exposure_time / 1e9:.3e} s"
                    + f"\nCamera readout time: {self.camera_trig_time / 1e9:.3e} s"
                    + f"\nReference mode: {self.ref_mode}"
                    + f"\nNumber of frequency points: {len(self.frequency_list)}"
                    )


    def load(
        self,
        exposure_time: float = 0,
        camera_trig_time: float = 0,
        frequency_list: List[float] = None,
        rf_amplitude: int | None = None, # percentage of the maximum RF amplitude, default zero power
        ref_mode: str = "no_rf",
        **kwargs,
    ):
        seqgen: RFSOCAdapter = self.seqgen
        self.frequency_list = frequency_list
        self.rf_amplitude = rf_amplitude
        self.ref_mode = ref_mode

        # convert times to ns assuming the user inputs in s
        self.exposure_time = int(round(exposure_time * 1e9))  # s to ns
        self.camera_trig_time = int(round(camera_trig_time * 1e9))  # s to ns

        self.log_sequence_info()

        # Clear any previously loaded program (e.g. the priming halt instruction
        # added in RFSOCAdapter.open(), or a previously loaded sequence) before
        # building this one. Without this the new instructions are appended
        # after an existing STOP instruction at index 0, which the MicroBlaster
        # never advances past (a STOP always jumps back to instruction 0), so
        # the sequence built below would never actually run.
        seqgen.ub.clean_program()

        # enable the sinc filter to minimise rolloff from the DAC at the
        # multi-GHz frequencies this sequence synthesizes (without this the
        # RF output is heavily attenuated by the polyphase DDS upsampling)
        seqgen.rfbuilder.sinc_filters = 1

        # set the amplitude of the RF signal
        maxAmp = seqgen.ub.get_max_amp()
        if rf_amplitude is not None:
            maxAmp = maxAmp * rf_amplitude // 100
        else:
            maxAmp = 0
        holdFreq = seqgen.ub.get_max_freq() #setting frequency to this value will cause it to hold the frequency from the previous instruction


        seqgen.ub.add_instruction(0b0011, frequency_list[0], 0, maxAmp, 100)
        for f in frequency_list:
            # Signal pulse
            seqgen.ub.add_instruction(0b0011, f, 0, maxAmp, self.exposure_time, resync=1)
            # seqgen.ub.wait(0b0, holdFreq, 0, 0, exposure_time) #wait for the camera to finish reading out
            seqgen.ub.add_instruction(0b0001, f, 0, maxAmp, self.camera_trig_time)
            # seqgen.ub.wait(0b0, holdFreq, 0, 0, 2)
            # Reference pulse
            if ref_mode == "no_rf":
                seqgen.ub.add_instruction(0b0011, holdFreq, 0, 0, self.exposure_time, resync=1)
                # seqgen.ub.wait(0b0, holdFreq, 0, 0, 4)
                seqgen.ub.add_instruction(0b0001, holdFreq, 0, 0, self.camera_trig_time)


        seqgen.ub.end_program(0,0,0,0,4) 
        #set all ttl connections, and connect all blocks
        seqgen.rfbuilder.update()

        return
