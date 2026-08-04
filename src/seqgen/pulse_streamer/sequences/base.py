from __future__ import annotations

from typing import Any, Sequence, Tuple

import matplotlib.pyplot as plt

PulseSegment = Tuple[int, int]

class PulseStreamerSequence:
    """Base class for Pulse Streamer sequence builders.

    Sequence objects keep a reference to the loaded seqgen adapter so child
    classes can inspect device-specific metadata such as channel names,
    channel indices, and minimum pulse width before programming the hardware.
    """

    device_name = "Pulse Streamer"

    def __init__(self, seqgen, sequence_params: dict[str, float] | None = None):
        self.seqgen = seqgen
        self.ch_defs = dict(getattr(seqgen, "ch_defs", {}) or {})
        self.shortest_pulse_duration = int(getattr(seqgen, "shortest_dur", 1))
        self.channel_sequences: dict[str, list[tuple[int, int]]] = {}
        self.ch_names: list[str] = list(self.ch_defs)
        self.metadata: dict[str, Any] = {
            "device_name": self.device_name,
            "channel_names": list(self.ch_defs),
            "ch_defs": dict(self.ch_defs),
            "shortest_pulse_duration": self.shortest_pulse_duration,
        }


    @property
    def channel_names(self) -> list[str]:
        return list(self.ch_defs)

    def channel_index(self, channel_name: str) -> int:
        return self.ch_defs[channel_name]

    def update_metadata(self, **kwargs):
        self.metadata.update(kwargs)
        return self.metadata

    def set_channel_sequences(self, channel_sequences: dict[str, list[tuple[int, int]]]):
        self.channel_sequences = {
            channel: [(int(duration), int(state)) for duration, state in sequence]
            for channel, sequence in channel_sequences.items()
        }
        self.ch_names = list(self.channel_sequences)
        if hasattr(self.seqgen, "digital_patterns"):
            self.seqgen.digital_patterns = dict(self.channel_sequences)
        if hasattr(self.seqgen, "analog_patterns"):
            self.seqgen.analog_patterns = {}
        return self.channel_sequences

    def describe(self) -> dict[str, Any]:
        return dict(self.metadata)

    def load(self, **kwargs):
        raise NotImplementedError

    def make_segment(self, duration: int, state: int) -> PulseSegment:
        """Create a normalized pulse segment.
        Used to make sure we can check that the segments are valid and normalized before adding them to a sequence.
        """
        # check that duration is a non-negative integer and state is a boolean
        if not isinstance(duration, int) or duration < 0:
            raise ValueError("duration must be a non-negative integer")
        if not isinstance(state, int) or state not in (0, 1):
            raise ValueError("state must be 0 or 1")
        if duration == 0:
            return (0, state)
        if duration < self.shortest_pulse_duration:
            raise ValueError(f"duration must be at least {self.shortest_pulse_duration} ns you provided {duration} ns")

        return int(duration), state

    def repeated_block(self, *segments: PulseSegment, repeats: int = 1) -> list[PulseSegment]:
        """Return a repeated block of segments.
        Mainly used to make sure we can check that the segments are valid and normalized before repeating them.
        """

        block = [self.make_segment(duration, state) for duration, state in segments]

        if repeats <= 0:
            return []
        return block * repeats


    def get_total_block_duration(self, block: list[PulseSegment]) -> int:
        """Return the total duration of a block.
        """
        return sum(duration for duration, _ in block)

    def _shift_first_segment(self, sequence: list[tuple[int, int]], shift_ns: int) -> bool:
        if not sequence:
            return False

        shift_ns = int(round(shift_ns))
        if shift_ns <= 0:
            return True

        first_duration, first_state = sequence[0]
        if first_duration <= shift_ns:
            return False

        sequence[0] = (first_duration - shift_ns, first_state)
        return True


    def plot_sequences(
        self,
        sequences: Sequence[Sequence[PulseSegment]] | None = None,
        channel_names: Sequence[str] | None = None,
        title: str | None = None,
        *,
        show: bool = True,
        save_path: str | None = None,
    ) -> None:
        """Plot duration/state sequences using the same filled style as PulseKernel."""

        if sequences is None:
            sequences = list(self.channel_sequences.values())
        if channel_names is None:
            channel_names = list(self.channel_sequences) if self.channel_sequences else list(self.ch_names)

        plt.figure(figsize=(10, 6))
        colormap = plt.get_cmap("tab20")
        fill_colors = [colormap(i) for i in range(1, 20, 2)]
        line_colors = [
            "tab:blue",
            "tab:orange",
            "tab:green",
            "tab:red",
            "tab:purple",
            "tab:brown",
            "tab:pink",
            "tab:gray",
            "tab:olive",
            "tab:cyan",
        ]

        plt_offset = 1.1
        plt_height = 0.9
        baselines = [index * plt_offset for index in range(len(sequences))]
        total_time = max((sum(duration for duration, _ in seq) for seq in sequences), default=0)

        for index, seq in enumerate(sequences):
            baseline = baselines[index]
            line_color = line_colors[index % len(line_colors)]
            fill_color = fill_colors[index % len(fill_colors)]
            time = 0
            for duration, state in seq:
                if state:
                    top = baseline + plt_height
                    plt.plot([time, time + duration], [top, top], color=line_color)
                    plt.fill_between([time, time + duration], baseline, top, color=fill_color)
                    plt.plot([time, time], [baseline, top], color=line_color)
                    plt.plot([time + duration, time + duration], [baseline, top], color=line_color)
                else:
                    plt.plot([time, time + duration], [baseline, baseline], color=line_color)
                time += duration

        plt.yticks([baseline + plt_height / 2 for baseline in baselines], list(channel_names))
        plt.ylim(-0.2, (baselines[-1] + plt_height + 0.2) if baselines else 1.0)
        plt.xlim(0, total_time * 1.02 if total_time else 1.0)
        plt.xlabel("Time (ns)")
        if title is not None:
            plt.title(title)
        if save_path:
            plt.savefig(save_path, bbox_inches="tight", dpi=150)
        plt.tight_layout()
        if show:
            plt.show()