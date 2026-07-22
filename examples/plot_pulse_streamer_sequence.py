"""
Example: Digital + analog sequence on the Swabian Pulse Streamer 8/2

- Builds a kernel mixing digital channels (laser, camera trigger) with
  analog channels (MW I/Q amplitude) using the same PulseKernel API.
- Compiles the kernel through the PulseStreamerAdapter in offline mode
  (no hardware/IP address required) into digital + analog patterns.
- Plots the kernel, rendering analog channels by their programmed level.

Run:
    python examples/plot_pulse_streamer_sequence.py
"""
from __future__ import annotations

import os
import sys

# Make local packages importable without install
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
PLUGINS_ROOT = os.path.join(REPO_ROOT, "plugins")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
if PLUGINS_ROOT not in sys.path:
    sys.path.insert(0, PLUGINS_ROOT)

from seqgen import ChannelType, PulseKernel  # type: ignore
from plugins.pulse_streamer import PulseStreamerAdapter  # type: ignore

IMG_DIR = os.path.join(REPO_ROOT, "examples", "img")
os.makedirs(IMG_DIR, exist_ok=True)


def main():
    # Digital channels map to Pulse Streamer digital output indices (0-7),
    # analog channels map to analog output indices (0-1).
    ch_defs = {
        "laser": 0,
        "camera": 1,
        "mw_i": 0,
        "mw_q": 1,
    }
    ch_types = {
        "laser": ChannelType.DIGITAL,
        "camera": ChannelType.DIGITAL,
        "mw_i": ChannelType.ANALOG,
        "mw_q": ChannelType.ANALOG,
    }

    # Build the abstract kernel: same PulseKernel API used for PulseBlaster.
    pk = PulseKernel(ch_defs, ch_types=ch_types)
    pk.add_pulse(["laser"], 0, 1_000)                       # 1 us laser pulse
    pk.append_delay(200)                                    # 200 ns delay
    pk.append_pulse(["mw_i"], 300, level=0.8)                # analog I pulse at 0.8 V
    pk.append_pulse(["mw_q"], 300, level=-0.4)               # analog Q pulse at -0.4 V
    pk.append_delay(100)
    pk.finish_kernel()

    print("Step 1: Kernel view (digital + analog channels)")
    pk.plot_pulses(
        title="Pulse Streamer kernel (digital + analog)",
        save_path=os.path.join(IMG_DIR, "pulse_streamer_step1_kernel.png"),
        show=False,
    )

    print("Step 2: Instruction view after convert_to_instructions()")
    pk.convert_to_instructions(const_chs=["camera"])
    pk.plot_inst_kernel(
        title="Pulse Streamer instructions",
        save_path=os.path.join(IMG_DIR, "pulse_streamer_step2_instructions.png"),
        show=False,
    )

    # Compile the same kernel via the Pulse Streamer adapter (offline mode:
    # no ip_address needed to inspect the compiled digital/analog patterns).
    adapter = PulseStreamerAdapter(ch_defs=ch_defs, ch_types=ch_types)
    adapter.start_programming()
    adapter.add_kernel(pk, num_loop=1, const_chs=["camera"])
    adapter.end_sequence(100)
    adapter.stop_programming()

    print("Digital patterns (duration_ns, state):")
    for ch, pattern in adapter.digital_patterns.items():
        print(f"  {ch}: {pattern}")

    print("Analog patterns (duration_ns, volts):")
    for ch, pattern in adapter.analog_patterns.items():
        print(f"  {ch}: {pattern}")


if __name__ == "__main__":
    main()
