from __future__ import annotations

import logging

import numpy as np

from typing import Any, Dict, List

try:
    from loguru import logger
except Exception:
    logger = logging.getLogger(__name__)

# from seqgen.pulse_kernel import PulseKernel  # type: ignore

try:
    from . import spinapi as pb
    from .spinapi import *
except Exception as e:
    pb = None

class MockPulseBlaster:
    """Minimal PulseBlaster mock for building/holding instructions.

    Implements only the APIs used by p_esr.seq_p_esr.
    """

    def __init__(self, ch_defs: Dict[str, str], sequence_params: Dict[str, float]):
        self.ch_defs = ch_defs
        self.sequence_params = sequence_params
        self.insts: List[Dict[str, Any]] = []
        self._programming = False
        self.shortest_dur = 12

    # Programming lifecycle
    def start_programming(self):
        self._programging = True

    def stop_programming(self):
        self._programming = False

    # Instruction helpers (no hardware calls)
    def add_instruction(self, active_chs, dur=0, delay=None, loop=None, num=0, inst=None, const_chs=(), **kwargs):
        self.insts.append(
            {
                "active_chs": list(active_chs) if active_chs else [],
                "dur": int(dur),
                "const_chs": list(const_chs) if const_chs else [],
                "loop": loop,
                "num": int(num) if isinstance(num, (int, float)) else num,
                "loop_anchor": inst,
            }
        )
        # Return a dummy anchor for loop start
        return len(self.insts) - 1 if loop == "start" else None

    def end_sequence(self, dur):
        # Mark sequence end with a STOP-like sentinel
        self.insts.append({"active_chs": [], "dur": int(dur), "const_chs": [], "stop": True})

    def add_kernel(self, pulse_kernel: PulseKernel, num_loop: int, const_chs=None, **kwargs):
        if const_chs is None:
            const_chs = []
        pulse_kernel.convert_to_instructions(const_chs=const_chs)
        for _ in range(int(num_loop)):
            for inst in pulse_kernel.insts:
                self.add_instruction(inst["active_chs"], dur=inst["dur"], const_chs=inst.get("const_chs", []))