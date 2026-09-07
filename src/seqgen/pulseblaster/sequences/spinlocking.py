# This function defines the ODMR sequence for the pulseblaster
from __future__ import annotations

import logging
import typing

import numpy as np

try:
    from loguru import logger
except Exception:
    logger = logging.getLogger(__name__)

from seqgen.pulse_kernel import PulseKernel
from seqgen.pulseblaster.sequences.base import PulseBlasterSequence

if typing.TYPE_CHECKING:
    from ..pulseblaster import PulseBlasterAdapter



class SpinlockSequence(PulseBlasterSequence):
    """PulseBlaster Spinlock sequence builder.
    """


    sequence_name = "Spinlock"
    ch_names = ["laser", "rf_x", "rf_-x", "rf_y", "camera", "rf_trig"]

    def log_sequence_info(self,
                          sweep_x: list[int],
                          laser_dur: int,
                          laser_delay: int,
                          rf_delay: int,
                          pi_2_dur: int,
                          laser_to_rf_delay: int,
                          ref_mode: str,
                          base_time: int,
                          exposure_time: float,
                          num_loops: int,
                          camera_trig_time: float,
                          trigger_loops: int,
                          ):

        logger.info(
        "Programming Spinlock sequence with the following parameters:" +
        f"\nTime start: {sweep_x[0]} ns"
        + f"\nTime stop: {sweep_x[-1]} ns"
        + f"\nTime num: {len(sweep_x)}"
        + f"\nLaser duration: {laser_dur} ns"
        + f"\nLaser delay: {laser_delay} ns"
        + f"\nLaser to RF delay: {laser_to_rf_delay} ns"
        + f"\nPi/2 pulse duration: {pi_2_dur} ns"
        + f"\nRF delay: {rf_delay} ns"
        + f"\nReference mode: {ref_mode}"
        + f"\nBase time: {base_time} ns"
        + f"\nCamera exposure time: {exposure_time * 1e-6} ms"
        + f"\nNumber of loops: {num_loops}"
        + f"\nCamera trigger time: {camera_trig_time * 1e-6} ms"
        + f"\nNumber of trigger loops: {trigger_loops}"
    )


    def load(
            self,
            ref_mode: str = "no_rf",
            sweep_x: np.ndarray = None,
            pi_2_dur: float = 0,
            laser_dur: float = 0,
            laser_delay: float = 0,
            laser_to_rf_delay: float = 0,
            rf_delay: float = 0,
            exposure_time: float = 0,
            avg_per_point: int = 1,
            camera_trig_time: float = 0,
            **kwargs,
        ):
        seqgen: PulseBlasterAdapter = self.seqgen

        if ref_mode == ("" or None):
            b_ref = False
            logger.info("Setting up Spinlock sequence with no reference")
        else:
            b_ref = True
            logger.info("Setting up Spinlock sequence with {} as a reference", ref_mode)


        # convert times to ns assuming the user inputs in s
        laser_dur = int(np.ceil(laser_dur * 1e9))
        laser_to_rf_delay = int(np.ceil(laser_to_rf_delay * 1e9))
        pi_2_dur = int(np.ceil(pi_2_dur * 1e9))
        laser_delay = int(np.ceil(laser_delay * 1e9))
        rf_delay = int(np.ceil(rf_delay * 1e9))
        exposure_time = int(np.ceil(exposure_time * 1e9))
        camera_trig_time = int(np.ceil(camera_trig_time * 1e9))

        # time_list = np.linspace(time_start, time_stop, time_num)
        time_list = 1e9 * sweep_x
        # Make the time list a list of integers
        time_list = [int(i) for i in time_list.tolist()]

        # --- SIGNAL KERNEL ---
        # initialise the pulse series object
        pk_sig = PulseKernel(seqgen.ch_defs)
        # Program the kernel pulses
        pk_sig.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
        pk_sig.append_delay(laser_to_rf_delay)
        pk_sig.append_pulse(["rf_x"], pi_2_dur, ch_delay=rf_delay)
        pk_sig.append_pulse(["rf_y"], 1, var_dur=True)
        pk_sig.append_pulse(["rf_x"], pi_2_dur, ch_delay=rf_delay)
        pk_sig.finish_kernel()

        # --- REFERENCE KERNEL ---
        # Program the kernel pulses
        pk_ref = PulseKernel(seqgen.ch_defs)
        # Program the kernel pulses
        pk_ref.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
        pk_ref.append_delay(laser_to_rf_delay)
        pk_ref.append_pulse(["rf_x"], pi_2_dur, ch_delay=rf_delay)
        pk_ref.append_pulse(["rf_y"], 1, var_dur=True)

        if ref_mode == "-π/2 at end":
            pk_ref.append_pulse(["rf_-x"], pi_2_dur, ch_delay=rf_delay)
        elif ref_mode == "3π/2 at end":
            pk_ref.append_pulse(["rf_x"], 3 * pi_2_dur, ch_delay=rf_delay)
        else:
            pk_ref.append_pulse(["rf_x"], 3 *pi_2_dur, ch_delay=rf_delay)
        pk_ref.finish_kernel()

        # Get the base kernel time
        base_time = pk_sig.get_end_time() - 1

        # Get the number of cycles for the inner loops
        num_loops = int(exposure_time / base_time) + 1
        trigger_loops = int(camera_trig_time / base_time) + 1
        

        self.log_sequence_info(
            sweep_x=time_list,
            laser_dur=laser_dur,
            laser_delay=laser_delay,
            rf_delay=rf_delay,
            ref_mode=ref_mode,
            base_time=base_time,
            laser_to_rf_delay=laser_to_rf_delay,
            pi_2_dur=pi_2_dur,
            exposure_time=exposure_time,
            num_loops=num_loops,
            camera_trig_time=camera_trig_time,
            trigger_loops=trigger_loops
        )


        # Start the programming of the pulseblaster
        seqgen.start_programming()
        # Initial laser pulse
        seqgen.add_instruction(**{"active_chs": ["laser"], "dur": 2*exposure_time})

        for tau in time_list:
            if avg_per_point > 1:
                # Make a trigger loop for the averaging that is as short as possible
                inst = seqgen.add_instruction(
                    [], 12, loop="start", num=avg_per_point, const_chs=["camera"]
                )

            pk_sig.update_var_durs(tau)
            # Add the SIG kernel to the sequence generator
            seqgen.add_kernel(pk_sig, num_loops, const_chs=["camera"])
            seqgen.add_kernel(pk_sig, trigger_loops, const_chs=[])

            # Reference pulse sequence
            if b_ref:
                # update the time in the kernel
                pk_ref.update_var_durs(tau)
                # Add the REF kernel to the sequence generator
                seqgen.add_kernel(pk_ref, num_loops, const_chs=["camera"])
                seqgen.add_kernel(pk_ref, trigger_loops, const_chs=[])

                if avg_per_point > 1:
                    seqgen.add_instruction([], 12, loop="end", inst=inst)

        seqgen.add_instruction([], camera_trig_time)

        # Turn the laser off and end sequence
        seqgen.end_sequence(1e6)

        # End of pulse program
        seqgen.stop_programming()

        return pk_sig, pk_ref
