"""Keysight AWG plugin package.

This package provides a seqgen-compatible adapter for Keysight AWGs.
The adapter keeps the same high-level programming API as the PulseBlaster
example so existing sequence builders can be reused.
"""

from .keysight9336a import Keysight9336A

__all__ = ["Keysight9336A"]