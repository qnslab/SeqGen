from __future__ import annotations

import logging
import typing

import numpy as np

from seqgen.pulseblaster.sequences.base import PulseBlasterSequence

try:
    from loguru import logger
except Exception:
    logger = logging.getLogger(__name__)

from seqgen.pulse_kernel import PulseKernel

if typing.TYPE_CHECKING:
    from ..pulseblaster import PulseBlasterAdapter



class RabiSequence(PulseBlasterSequence):
    """PulseBlaster Rabi sequence builder.

    Same programming logic as the original ``seq_rabi`` function: a
    ``PulseKernel``-based signal/reference pair is built and streamed to the
    PulseBlaster via ``add_kernel``/``add_instruction`` with hardware
    LOOP/END_LOOP opcodes. Only the wrapping (class + ``load()``) matches the
    ``RabiSequence`` naming used by the Pulse Streamer's
    ``seqgen.pulse_streamer.sequences.rabi.RabiSequence``; the two are
    programmed completely differently under the hood.
    """

    sequence_name = "Rabi"
    ch_names = ["laser", "rf_x", "camera", "rf_trig"]

    def log_sequence_info(self,
                        camera_on_time_ns: int, 
                        camera_trig_time: int, 
                        trigger_loops: int,
                        num_loops: int,
                        ref_mode: str, 
                        laser_dur: float,
                        laser_delay: float,
                        laser_to_rf_delay: float,
                        rf_delay: float,
                        time_list: list[float],
                          ):

        logger.info(
            "Programming Rabi sequence with the following parameters:" +
            f"\nLaser duration: {laser_dur} ns" +
            f"\nFirst RF pulse duration: {time_list[0]} ns" +
            f"\nLast RF pulse duration: {time_list[-1]} ns" +
            f"\nLaser delay: {laser_delay} ns" +
            f"\nRF delay: {rf_delay} ns" +
            f"\nLaser to RF delay: {laser_to_rf_delay} ns" +
            f"\nReference mode: {ref_mode}" +
            f"\nCamera exposure time: {camera_on_time_ns * 1e-6} ms" +
            f"\nCamera trigger time: {camera_trig_time * 1e-6} ms" +
            f"\nNumber of trigger loops: {trigger_loops}" +
            f"\nNumber of signal loops: {num_loops}"
        )

    def load(
        self,
        ref_mode: str = "no_rf",
        exposure_time: float = 0,
        sweep_x: np.ndarray = None,
        avg_per_point: int = 1,
        camera_trig_time: float = 0,
        laser_dur: float = 0,

        laser_delay: float = 0,
        laser_to_rf_delay: float = 0,
        rf_delay: float = 0,
        **kwargs,
    ):
        seqgen: PulseBlasterAdapter = self.seqgen

        if ref_mode == ("" or None):
            b_ref = False
            logger.info("Setting up Rabi sequence with no reference")
        else:
            b_ref = True
            logger.info("Setting up Rabi sequence with {} as a reference", ref_mode)

        if sweep_x is None:
            logger.error("Sweep x values must be provided for Rabi sequence.")
            return None, None
            

        laser_dur = int(laser_dur * 1e9)
        laser_delay = int(laser_delay * 1e9)
        laser_to_rf_delay = int(laser_to_rf_delay * 1e9)
        rf_delay = int(rf_delay * 1e9)
        exposure_time = int(exposure_time * 1e9)
        camera_trig_time = int(camera_trig_time * 1e9)

        time_list = 1e9 * sweep_x
        time_list = [int(i) for i in time_list.tolist()]


        pk_sig = PulseKernel(seqgen.ch_defs)
        pk_sig.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
        pk_sig.append_delay(laser_to_rf_delay)
        # for the kernel to be valid, the RF pulse must be at least 12 ns long to var_dur
        # The actual time is updated using the var_dur mechanism
        pk_sig.append_pulse(["rf_x"], 12, ch_delay=rf_delay, var_dur=True)
        pk_sig.finish_kernel()

        pk_ref = PulseKernel(seqgen.ch_defs)
        pk_ref.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
        pk_ref.append_delay(laser_to_rf_delay)
        pk_ref.append_delay(12, var_dur=True)
        pk_ref.finish_kernel()


        base_time = pk_sig.get_end_time() - 12
        num_loops = int(exposure_time / base_time)
        trigger_loops = int(camera_trig_time / base_time)
        trigger_loops = int(trigger_loops * 1.05)


        self.log_sequence_info(
            camera_on_time_ns=exposure_time,
            camera_trig_time=camera_trig_time,
            trigger_loops=trigger_loops,
            num_loops=num_loops,
            ref_mode=ref_mode,
            laser_dur=laser_dur,
            laser_delay=laser_delay,
            laser_to_rf_delay=laser_to_rf_delay,
            rf_delay=rf_delay,
            time_list=time_list
        )



        seqgen.start_programming()
        seqgen.add_instruction(**{"active_chs": ["laser"], "dur": 2 * exposure_time})

        for tau in time_list:
            if avg_per_point > 1:
                inst = seqgen.add_instruction([], 12, loop="start", num=avg_per_point)
            pk_sig.update_var_durs(tau)
            seqgen.add_kernel(pk_sig, num_loops, const_chs=["camera"]) 
            seqgen.add_kernel(pk_sig, trigger_loops, const_chs=[]) 
            if b_ref:
                pk_ref.update_var_durs(tau)
                seqgen.add_kernel(pk_ref, num_loops, const_chs=["camera"]) 
                seqgen.add_kernel(pk_ref, trigger_loops, const_chs=[])
                if avg_per_point > 1:
                    seqgen.add_instruction([], 12, loop="end", inst=inst)

        seqgen.add_instruction([], camera_trig_time)

        seqgen.end_sequence(1e6)
        seqgen.stop_programming()

        return pk_sig, pk_ref
