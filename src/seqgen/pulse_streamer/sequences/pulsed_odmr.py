from __future__ import annotations

from loguru import logger
import numpy as np

from .base import PulseStreamerSequence


HIGH = 1
LOW = 0

class PulsedODMRSequence(PulseStreamerSequence):
    """Pulse Streamer Pulsed ODMR sequence builder."""

    sequence_name = "PulsedODMR"
    ch_names = ["laser", "rf_x", "camera"]

    def signal_sequence(
        self,
        rf_dur: int,
        repeats: int,
        laser_dur: int,
        rf_delay: int,
        camera_state: int = HIGH,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:

        laser_sequence = self.repeated_block(
            (laser_dur, HIGH),
            (rf_delay + rf_dur, LOW),
            repeats=repeats,
        )

        rf_x_sequence = self.repeated_block(
            (laser_dur + rf_delay, LOW),
            (rf_dur, HIGH),
            repeats=repeats,
        )

        # get the total duration of the sequence to determine how long the camera should be on
        camera_time = self.get_total_block_duration(rf_x_sequence)
        print(f"Camera signal time: {camera_time} ns")

        camera_sequence = self.repeated_block(
            (camera_time, camera_state),
            repeats=1,
        )
        return laser_sequence, rf_x_sequence, camera_sequence

    def reference_sequence(
        self,
        rf_dur: int,
        repeats: int,
        laser_dur: int,
        rf_delay: int,
        camera_state: int = HIGH,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:

        laser_sequence = self.repeated_block(
            (laser_dur, HIGH),
            (rf_delay + rf_dur, LOW),
            repeats=repeats,
        )

        rf_x_sequence = self.repeated_block(
            (laser_dur + rf_delay + rf_dur, LOW),
            repeats=repeats,
        )

        # get the total duration of the sequence to determine how long the camera should be on
        camera_time = self.get_total_block_duration(rf_x_sequence)

        print(f"Camera reference time: {camera_time} ns")
        camera_sequence = self.repeated_block(
            (camera_time, camera_state),
            repeats=1,
        )
        return laser_sequence, rf_x_sequence, camera_sequence

    def load(
        self,
        number_pts: int = 0,
        laser_dur: float = 3e-6,
        laser_delay: float = 0,
        laser_initialization_time: float | None = None,
        rf_delay: float = 0,
        rf_dur: float = 1e-6,
        ref_mode: str = "no_rf",
        camera_on_time: float = 1e-3,
        camera_readout_time: float = 0.1e-3,
        **kwargs,
    ):

        if laser_initialization_time in (None, 0):
            laser_initialization_time = 3 * laser_dur

        if ref_mode == ("" or None):
            logger.info("Setting up Rabi sequence with no reference")
        else:
            logger.info(f"Setting up Rabi sequence with {ref_mode} as a reference")


        laser_dur_ns = int(round(laser_dur * 1e9))
        laser_delay_ns = int(round(laser_delay * 1e9))
        rf_delay_ns = int(round(rf_delay * 1e9))
        laser_initialization_time_ns = int(round(laser_initialization_time * 1e9))
        camera_on_time_ns = int(round(camera_on_time * 1e9))
        camera_readout_time_ns = int(round(camera_readout_time * 1e9))
        rf_dur_ns = int(round(rf_dur * 1e9))

        base_block_time = laser_dur_ns + rf_delay_ns + rf_dur_ns
        n_repetitions = round(camera_on_time_ns / base_block_time)
        n_repetitions_readout = round(camera_readout_time_ns / base_block_time)
        b_ref = ref_mode not in ("", None)

        seq_laser   = [(laser_initialization_time_ns, HIGH)]
        seq_rf_x    = [(laser_initialization_time_ns, LOW)]
        seq_camera  = [(laser_initialization_time_ns, LOW)]

        for _ in range(number_pts):
            sig_laser, sig_rf_x, sig_camera = self.signal_sequence(
                rf_dur_ns,
                n_repetitions,
                laser_dur_ns,
                rf_delay_ns,
                camera_state=HIGH,
            )
            seq_laser += sig_laser
            seq_rf_x += sig_rf_x
            seq_camera += sig_camera

            sig_laser_readout, sig_rf_x_readout, sig_camera_readout = self.signal_sequence(
                rf_dur_ns,
                n_repetitions_readout,
                laser_dur_ns,
                rf_delay_ns,
                camera_state=LOW,
            )
            seq_laser += sig_laser_readout
            seq_rf_x += sig_rf_x_readout
            seq_camera += sig_camera_readout

            ref_laser, ref_rf_x, ref_camera = self.reference_sequence(
                rf_dur_ns,
                n_repetitions,
                laser_dur_ns,
                rf_delay_ns,
                camera_state=HIGH,
            )
            seq_laser += ref_laser
            seq_rf_x += ref_rf_x
            seq_camera += ref_camera

            ref_laser_readout, ref_rf_x_readout, ref_camera_readout = self.reference_sequence(
                rf_dur_ns,
                n_repetitions_readout,
                laser_dur_ns,
                rf_delay_ns,
                camera_state=LOW,
            )

            seq_laser += ref_laser_readout
            seq_rf_x += ref_rf_x_readout
            seq_camera += ref_camera_readout

        self._shift_first_segment(seq_laser, laser_delay_ns)

        self.seqgen.start_programming()

        self.set_channel_sequences({
            "laser": seq_laser,
            "rf_x": seq_rf_x,
            "camera": seq_camera,
        })
        self.seqgen.stop_programming()

        self.update_metadata(
            sequence_name=self.sequence_name,
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



    