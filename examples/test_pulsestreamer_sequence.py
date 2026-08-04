"""Test script for the Pulse Streamer Rabi sequence loader.

This script uses the new class-based Pulse Streamer sequence API so you can
inspect the generated per-channel tuple sequences before streaming anything to
hardware.

Run:
    python examples/test_pulsestreamer_programming.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from loguru import logger

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from seqgen.pulse_streamer import PulseStreamerAdapter


def main():
    ch_defs = {
        "laser": 0,
        "camera": 1,
        "mw_x": 2,
        "mw_-x": 3,
        "mw_y": 4,
        "mw_-y": 5,
        "mw_trig": 6,
        "mw2_trig": 7,
    }

    logger.remove()
    logger.add(sys.stderr, level="INFO")

    sweep_x = np.linspace(200e-9, 500e-9, 11)  # 10 points from 0 to 1 us
    number_pts = 21

    ip_or_serial='169.254.8.2' # edit this line to connect to a specific Pulse Streamer via its IP address, hostname or serial number

    adapter = PulseStreamerAdapter(
        ch_defs=ch_defs,
        address=ip_or_serial,
    )
    connected, message = adapter.open()
    print(message)

    loaded_sequence = adapter.load_sequence(
        "rabi",
        sweep_x     = sweep_x,
        ref_mode    = "no_rf",
        laser_dur   = 1e-6,
        laser_delay = 0e-9,
        rf_delay    = 200e-9,
        camera_on_time      = 1e-3,
        camera_readout_time = 0.01e-3,
    )

    # loaded_sequence = adapter.load_sequence(
    #     "pulsed_odmr",
    #     rf_dur=1e-6,
    #     number_pts=number_pts,
    #     ref_mode="no_rf",
    #     laser_dur=1e-6,
    #     laser_delay=100e-9,
    #     rf_delay=200e-9,
    #     camera_on_time=0.01e-3,
    #     camera_readout_time=0.01e-3,
    # )

    # loaded_sequence = adapter.load_seq(
    #     "cw_odmr",
    #     number_pts=number_pts,
    #     ref_mode="no_rf",
    #     camera_on_time=0.01e-3,
    #     camera_readout_time=0.01e-3,
    # )


    print("\nLoaded sequence metadata:")
    for key, value in adapter.get_loaded_sequence_info().items():
        print(f"  {key}: {value}")

    if loaded_sequence is not None:
        print("\nLoaded sequence object:")
        print(f"  {loaded_sequence.__class__.__name__}")


    if connected and adapter._ps is not None:
        print("\nStreaming to hardware...")
        adapter.start()
        print("Output running on Pulse Streamer")
    else:
        print("\nOffline mode only; no hardware stream was started.")


if __name__ == "__main__":
    main()
