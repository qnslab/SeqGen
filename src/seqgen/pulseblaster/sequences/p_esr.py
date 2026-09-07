# This function defines the ODMR sequence for the pulseblaster
from __future__ import annotations

import logging
import typing

from seqgen.pulseblaster.sequences.base import PulseBlasterSequence

try:
    from loguru import logger
except Exception:
    logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from ..pulseblaster import PulseBlasterAdapter

from seqgen.pulse_kernel import PulseKernel

class PODMRSequence(PulseBlasterSequence):
    """PulseBlaster Pulsed ODMR sequence builder.

    Same programming logic as the original ``seq_p_esr`` function: a
    ``PulseKernel``-based signal/reference pair is built and streamed to the
    PulseBlaster via ``add_kernel``/``add_instruction`` with hardware
    LOOP/END_LOOP opcodes. Only the wrapping (class + ``load()``) matches the
    ``PODMRSequence`` naming used by the Pulse Streamer's
    ``seqgen.pulse_streamer.sequences.p_esr.PODMRSequence``; the two are
    programmed completely differently under the hood.
    """

    sequence_name = "Pulsed ODMR"
    ch_names = ["laser", "rf_x", "camera", "rf_trig"]

    def log_sequence_info(self, 
                        camera_on_time_ns: int, 
                        camera_trig_time: int, 
                        ref_mode: str, 
                        f_pts: int,
                        laser_dur: float,
                        rf_dur: float,
                        laser_delay: float,
                        laser_to_rf_delay: float,
                        rf_delay: float
                          ):
        logger.info(f"Loaded {self.sequence_name} sequence \n"
                    + f"Channel names: {self.ch_names}"
                    + f"\nCamera on time: {camera_on_time_ns / 1e9:.3e} s"
                    + f"\nCamera readout time: {camera_trig_time / 1e9:.3e} s"
                    + f"\nReference mode: {ref_mode}"
                    + f"\nNumber of frequency points: {f_pts}"
                    + f"\nLaser duration: {laser_dur:.3e} ns"
                    + f"\nRF duration: {rf_dur:.3e} ns"
                    + f"\nLaser delay: {laser_delay:.3e} ns"
                    + f"\nLaser to RF delay: {laser_to_rf_delay:.3e} ns"
                    + f"\nRF delay: {rf_delay:.3e} ns"
                    )


    def load(
        self,
        ref_mode: str = "no_rf",
        exposure_time: float = 0,
        sweep_length: int = 1,
        avg_per_point: int = 1,
        camera_trig_time: float = 0,
        laser_dur: float = 0,
        rf_dur: float = 0,
        laser_delay: float = 0,
        laser_to_rf_delay: float = 0,
        rf_delay: float = 0,
        **kwargs,
    ):
        seqgen: PulseBlasterAdapter = self.seqgen


        if ref_mode in ("" , None):
            b_ref = False
            logger.info("Setting up pulsed ESR sequence with no reference")
        else:
            b_ref = True
        logger.info("Setting up pulsed ESR sequence with {} as a reference", ref_mode)



        # convert times to ns assuming the user inputs in s
        laser_dur = int(laser_dur * 1e9)
        rf_dur = int(rf_dur * 1e9)
        laser_delay = int(laser_delay * 1e9)
        laser_to_rf_delay = int(laser_to_rf_delay * 1e9)
        rf_delay = int(rf_delay * 1e9)
        exposure_time = int(exposure_time * 1e9)
        camera_trig_time = int(camera_trig_time * 1e9)

        self.log_sequence_info(
            exposure_time,
            camera_trig_time,
            ref_mode,
            sweep_length,
            laser_dur,
            rf_dur,
            laser_delay,
            laser_to_rf_delay,
            rf_delay
            )


        # Create the SIGNAL kernel
        pk_sig = PulseKernel(seqgen.ch_defs)
        # Program the kernel pulses
        pk_sig.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
        pk_sig.append_delay(laser_to_rf_delay)
        pk_sig.append_pulse(["rf_x"], rf_dur, ch_delay=rf_delay)
        pk_sig.finish_kernel()

        # create the REFERENCE kernel
        pk_ref = PulseKernel(seqgen.ch_defs)
        # Program the kernel pulses
        pk_ref.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
        pk_ref.append_delay(laser_to_rf_delay + rf_dur)
        pk_ref.finish_kernel()

        # Get the base kernel time
        base_time = pk_sig.get_end_time()

        # Get the number of cycles for the inner loops
        trigger_loops = int(camera_trig_time / base_time) + 1
        num_loops = int(exposure_time / base_time) + 1


        # Start the programming of the pulseblaster
        seqgen.start_programming()

        # Turn the laser on to initialize the system
        seqgen.add_instruction(**{"active_chs": ["laser"], "dur": 2 * exposure_time})

        for i in range(0,   sweep_length):
            # Start the per point average loop if required
            if avg_per_point > 1:
                inst = seqgen.add_instruction([], 12, loop="start", num=avg_per_point)
            else:
                inst = None

            # Add the SIG kernel to the sequence generator
            seqgen.add_kernel(pk_sig, num_loops, const_chs=["camera"])
            if ref_mode == "f_mod":
                # trigger the segnal generator to go to the next freq
                seqgen.add_kernel(pk_sig, trigger_loops, const_chs=["rf_trig"])
            else:
                seqgen.add_kernel(pk_sig, trigger_loops)

            # Reference pulse sequence
            if b_ref:
                seqgen.add_kernel(pk_ref, num_loops, const_chs=["camera"])
                seqgen.add_kernel(pk_ref, trigger_loops, const_chs=["rf_trig"])

            if avg_per_point > 1:
                seqgen.add_instruction([], 12, loop="end", inst=inst)

        # Turn the laser off and end sequence
        seqgen.end_sequence(1e6)

        # End of pulse program
        seqgen.stop_programming()

        return pk_sig, pk_ref
