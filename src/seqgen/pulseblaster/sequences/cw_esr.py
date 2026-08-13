from __future__ import annotations

import typing
from loguru import logger
import numpy as np

from seqgen.pulse_kernel import PulseKernel

from .base import PulseBlasterSequence

if typing.TYPE_CHECKING:
    from ..pulseblaster import PulseBlasterAdapter


class ODMRSequence(PulseBlasterSequence):
    """PulseBlaster CW ODMR sequence builder.

    Same programming logic as the original ``seq_cw_esr`` function: a
    ``PulseKernel``-based signal/reference pair is built and streamed to the
    PulseBlaster via ``add_kernel``/``add_instruction`` with hardware
    LOOP/END_LOOP opcodes. Only the wrapping (class + ``load()``) matches the
    ``ODMRSequence`` naming used by the Pulse Streamer's
    ``seqgen.pulse_streamer.sequences.cw_odmr.ODMRSequence``; the two are
    programmed completely differently under the hood.
    """

    sequence_name = "CW ODMR"
    ch_names = ["laser", "mw_x", "camera", "mw_trig"]

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
        ref_mode: str = "no_rf",
        exposure_time: float = 0,
        sweep_length: int = 1,
        avg_per_point: int = 1,
        camera_trig_time: float = 0,
        **kwargs,
    ):
        seqgen: PulseBlasterAdapter = self.seqgen
        sequence_params = self.sequence_params

        if camera_trig_time == 0:
            trigger_time = sequence_params["camera_trig_time"]  # s
        else:
            trigger_time = camera_trig_time
        if ref_mode in ("" , None):
            b_ref = False
            logger.info("Setting up CW ODMR sequence with no reference")
        else:
            b_ref = True
            logger.info("Setting up CW ODMR sequence with {} as a reference", ref_mode)

        # convert times to ns assuming the user inputs in s
        exposure_time = int(round(exposure_time * 1e9))  # s to ns
        trigger_time = int(round(trigger_time * 1e9))  # s to ns

        self.log_sequence_info(
            exposure_time,
            trigger_time,
            ref_mode,
            sweep_length)

        # ------- SIGNAL -------
        pk_sig = PulseKernel(seqgen.ch_defs)
        # Program the kernel pulses
        pk_sig.add_pulse(["laser", "mw_x"], 0, exposure_time)

        # ------- Trigger -------
        pk_sig_trig = PulseKernel(seqgen.ch_defs)
        pk_sig_trig.add_pulse(["laser", "mw_x"], 0, trigger_time)

        # ------- REFERENCE -------
        pk_ref = PulseKernel(seqgen.ch_defs)
        if ref_mode == "no_rf":
            pk_ref.append_pulse(["laser"], exposure_time)
        elif ref_mode == "no_laser":
            pk_ref.append_pulse(["mw_x"], exposure_time)

        # ------- Trigger -------
        pk_ref_trig = PulseKernel(seqgen.ch_defs)
        if ref_mode == "no_rf":
            pk_ref_trig.append_pulse(["laser"], trigger_time)
        elif ref_mode == "no_laser":
            pk_ref_trig.append_pulse(["mw_x"], trigger_time)
        elif ref_mode == "f_mod":
            pk_ref_trig.append_pulse(["laser", "mw_x"], trigger_time)

        # Start the programming of the pulseblaster
        seqgen.start_programming()

        # Turn the laser on to initialize the system
        seqgen.add_instruction(**{"active_chs": ["laser"], "dur": exposure_time})

        for _ in range(0, sweep_length):
            # Start the per point average loop if required
            if avg_per_point > 1:
                inst = seqgen.add_instruction([], 12, loop="start", num=avg_per_point)

            # Add the SIG kernel to the sequence generator
            seqgen.add_kernel(pk_sig, 1, const_chs=["camera"])
            if ref_mode == "f_mod":
                # trigger the signal generator to go to the next freq
                seqgen.add_kernel(pk_sig, 1, const_chs=["mw_trig"])
            else:
                seqgen.add_kernel(pk_sig, 1)

            if b_ref:
                seqgen.add_kernel(pk_ref, 1, const_chs=["camera"])
                seqgen.add_kernel(pk_ref_trig, 1, const_chs=["mw_trig"])

            if avg_per_point > 1:
                seqgen.add_instruction([], 12, loop="end", inst=inst)

            seqgen.add_instruction([], dur=trigger_time)

        # Turn the laser off and end sequence
        seqgen.end_sequence(10e6)

        # End of pulse program
        seqgen.stop_programming()

        self.pk_sig = pk_sig
        self.pk_ref = pk_ref
        self.update_metadata(
            reference_mode=ref_mode,
            reference_enabled=b_ref,
            exp_t_ns=exposure_time,
            trigger_time_ns=trigger_time,
            sweep_len=sweep_length,
            avg_per_point=avg_per_point,
        )
        return self
