from __future__ import annotations

from typing import List
from loguru import logger
import numpy as np

from seqgen.rfsoc.rfsoc import RFSOCAdapter
from seqgen.rfsoc.sequences.base import RFSocSequence, PHASE_X

# This sequence uses its own 3-bit TTL convention (bit0 = laser, bit1 =
# rf_x, bit2 = camera) rather than the 2-bit laser/camera convention used
# by the other RFSoC sequences, matching its ``ch_names``.
LASER = 0b001
RF_X = 0b010
CAMERA = 0b100
SIGNAL = LASER | RF_X  # laser + rf_x asserted together during the RF-on period
READOUT = LASER  # laser only, asserted during the camera trigger period


class ODMRSequence(RFSocSequence):
    """
    CW ODMR sequence builder, sweeping RF frequency.
    """

    sequence_name = "CW ODMR"
    ch_names = ["laser", "rf_x", "camera"]

    def extra_log_info(self):
        return f"\nNumber of frequency points: {len(self.frequency_list)}" + f"\nRF amplitude: {self.rf_amplitude}"

    def load(
        self,
        exposure_time: float = 0,
        camera_trig_time: float = 0,
        frequency_list: List[float] = None,
        rf_amplitude: int | None = None,  # percentage of the maximum RF amplitude, default zero power
        ref_mode: str = "no_rf",
        **kwargs,
    ):
        self.frequency_list = frequency_list
        self.rf_amplitude = rf_amplitude
        self.maxAmp, holdFreq = self.prepare(exposure_time, camera_trig_time, ref_mode, rf_amplitude)

        self.log_sequence_info()


        self.seqgen.ub.add_instruction(SIGNAL, frequency_list[0], 0, self.maxAmp, 100)
        for f in frequency_list:
            # Signal pulse
            self.seqgen.ub.add_instruction(SIGNAL, f, PHASE_X, self.maxAmp, self.exposure_time, resync=1)
            self.seqgen.ub.add_instruction(READOUT, f, PHASE_X, self.maxAmp, self.camera_trig_time)
            # Reference pulse
            if ref_mode == "no_rf":
                self.seqgen.ub.add_instruction(SIGNAL, holdFreq, PHASE_X, 0, self.exposure_time, resync=1)
                self.seqgen.ub.add_instruction(READOUT, holdFreq, PHASE_X, 0, self.camera_trig_time)

        self.finish()

        return

