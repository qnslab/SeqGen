"""PulseBlaster plugin package.

Submodules:
- pulseblaster: hardware adapter class
- camera_sequences: device-specific sequence builders

Imports are intentionally light to avoid heavy dependencies during partial imports.
"""

__all__ = ["pulseblaster", "camera_sequences"]

from .pulseblaster import PulseBlasterAdapter