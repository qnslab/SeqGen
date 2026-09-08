"""
Manual hardware test: run the CW ODMR sequence on the RFSoC board so its
laser/camera TTL lines and RF (DDS) output can be checked on an oscilloscope.

This is not an automated test -- it just opens a connection to the board,
loads the ``cw_odmr`` sequence (``seqgen.rfsoc.sequences.cw_esr.ODMRSequence``)
with a small frequency sweep, starts it running, and leaves it running until
you press Ctrl+C, at which point it stops and disconnects cleanly.

Requires:
- The RFSoC control host with the ``RFBuilder``/``RFSOC4x2`` SDK installed
  and importable (this is an external hardware SDK, not a pip dependency of
  SeqGen -- see the ``from RFBuilder import *`` in ``seqgen.rfsoc.rfsoc``).
- The board powered on and reachable at ``address`` below.

Run:
    python examples/rfsoc_cw_odmr_test.py
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

# The cw_odmr sequence drives the MicroBlaster flag/RF outputs directly, so
# ch_defs/sequence_params aren't used to build it, but the adapter still
# expects them for API consistency with the other device adapters.
ch_defs = {
    "laser": 0,
    "rf_x": 1,
    "camera": 2,
}
sequence_params = {}

# --- CW ODMR sequence settings ---------------------------------------------
frequency_list = np.linspace(1e6, 10e6, 51).tolist()  # Hz, RF sweep points
exposure_time = 10e-3      # s, signal (and reference) exposure per point
camera_trig_time = 1e-3    # s, camera trigger/readout time per point
rf_amplitude = 100        # percentage (0-100) of max DDS amplitude
ref_mode = "no_rf"         # reference pulse has RF off

# --- Diagnostic mode: bypass cw_odmr and just hold a static CW tone --------
# Uses the same code path (RFSOCAdapter.constant_frequency_output) as
# labdaemon's scripts/devices/rfsources/test_rfsoc.py, which is known to
# produce RF output at 1 MHz. If this also shows nothing at
# DIAGNOSTIC_FREQUENCY, the issue is a frequency-range/hardware limitation
# rather than a bug in the cw_odmr sequence logic.
DIAGNOSTIC_MODE = False
DIAGNOSTIC_FREQUENCY = 2.90e9  # Hz

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
    if DIAGNOSTIC_MODE:
        print(f"[DIAGNOSTIC] Holding a static CW tone at {DIAGNOSTIC_FREQUENCY / 1e9:.3f} GHz "
              "via constant_frequency_output() - probe the RF output now.")
        adapter.constant_frequency_output(channel="dac_a", frequency=DIAGNOSTIC_FREQUENCY)
    else:
        adapter.load_sequence(
            "cw_odmr",
            exposure_time=exposure_time,
            camera_trig_time=camera_trig_time,
            frequency_list=frequency_list,
            rf_amplitude=rf_amplitude,
            ref_mode=ref_mode,
        )

        print("Starting sequence - probe the laser/camera TTL lines and RF output now.")
        adapter.start()

    print("Sequence running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping...")
finally:
    adapter.stop()
    adapter.close()
    print("Stopped and disconnected.")
