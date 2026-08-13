from __future__ import annotations

import logging

import numpy as np

try:
    from loguru import logger
except Exception:
    logger = logging.getLogger(__name__)

from seqgen.pulse_kernel import PulseKernel


def seq_rabi(
    seqgen,
    sequence_params: dict[str, float],
    sweep_x: np.ndarray = None,
    laser_dur: float = 3e-6,
    laser_delay: float = 0,
    laser_to_rf_delay: float = 200e-9,
    rf_delay: float = 0,
    ref_mode: str = "no_rf",
    exp_t: float = 30e-3,
    avg_per_point: int = 1,
    camera_trig_time: float = 0,
    **kwargs,
):
    if ref_mode == ("" or None):
        b_ref = False
        logger.info("Setting up Rabi sequence with no reference")
    else:
        b_ref = True
        logger.info("Setting up Rabi sequence with {} as a reference", ref_mode)

    if laser_delay == 0:
        laser_delay = sequence_params["laser_delay"]
    if rf_delay == 0:
        rf_delay = sequence_params["rf_delay"]

    if camera_trig_time == 0:
        trigger_time = sequence_params["camera_trig_time"]
    else:
        trigger_time = camera_trig_time

    laser_dur = int(laser_dur * 1e9)
    laser_delay = int(laser_delay * 1e9)
    laser_to_rf_delay = int(laser_to_rf_delay * 1e9)
    rf_delay = int(rf_delay * 1e9)
    exp_t = int(exp_t * 1e9)
    trigger_time = int(trigger_time * 1e9)

    time_list = 1e9 * sweep_x
    time_list = [int(i) for i in time_list.tolist()]

    pk_sig = PulseKernel(seqgen.ch_defs)
    pk_sig.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
    pk_sig.append_delay(laser_to_rf_delay)
    pk_sig.append_pulse(["rf_x"], 12, ch_delay=rf_delay, var_dur=True)
    pk_sig.finish_kernel()

    pk_ref = PulseKernel(seqgen.ch_defs)
    pk_ref.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
    pk_ref.append_delay(laser_to_rf_delay)
    pk_ref.append_delay(12, var_dur=True)
    pk_ref.finish_kernel()

    base_time = pk_sig.get_end_time() - 12
    num_loops = int(exp_t / base_time)
    trigger_loops = int(trigger_time / base_time)
    trigger_loops = int(trigger_loops * 1.05)

    logger.info(
        "Programming Rabi sequence with the following parameters:" +
        f"\nLaser duration: {laser_dur} ns" +
        f"\nFirst RF pulse duration: {time_list[0]} ns" +
        f"\nLast RF pulse duration: {time_list[-1]} ns" +
        f"\nLaser delay: {laser_delay} ns" +
        f"\nRF delay: {rf_delay} ns" +
        f"\nReference mode: {ref_mode}" +
        f"\nBase time: {base_time} ns" +
        f"\nCamera exposure time: {exp_t * 1e-6} ms" +
        f"\nNumber of loops: {num_loops}" +
        f"\nCamera trigger time: {trigger_time * 1e-6} ms" +
        f"\nNumber of trigger loops: {trigger_loops}"
    )

    seqgen.start_programming()
    seqgen.add_instruction(**{"active_chs": ["laser"], "dur": 2 * exp_t})

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

    seqgen.end_sequence(1e6)
    seqgen.stop_programming()

    return pk_sig, pk_ref
