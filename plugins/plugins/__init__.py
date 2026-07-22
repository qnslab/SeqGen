"""SeqGen internal plugins package.

Device adapters (e.g., PulseBlaster, Keysight AWG, Pulse Streamer 8/2) are
available under subpackages like ``plugins.pulseblaster``,
``plugins.keysight_awg``, and ``plugins.pulse_streamer``. Imports are
intentionally minimal here to avoid heavy dependencies during partial
imports.
"""