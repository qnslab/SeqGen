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


def plot_duration_patterns(patterns: dict[str, list[tuple[int, int]]], title: str):
    if not patterns:
        print("No patterns were compiled.")
        return

    channels = list(patterns)
    fig, ax = plt.subplots(figsize=(12, max(3, 0.7 * len(channels))))
    y_positions = list(range(len(channels)))

    for y, ch in zip(y_positions, channels):
        time_ns = 0
        baseline = y
        for dur, state in patterns[ch]:
            if state:
                ax.broken_barh([(time_ns, dur)], (baseline - 0.3, 0.6), facecolors="tab:blue")
            else:
                ax.hlines(baseline, time_ns, time_ns + dur, color="tab:gray", linewidth=1.25)
            time_ns += dur

    ax.set_yticks(y_positions)
    ax.set_yticklabels(channels)
    ax.set_xlabel("Time (ns)")
    ax.set_title(title)
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    plt.show()


def main():
    ch_defs = {
        "laser": 0,
        "rf_x": 2,
        "rf_-x": 3,
        "rf_y": 4,
        "rf_-y": 5,
        "rf_trig": 6,
        "camera": 1,
        "rf2_trig": 7,
    }

    logger.remove()
    logger.add(sys.stderr, level="INFO")

    sweep_x = np.linspace(200e-9, 500e-9, 2)  # 10 points from 0 to 1 us
    number_pts = 10

    adapter = PulseStreamerAdapter(
        ch_defs=ch_defs,
        ip_address=None,
    )
    connected, message = adapter.open()
    print(message)

    # loaded_sequence = adapter.load_seq(
    #     "rabi",
    #     sweep_x=sweep_x,
    #     ref_mode="no_rf",
    #     laser_dur=1e-6,
    #     laser_delay=100e-9,
    #     rf_delay=200e-9,
    #     camera_on_time=0.01e-3,
    #     camera_readout_time=0.01e-3,
    # )

    loaded_sequence = adapter.load_seq(
        "pulsed_odmr",
        rf_dur=1e-6,
        number_pts=number_pts,
        ref_mode="no_rf",
        laser_dur=1e-6,
        laser_delay=100e-9,
        rf_delay=200e-9,
        camera_on_time=0.01e-3,
        camera_readout_time=0.01e-3,
    )

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

    print("\nChannel tuple sequences:")
    for channel, pattern in loaded_sequence.channel_sequences.items():
        print(f"  {channel}: {pattern}\n")

    print("\nBuilding plots...")
    # plot_duration_patterns(loaded_sequence.channel_sequences, "Pulse Streamer Rabi tuple sequences")
    loaded_sequence.plot_sequences(title="Pulse Streamer Rabi tuple sequences")

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
