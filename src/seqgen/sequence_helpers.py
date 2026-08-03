"""Helpers for building and plotting simple duration/state pulse sequences.

These utilities keep Pulse Streamer example scripts readable by hiding the
repetitive list manipulation used to assemble channel timelines.
"""

from __future__ import annotations

from typing import Iterable, MutableSequence, Sequence, Tuple

import matplotlib.pyplot as plt

PulseSegment = Tuple[int, bool]


def make_segment(duration: int, state: int, smallest_pulse_duration: int = 1) -> PulseSegment:
    """Create a normalized pulse segment."""
    # check that duration is a non-negative integer and state is a boolean
    if not isinstance(duration, int) or duration < 0:
        raise ValueError("duration must be a non-negative integer")
    if not isinstance(state, int) or state not in (0, 1):
        raise ValueError("state must be 0 or 1")
    if duration == 0:
        return (0, state)
    if duration < smallest_pulse_duration:
        raise ValueError(f"duration must be at least {smallest_pulse_duration} ns you provided {duration} ns")

    return int(duration), state


def repeated_block(*segments: PulseSegment, repeats: int = 1, smallest_pulse_duration: int = 1) -> list[PulseSegment]:
    """Return a repeated block of segments."""

    block = [make_segment(duration, state, smallest_pulse_duration) for duration, state in segments]

    if repeats <= 0:
        return []
    return block * repeats


def get_total_block_duration(block: dict[str, dict[str, list[int]]]) -> int:
    """Return the total duration of a block dictionary.
    All channels must have the same total duration, otherwise a ValueError is raised.
    so we can just return the total duration of the first channel.
    """
    max_duration = 0
    channel_commands = block[0]
    for command in channel_commands:
        max_duration += command[0]
    
    return max_duration

def extend_sequence(sequence: MutableSequence[PulseSegment], *segments: Iterable[PulseSegment]) -> MutableSequence[PulseSegment]:
    """Append one or more segment iterables to an existing sequence."""

    for block in segments:
        sequence.extend(make_segment(duration, state) for duration, state in block)
    return sequence


def prepend_idle(sequence: MutableSequence[PulseSegment], duration: int, state: bool = False) -> MutableSequence[PulseSegment]:
    """Insert a leading idle or initialization segment."""

    duration = int(duration)
    if duration > 0:
        sequence.insert(0, make_segment(duration, state))
    return sequence


def shift_first_segment(sequence: MutableSequence[PulseSegment], delta: int) -> MutableSequence[PulseSegment]:
    """Adjust the duration of the first segment by delta."""

    if not sequence:
        return sequence
    duration, state = sequence[0]
    new_duration = int(duration) + int(delta)
    if new_duration < 0:
        raise ValueError("first segment duration cannot become negative")
    sequence[0] = (new_duration, bool(state))
    return sequence


def plot_sequences(
    sequences: Sequence[Sequence[PulseSegment]],
    channel_names: Sequence[str],
    title: str | None = None,
    *,
    show: bool = True,
    save_path: str | None = None,
) -> None:
    """Plot duration/state sequences using the same filled style as PulseKernel."""

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
