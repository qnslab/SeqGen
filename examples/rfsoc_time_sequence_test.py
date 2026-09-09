"""
Manual hardware test: run one of the RFSoC *time-sweep* sequences (Rabi,
Ramsey, Spin Echo, Spinlocking, T1, CPMG, XY8) so the laser/camera TTL lines
and RF (DDS) output can be checked on an oscilloscope.

This is the time-sweep counterpart to ``rfsoc_test.py`` (which exercises the
frequency-sweep sequences ``cw_odmr``/``pulsed_odmr``). Pick a sequence below
by setting ``SEQUENCE_NAME`` and adjust its parameters in ``SEQUENCE_PARAMS``.

This is not an automated test -- it just opens a connection to the board,
loads the selected sequence at a fixed RF frequency while sweeping a time
parameter (RF pulse duration, free evolution time, etc.), starts it running,
and leaves it running until you press Ctrl+C, at which point it stops and
disconnects cleanly.

Requires:
- The RFSoC control host with the ``RFBuilder``/``RFSOC4x2`` SDK installed
  and importable (this is an external hardware SDK, not a pip dependency of
  SeqGen -- see the ``from RFBuilder import *`` in ``seqgen.rfsoc.rfsoc``).
- The board powered on and reachable at ``address`` below.

Run:
    python examples/rfsoc_time_sequence_test.py
"""
from __future__ import annotations

import os
import sys
import time
import numpy as np

# Make the local seqgen package importable without installing it.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from seqgen.rfsoc.rfsoc import RFSOCAdapter

# --- Board connection settings - edit to match your setup -----------------
board_num = 0
address = "169.254.127.84"

# These time-sweep sequences drive the MicroBlaster flag/RF outputs
# directly, so ch_defs/sequence_params aren't used to build them, but the
# adapter still expects them for API consistency with the other device
# adapters.
ch_defs = {
    "laser": 0,
    "camera": 1,
}
sequence_params = {}

# --- Choose which sequence to run ---------------------------------------
# One of: "rabi", "ramsey", "spin_echo", "spinlocking", "t1", "cpmg", "xy"
SEQUENCE_NAME = "xy"

# Common settings shared by every sequence.
frequency = 2e6          # Hz, fixed RF frequency (e.g. the ESR resonance)
exposure_time = 0.01e-3      # s, signal (and reference) exposure per point
camera_trig_time = 0.001e-3    # s, camera trigger/readout time per point
rf_amplitude = 100          # percentage (0-100) of max DDS amplitude
laser_dur = 1e-6            # s, laser initialisation pulse duration
laser_to_rf_delay = 300e-9   # s, dark wait between laser and first RF pulse
rf_delay = 0                # s, additional dark wait before the RF pulse(s)

# Per-sequence sweep points and extra parameters.
SEQUENCE_PARAMS = {
    "rabi": dict(
        ref_mode="no_rf",
        sweep_x=np.linspace(1e-6, 5e-6, 5).tolist(),  # RF pulse duration
    ),
    "ramsey": dict(
        ref_mode="no_rf",
        sweep_x=np.linspace(1e-6, 5e-6, 5).tolist(),  # free evolution time tau
        pi_2_dur=250e-9,
    ),
    "spin_echo": dict(
        ref_mode="no_rf",
        sweep_x=np.linspace(1e-6, 10e-6, 5).tolist(),  # total free evolution time tau
        pi_dur=500e-9,
        pi_2_dur=250e-9,
    ),
    "spinlocking": dict(
        ref_mode="no_rf",
        sweep_x=np.linspace(1e-6, 10e-6, 5).tolist(),  # spin-lock duration
        pi_2_dur=250e-9,
    ),
    "t1": dict(
        ref_mode="π at end",
        sweep_x=np.linspace(1e-6, 1e-3, 21).tolist(),  # dark wait time
        pi_dur=100e-9,
    ),
    "cpmg": dict(
        ref_mode="no_rf",
        sweep_x=np.linspace(1e-6, 20e-6, 11).tolist(),  # total free precession time
        n_pulses=4,
        pi_dur=500e-9,
        pi_2_dur=250e-9,
    ),
    "xy": dict(
        ref_mode="no_rf",
        sweep_x=np.linspace(1e-6, 20e-6, 11).tolist(),  # total free precession time
        n_reps=1,
        pi_dur=500e-9,
        pi_2_dur=250e-9,
    ),
    "aom_delay": dict(
        ref_mode="no_rf",
        sweep_x=np.linspace(0, 2e-6, 21).tolist(),  # laser-to-RF delay
        rf_dur=200e-9,
    ),
}


adapter = RFSOCAdapter(
    board_num=board_num,
    address=address,
    sequence_params=sequence_params,
)

connected, msg = adapter.open()
print(msg)
if not connected:
    raise SystemExit(f"Could not connect to RFSoC board at {address} - check it is powered on and reachable.")

try:
    adapter.load_sequence(
        SEQUENCE_NAME,
        frequency=frequency,
        exposure_time=exposure_time,
        camera_trig_time=camera_trig_time,
        rf_amplitude=rf_amplitude,
        laser_dur=laser_dur,
        laser_to_rf_delay=laser_to_rf_delay,
        rf_delay=rf_delay,
        **SEQUENCE_PARAMS[SEQUENCE_NAME],
    )

    print(f"Starting '{SEQUENCE_NAME}' sequence - probe the laser/camera TTL lines and RF output now.")
    adapter.start()

    print("Sequence running. Press Ctrl+C to stop.")
    # while True:
    time.sleep(1)
except KeyboardInterrupt:
    print("Stopping...")
finally:
    adapter.stop()
    adapter.close()
    print("Stopped and disconnected.")
