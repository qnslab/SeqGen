"""Pulse Streamer 8/2 plugin package.

This package provides a seqgen-compatible adapter for the Swabian
Instruments Pulse Streamer 8/2 -- a synchronous pattern generator with
8 digital outputs and 2 analog outputs. The adapter keeps the same
high-level programming API as the PulseBlaster/Keysight adapters
(``start_programming``/``add_kernel``/``add_instruction``/...) so existing
sequence builders (``camera_sequences``) can be reused unchanged, while
adding native support for mixed digital + analog channels via
``seqgen.ChannelType``.
"""

from .pulse_streamer import PulseStreamerAdapter

__all__ = ["PulseStreamerAdapter"]
