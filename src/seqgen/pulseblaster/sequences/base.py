from __future__ import annotations

from typing import Any


class PulseBlasterSequence:
    """Base class for PulseBlaster sequence builders.

    Mirrors the naming/metadata conventions of
    ``seqgen.pulse_streamer.sequences.base.PulseStreamerSequence`` (
    ``sequence_name``/``ch_names`` class attributes, a ``metadata`` dict,
    ``update_metadata``/``describe``, and a ``load(**kwargs)`` entry point
    that returns ``self``) while keeping the PulseBlaster-specific
    programming model intact: sequences are built from ``PulseKernel``
    objects and streamed to hardware via the adapter's
    ``add_kernel``/``add_instruction`` calls and hardware LOOP/END_LOOP
    opcodes, rather than the plain duration/state channel sequences used by
    the Pulse Streamer.
    """

    device_name = "PulseBlaster"
    sequence_name = "Sequence"
    ch_names: list[str] = []

    def __init__(self, seqgen, sequence_params: dict[str, float] | None = None):
        self.seqgen = seqgen
        self.sequence_params = dict(sequence_params or getattr(seqgen, "sequence_params", {}) or {})
        self.ch_defs = dict(getattr(seqgen, "ch_defs", {}) or {})
        self.shortest_pulse_duration = int(getattr(seqgen, "shortest_dur", 12))
        self.metadata: dict[str, Any] = {
            "device_name": self.device_name,
            "sequence_name": self.sequence_name,
            "channel_names": list(self.ch_defs),
            "ch_defs": dict(self.ch_defs),
            "shortest_pulse_duration": self.shortest_pulse_duration,
        }

    @property
    def channel_names(self) -> list[str]:
        return list(self.ch_defs)

    def update_metadata(self, **kwargs):
        self.metadata.update(kwargs)
        return self.metadata

    def describe(self) -> dict[str, Any]:
        return dict(self.metadata)

    def load(self, **kwargs):
        raise NotImplementedError
