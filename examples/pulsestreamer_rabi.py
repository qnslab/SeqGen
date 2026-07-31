"""
Example: run the device-agnostic Rabi camera sequence on a Pulse Streamer 8/2.

This demonstrates the generalized SeqGen workflow:

1. A single sequence builder (``seq_rabi`` from
   ``plugins.pulseblaster.camera_sequences``) describes the experiment purely
   in terms of ``PulseKernel`` calls and the ``seqgen`` adapter API
   (``start_programming``/``add_kernel``/``add_instruction``/``end_sequence``/
   ``stop_programming``). It has no PulseBlaster-specific code in it.
2. Any adapter implementing that same API can execute it. Here we use
   ``PulseStreamerAdapter`` instead of the PulseBlaster adapter -- the
   sequence builder code is completely unchanged.
3. The adapter compiles the abstract kernel into Pulse Streamer digital
   patterns (and would compile analog patterns too, if any channels were
   declared as analog).

If ``ip_or_serial`` is left as ``None`` (or the device can't be reached) the
adapter runs in offline mode: the sequence is still built and compiled into
``digital_patterns``/``analog_patterns`` for inspection/plotting, but nothing
is streamed to hardware.

Run:
    python examples/pulsestreamer_rabi.py
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

import numpy as np

from plugins.pulse_streamer import PulseStreamerAdapter  # type: ignore
from plugins.pulseblaster.camera_sequences.rabi import seq_rabi  # type: ignore

# Pulse Streamer 8/2 has 8 digital outputs (indices 0-7) and 2 analog outputs
# (indices 0-1). All channels here are digital, so ch_types defaults to
# ChannelType.DIGITAL for every entry.
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

sequence_params = {
    "laser_delay": 340e-9,
    "rf_delay": 12e-9,
    "camera_trig_time": 10e-3,
}

sweep_x = np.linspace(20, 500, 51) * 1e-9

ip_or_serial = '169.254.8.2'  # edit to your Pulse Streamer's IP/hostname/serial to stream to hardware; leave None to compile offline only

adapter = PulseStreamerAdapter(ch_defs=ch_defs, sequence_params=sequence_params, ip_address=ip_or_serial)
connected, msg = adapter.open()
print(msg)

# Program the pulse sequence: identical call signature/body to the
# PulseBlaster example, only the adapter passed in differs.
pk_sig, pk_ref = seq_rabi(
    adapter,
    sequence_params=sequence_params,
    sweep_x=sweep_x,
    ref_mode="no_rf",
    exp_t=30e-3,
    laser_dur=1e-6,
    laser_delay=300e-9,
    rf_delay=50e-9,
    avg_per_point=1,
    camera_trig_time=1e-3,
)

print("\nCompiled digital patterns (duration_ns, state):")
for ch, pattern in adapter.digital_patterns.items():
    print(f"  {ch}: {pattern[:5]}{' ...' if len(pattern) > 5 else ''}")

print("\nThe signal-kernel instruction pattern is shown in a Pop-Up window. Close it to proceed.")
pk_sig.plot_inst_kernel(title="Rabi signal kernel (Pulse Streamer)")

if connected and adapter._ps is not None:
    print("\nStreaming sequence to Pulse Streamer hardware...")
    adapter.start()
    print("Output running on Pulse Streamer")
else:
    print("\nNo hardware connection -- sequence compiled offline only (set ip_or_serial to stream).")