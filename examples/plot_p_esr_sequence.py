"""
Example: Visualize pulsed ESR (p_esr) kernel delay shifting and wrapping

- Builds the p_esr signal/reference kernels
- Plots the kernel in stages to demonstrate:
  1) Original kernel (with channel delays in-place)
  2) After shift_ch_delays() moves channels earlier by their per-channel delay
  3) After wrap_pulses() moves negative-start segments to the end of the kernel
  4) Final device-agnostic instruction view (after convert_to_instructions)

Run:
    python examples/plot_p_esr_sequence.py
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import matplotlib.pyplot as plt

# Make local packages importable without install
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
PLUGINS_ROOT = os.path.join(REPO_ROOT, "plugins")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if PLUGINS_ROOT not in sys.path:
    sys.path.insert(0, PLUGINS_ROOT)

from plugins.pulseblaster.camera_sequences.p_esr import seq_p_esr  # type: ignore
from seqgen.pulse_kernel import PulseKernel  # type: ignore
from plugins.pulseblaster.mock_pulseblaster import MockPulseBlaster  # type: ignore

IMG_DIR = os.path.join(REPO_ROOT, "examples", "img")
os.makedirs(IMG_DIR, exist_ok=True)

def main():
    # Define channels (bit strings are placeholders for hardware; here for completeness)
    ch_defs = {
        "laser": "00000001",
        "rf_x": "00000010",
        "camera": "00000100",
        "rf_trig": "00001000",
    }

    # High-level sequence parameters (units are seconds)
    sequence_params = {
        # Exposure/integration time (s) — governs outer loop length
        "camera_trig_time": 50e-6,
    }

    # Build kernels using the p_esr sequence function
    # Choose a non-zero laser_delay to demonstrate wrapping of negative-start pulses
    seqgen = MockPulseBlaster(ch_defs=ch_defs, sequence_params=sequence_params)
    pk_sig, pk_ref = seq_p_esr(
        seqgen,
        sequence_params,
        laser_dur=3e-6,
        rf_dur=100e-9,
        laser_delay=300e-9,       # this delay will shift the laser pulse backward
        laser_to_rf_delay=300e-9, # spacing between laser and RF
        rf_delay=100e-9,          # per-channel RF delay
        ref_mode="no_rf",         # set "no_rf" to focus on the signal kernel
        exp_t=20e-6,
        sweep_len=1,
        avg_per_point=1,
    )

    # Visualize the signal kernel through the transformation stages
    print("Step 1: Original kernel (channel delays not yet shifted)")
    pk_sig.reset_kernel()  # ensure original view
    pk_sig.plot_pulses(title="Original Kernel", save_path=os.path.join(IMG_DIR, "p_esr_step1_original.png"), show=False)

    print("Step 2: After shift_ch_delays() — pulses move earlier by ch_delay")
    pk_sig.reset_kernel()
    pk_sig.shift_ch_delays()
    pk_sig.plot_pulses(title="After shift_ch_delays()", save_path=os.path.join(IMG_DIR, "p_esr_step2_shifted.png"), show=False)

    print("Step 3: After wrap_pulses() — negative-start segments wrap to end")
    pk_sig.wrap_pulses()
    pk_sig.plot_pulses(title="After wrap_pulses()", save_path=os.path.join(IMG_DIR, "p_esr_step3_wrapped.png"), show=False)

    print("Step 4: Instruction view after convert_to_instructions()")
    pk_sig.convert_to_instructions(const_chs=["camera"])  # camera held high across each instruction
    pk_sig.plot_inst_kernel(title="Instruction View", save_path=os.path.join(IMG_DIR, "p_esr_step4_instructions.png"), show=False)


if __name__ == "__main__":
    main()
