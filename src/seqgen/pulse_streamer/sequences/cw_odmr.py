from __future__ import annotations

from loguru import logger
import numpy as np

from .base import PulseStreamerSequence


HIGH = 1
LOW = 0

class ODMRSequence(PulseStreamerSequence):
    """Pulse Streamer ODMR sequence builder."""

    sequence_name = "CW ODMR"
    ch_names = ["laser", "mw_x", "camera", "mw_trig"]

    laser_sequence: list[tuple[int, int]] = []
    mw_x_sequence: list[tuple[int, int]] = []
    camera_sequence: list[tuple[int, int]] = []
    mw_trig_sequence: list[tuple[int, int]] = []

    def signal_sequence(
        self,
        camera_dur: int,
        camera_state: int = HIGH,
        mw_trig_state: int = LOW,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
        
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
        mw_trig_sequence = self.repeated_block(
            (camera_dur, mw_trig_state),
            repeats=1,
        )
        return laser_sequence, mw_x_sequence, camera_sequence, mw_trig_sequence

    def reference_sequence(
        self,
        camera_dur: int,
        camera_state: int = HIGH,
        mw_trig_state: int = LOW,
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:

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
        mw_trig_sequence = self.repeated_block(
            (camera_dur, mw_trig_state),
            repeats=1,
        )
        return laser_sequence, mw_x_sequence, camera_sequence, mw_trig_sequence

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
        sweep_length: int = 1,
        ref_mode: str = "no_rf",
        exposure_time: float = 0,
        camera_trig_time: float = 0,
        **kwargs,
    ):

        if ref_mode == ("" or None):
            logger.info("Setting up ODMR sequence with no reference")
        else:
            logger.info(f"Setting up ODMR sequence with {ref_mode} as a reference")

        if exposure_time == 0 or camera_trig_time == 0:
            raise ValueError("Both exposure_time and camera_trig_time must be provided.")

        camera_on_time_ns = int(round(exposure_time * 1e9))
        camera_readout_time_ns = int(round(camera_trig_time * 1e9))

        self.log_sequence_info(camera_on_time_ns, camera_readout_time_ns, ref_mode, sweep_length)

        seq_laser: list[tuple[int, int]]  = [(0, HIGH)]
        seq_mw_x: list[tuple[int, int]]   = [(0, LOW)]
        seq_camera: list[tuple[int, int]] = [(0, LOW)]
        seq_mw_trig: list[tuple[int, int]] = [(0, LOW)]

        # trigger the segnal generator to start the sequence
        seq_laser += [(camera_trig_time, HIGH)]
        seq_mw_x += [(camera_trig_time, LOW)]
        seq_camera += [(camera_trig_time, LOW)]
        seq_mw_trig += [(camera_trig_time, HIGH)]

        # program an initalisation pulse for laser stability
        seq_laser += [(camera_on_time_ns, HIGH)]
        seq_mw_x += [(camera_on_time_ns, LOW)]
        seq_camera += [(camera_on_time_ns, LOW)]    
        seq_mw_trig += [(camera_on_time_ns, LOW)]


        for _ in range(sweep_length):
            sig_laser, sig_mw_x, sig_camera, sig_mw_trig = self.signal_sequence(
                camera_on_time_ns,
                camera_state=HIGH,
            )
            seq_laser += sig_laser
            seq_mw_x += sig_mw_x
            seq_camera += sig_camera
            seq_mw_trig += sig_mw_trig

            sig_laser_readout, sig_mw_x_readout, sig_camera_readout, sig_mw_trig_readout = self.signal_sequence(
                camera_readout_time_ns,
                camera_state=LOW,
            )
            seq_laser += sig_laser_readout
            seq_mw_x += sig_mw_x_readout
            seq_camera += sig_camera_readout
            seq_mw_trig += sig_mw_trig_readout

            ref_laser, ref_mw_x, ref_camera, ref_mw_trig = self.reference_sequence(
                camera_on_time_ns,
                camera_state=HIGH,
            )
            seq_laser += ref_laser
            seq_mw_x += ref_mw_x
            seq_camera += ref_camera
            seq_mw_trig += ref_mw_trig

            ref_laser_readout, ref_mw_x_readout, ref_camera_readout, ref_mw_trig_readout = self.reference_sequence(
                camera_readout_time_ns,
                camera_state=LOW,
                mw_trig_state=HIGH,
            )

            seq_laser += ref_laser_readout
            seq_mw_x += ref_mw_x_readout
            seq_camera += ref_camera_readout
            seq_mw_trig += ref_mw_trig_readout


        self.seqgen.start_programming()

        self.set_channel_sequences({
            "laser": seq_laser,
            "mw_x": seq_mw_x,
            "camera": seq_camera,
            "mw_trig": seq_mw_trig,
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
