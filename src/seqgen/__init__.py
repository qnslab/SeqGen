"""
SeqGen: A framework for defining abstract pulse kernels and converting them into concrete device-specific instruction sequences.

Public API:
- PulseKernel: core abstraction for building pulse kernels
- PulseSeries: legacy series-based abstraction
- sequence_plotting: helpers for visualizing kernels and instructions
- pulseblaster: example device adapter implementing SpinCore PulseBlaster programming
"""

from .pulse_kernel import PulseKernel

# Note: device adapters live outside core `seqgen` (e.g., `plugins.pulseblaster`).
# Avoid importing adapters here to prevent circular import during plugin usage.
