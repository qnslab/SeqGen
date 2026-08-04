from __future__ import annotations

from loguru import logger
import numpy as np

from .base import PulseStreamerSequence


HIGH = 1
LOW = 0

class RabiSequence(PulseStreamerSequence):
    """Pulse Streamer Rabi sequence builder."""

    sequence_name = "Rabi"
    ch_names = ["laser", "mw_x", "camera"]

    def signal_sequence(
        self,
        tau_ns: int,
        repeats: int,
        laser_dur: int,
        rf_delay: int,
        camera_state: int = HIGH,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:

        laser_sequence = self.repeated_block(
            (laser_dur, HIGH),
            (rf_delay + tau_ns, LOW),
            repeats=repeats,
        )

        mw_x_sequence = self.repeated_block(
            (laser_dur + rf_delay, LOW),
            (tau_ns, HIGH),
            repeats=repeats,
        )

        # get the total duration of the sequence to determine how long the camera should be on
        camera_time = self.get_total_block_duration(mw_x_sequence)

        camera_sequence = self.repeated_block(
            (camera_time, camera_state),
            repeats=1,
        )
        return laser_sequence, mw_x_sequence, camera_sequence

    def reference_sequence(
        self,
        tau: int,
        repeats: int,
        laser_dur: int,
        rf_delay: int,
        camera_state: int = HIGH,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:

        laser_sequence = self.repeated_block(
            (laser_dur, HIGH),
            (rf_delay + tau, LOW),
            repeats=repeats,
        )

        mw_x_sequence = self.repeated_block(
            (laser_dur + rf_delay + tau, LOW),
            repeats=repeats,
        )

        # get the total duration of the sequence to determine how long the camera should be on
        camera_time = self.get_total_block_duration(mw_x_sequence)
        camera_sequence = self.repeated_block(
            (camera_time, camera_state),
            repeats=1,
        )
        return laser_sequence, mw_x_sequence, camera_sequence

    def load(
        self,
        sweep_x: np.ndarray | None = None,
        laser_dur: float = 3e-6,
        laser_delay: float = 0,
        laser_initialization_time: float | None = None,
        rf_delay: float = 0,
        ref_mode: str = "no_rf",
        camera_on_time: float = 1e-3,
        camera_readout_time: float = 0.1e-3,
        **kwargs,
    ):
        if sweep_x is None:
            sweep_x = np.linspace(250, 500, 2) * 1e-9

        if laser_initialization_time in (None, 0):
            laser_initialization_time = 3 * laser_dur

        if ref_mode == ("" or None):
            logger.info("Setting up Rabi sequence with no reference")
        else:
            logger.info(f"Setting up Rabi sequence with {ref_mode} as a reference")

        time_list = np.asarray(sweep_x, dtype=float)
        time_list = [int(round(i * 1e9)) for i in time_list.tolist()]
        if not time_list:
            raise ValueError("sweep_x must contain at least one time point")

        laser_dur_ns = int(round(laser_dur * 1e9))
        laser_delay_ns = int(round(laser_delay * 1e9))
        rf_delay_ns = int(round(rf_delay * 1e9))
        laser_initialization_time_ns = int(round(laser_initialization_time * 1e9))
        camera_on_time_ns = int(round(camera_on_time * 1e9))
        camera_readout_time_ns = int(round(camera_readout_time * 1e9))

        base_block_time = laser_dur_ns + rf_delay_ns + time_list[0]
        n_repetitions = round(camera_on_time_ns / base_block_time)
        n_repetitions_readout = round(camera_readout_time_ns / base_block_time)
        b_ref = ref_mode not in ("", None)

        seq_laser   = [(laser_initialization_time_ns, HIGH)]
        seq_mw_x    = [(laser_initialization_time_ns, LOW)]
        seq_camera  = [(laser_initialization_time_ns, LOW)]

        for tau in time_list:
            sig_laser, sig_mw_x, sig_camera = self.signal_sequence(
                tau,
                n_repetitions,
                laser_dur_ns,
                rf_delay_ns,
                camera_state=HIGH,
            )
            seq_laser += sig_laser
            seq_mw_x += sig_mw_x
            seq_camera += sig_camera

            sig_laser_readout, sig_mw_x_readout, sig_camera_readout = self.signal_sequence(
                tau,
                n_repetitions_readout,
                laser_dur_ns,
                rf_delay_ns,
                camera_state=LOW,
            )
            seq_laser += sig_laser_readout
            seq_mw_x += sig_mw_x_readout
            seq_camera += sig_camera_readout

            ref_laser, ref_mw_x, ref_camera = self.reference_sequence(
                tau,
                n_repetitions,
                laser_dur_ns,
                rf_delay_ns,
                camera_state=HIGH,
            )
            seq_laser += ref_laser
            seq_mw_x += ref_mw_x
            seq_camera += ref_camera

            ref_laser_readout, ref_mw_x_readout, ref_camera_readout = self.reference_sequence(
                tau,
                n_repetitions_readout,
                laser_dur_ns,
                rf_delay_ns,
                camera_state=LOW,
            )

            seq_laser += ref_laser_readout
            seq_mw_x += ref_mw_x_readout
            seq_camera += ref_camera_readout

        self._shift_first_segment(seq_laser, laser_delay_ns)

        self.seqgen.start_programming()

        self.set_channel_sequences({
            "laser": seq_laser,
            "mw_x": seq_mw_x,
            "camera": seq_camera,
        })
        self.seqgen.stop_programming()

        self.update_metadata(
            sequence_name=self.sequence_name,
            sweep_x_ns=time_list,
            laser_dur_ns=laser_dur_ns,
            laser_delay_ns=laser_delay_ns,
            rf_delay_ns=rf_delay_ns,
            laser_initialization_time_ns=laser_initialization_time_ns,
            camera_on_time_ns=camera_on_time_ns,
            camera_readout_time_ns=camera_readout_time_ns,
            n_repetitions=n_repetitions,
            n_repetitions_readout=n_repetitions_readout,
            reference_mode=ref_mode,
            reference_enabled=b_ref,
            channel_sequence_lengths={
                channel: len(sequence) for channel, sequence in self.channel_sequences.items()
            },
        )
        return self
