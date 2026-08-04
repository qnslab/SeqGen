from __future__ import annotations

from loguru import logger
import numpy as np

from .base import PulseStreamerSequence


HIGH = 1
LOW = 0

class ODMRSequence(PulseStreamerSequence):
    """Pulse Streamer ODMR sequence builder."""

    sequence_name = "CW ODMR"
    ch_names = ["laser", "mw_x", "camera"]

    laser_sequence: list[tuple[int, int]] = []
    mw_x_sequence: list[tuple[int, int]] = []
    camera_sequence: list[tuple[int, int]] = []

    def signal_sequence(
        self,
        camera_dur: int,
        camera_state: int = HIGH,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
        

        laser_sequence = self.repeated_block(
            (camera_dur, HIGH),
            repeats=1,
        )

        mw_x_sequence = self.repeated_block(
            (camera_dur, HIGH),
            repeats=1,
        )

        camera_sequence = self.repeated_block(
            (camera_dur, camera_state),
            repeats=1,
        )
        return laser_sequence, mw_x_sequence, camera_sequence

    def reference_sequence(
        self,
        camera_dur: int,
        camera_state: int = HIGH,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:

        laser_sequence = self.repeated_block(
            (camera_dur, HIGH),
            repeats=1,
        )

        mw_x_sequence = self.repeated_block(
            (camera_dur, LOW),
            repeats=1,
        )

        camera_sequence = self.repeated_block(
            (camera_dur, camera_state),
            repeats=1,
        )
        return laser_sequence, mw_x_sequence, camera_sequence

    def load(
        self,
        number_pts: int = 10,
        ref_mode: str = "no_rf",
        camera_on_time: float = 1e-3,
        camera_readout_time: float = 0.1e-3,
        **kwargs,
    ):

        if ref_mode == ("" or None):
            logger.info("Setting up ODMR sequence with no reference")
        else:
            logger.info(f"Setting up ODMR sequence with {ref_mode} as a reference")

        camera_on_time_ns = int(round(camera_on_time * 1e9))
        camera_readout_time_ns = int(round(camera_readout_time * 1e9))

        seq_laser: list[tuple[int, int]]  = [(0, HIGH)]
        seq_mw_x: list[tuple[int, int]]   = [(0, LOW)]
        seq_camera: list[tuple[int, int]] = [(0, LOW)]

        for _ in range(number_pts):
            sig_laser, sig_mw_x, sig_camera = self.signal_sequence(
                camera_on_time_ns,
                camera_state=HIGH,
            )
            seq_laser += sig_laser
            seq_mw_x += sig_mw_x
            seq_camera += sig_camera

            sig_laser_readout, sig_mw_x_readout, sig_camera_readout = self.signal_sequence(
                camera_readout_time_ns,
                camera_state=LOW,
            )
            seq_laser += sig_laser_readout
            seq_mw_x += sig_mw_x_readout
            seq_camera += sig_camera_readout

            ref_laser, ref_mw_x, ref_camera = self.reference_sequence(
                camera_on_time_ns,
                camera_state=HIGH,
            )
            seq_laser += ref_laser
            seq_mw_x += ref_mw_x
            seq_camera += ref_camera

            ref_laser_readout, ref_mw_x_readout, ref_camera_readout = self.reference_sequence(
                camera_readout_time_ns,
                camera_state=LOW,
            )

            seq_laser += ref_laser_readout
            seq_mw_x += ref_mw_x_readout
            seq_camera += ref_camera_readout


        self.seqgen.start_programming()

        self.set_channel_sequences({
            "laser": seq_laser,
            "mw_x": seq_mw_x,
            "camera": seq_camera,
        })
        self.seqgen.stop_programming()

        self.update_metadata(
            sequence_name=self.sequence_name,
            camera_on_time_ns=camera_on_time_ns,
            camera_readout_time_ns=camera_readout_time_ns,
            reference_mode=ref_mode,
            channel_sequence_lengths={
                channel: len(sequence) for channel, sequence in self.channel_sequences.items()
            },
        )
        return self
