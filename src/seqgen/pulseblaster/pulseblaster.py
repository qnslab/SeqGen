from __future__ import annotations

import logging

import numpy as np

try:
    from loguru import logger
except Exception:
    logger = logging.getLogger(__name__)

try:
    from . import spinapi as pb
    from .spinapi import *
except Exception as e:
    pb = None


class PulseBlasterAdapter:
    connected: bool = False
    board_num: str
    ch_defs: dict[str, str]
    sequence_params: dict[str, float]

    def __init__(self, board_num: int = 0, ch_defs: dict[str, str] = None, sequence_params: dict[str, float] = None, device_id: str | None = None, *args, **kwargs):
        ch_defs = ch_defs or {}
        sequence_params = sequence_params or {}
        self.board_num = board_num
        self.ch_defs = ch_defs
        self.sequence_params = sequence_params
        self.shortest_dur = int(12)
        self.device_id = device_id
        self.loaded_sequence = None

    def connect(self):
        # for interacting with labdaemon
        self.open()

    def open(self) -> tuple[bool, str]:
        if pb is None:
            return False, "SpinAPI not available: install device adapter dependencies"
        if pb.pb_count_boards() < 0:
            logger.error("No Pulseblaster boards found")
            self.connected = False
            return False, "Error: No Pulseblaster boards found"
        try:
            pb.pb_select_board(int(self.board_num))
            pb.pb_init()
            pb.pb_core_clock(500)
            logger.info("Pulseblaster opened, status: {}", pb.pb_read_status())
            self.connected = True
            return True, "Pulseblaster opened"
        except Exception:
            logger.exception("Error opening Pulseblaster")
            return False, "Error opening Pulseblaster"

    def disconnect(self):
        self.close()

    def close(self):
        if self.connected and pb is not None:
            self.stop()
            pb.pb_close()
        self.connected = False

    def is_connected(self) -> bool:
        try:
            return False if pb is None or pb.pb_count_boards() < 0 else True
        except:
            return False

    def start_sequence(self):
        self.start()

    def start(self):
        if pb is not None:
            logger.info("Starting Pulseblaster sequence")
            pb.pb_start()

    def reset(self):
        if pb is not None:
            logger.info("Resetting Pulseblaster sequence")
            pb.pb_reset()

    def stop(self):
        if pb is not None:
            logger.info("Stopping Pulseblaster sequence")
            pb.pb_stop()

    def is_finished(self):
        # pb_read_status() returns a status dict (stopped/reset/running/waiting),
        # so it must never be compared directly to an int (that comparison is
        # always False, which meant this method never reported completion).
        if pb is None:
            return True
        status = pb.pb_read_status()
        return bool(status.get("stopped"))

    def get_status(self):
        return pb.pb_read_status() if pb is not None else {}

    def get_available_sequences(self):
        from seqgen.pulseblaster.sequences.cw_esr import ODMRSequence
        from seqgen.pulseblaster.sequences.p_esr import PODMRSequence
        from seqgen.pulseblaster.sequences.rabi import RabiSequence
        from seqgen.pulseblaster.sequences.ramsey import RamseySequence
        from seqgen.pulseblaster.sequences.spinlocking import SpinlockSequence
        # from seqgen.pulseblaster.sequences.spin_echo import SpinEchoSequence
        # from seqgen.pulseblaster.sequences.t1 import T1Sequence
        
        return {
            "mock_odmr": ODMRSequence,
            "cw_odmr": ODMRSequence,
            "pulsed_odmr": PODMRSequence,
            "rabi": RabiSequence,
            "ramsey": RamseySequence,
            "spinlocking": SpinlockSequence,
            # "t1": T1Sequence,
        }

    def check_time_list(self, time_list):
        for i, t in enumerate(time_list):
            if t < self.shortest_dur:
                logger.warning(
                    "RF pulse duration at index {} is below the shortest duration ({} ns). Rounding up to {} ns.",
                    i,
                    t,
                    self.shortest_dur,
                )
                if t == 0:
                    time_list[i] = 0
                else:
                    time_list[i] = self.shortest_dur
        return time_list

    def load_sequence(self, seq_name, **seq_kwargs):
        logger.info("Loading {} sequence", seq_name)
        # to remove capitalization issues, we can convert the sequence name to lowercase
        seq_name = seq_name.lower()
        sequences = self.get_available_sequences()
        sequence_spec = sequences[seq_name]
        if isinstance(sequence_spec, type):
            loaded_sequence = sequence_spec(self, self.sequence_params)
            results = loaded_sequence.load(**seq_kwargs)
            self.loaded_sequence = loaded_sequence
        else:
            self.loaded_sequence = None
            results = sequence_spec(self, self.sequence_params, **seq_kwargs)
        logger.info("Loaded {} sequence", seq_name)
        # check if the loaded sequence had to round any pulse durations

        return results

    def get_loaded_sequence_info(self):
        if self.loaded_sequence is None:
            return {}
        if hasattr(self.loaded_sequence, "describe"):
            return self.loaded_sequence.describe()
        return {}

    def start_programming(self):
        if pb is not None:
            pb.pb_start_programming(pb.PULSE_PROGRAM)

    def stop_programming(self):
        if pb is not None:
            pb.pb_stop_programming()

    def inst_pbonly(self, chs, opcode, data, duration):
        if pb is not None:
            return pb.pb_inst_pbonly(chs, opcode, data, duration)

    def get_chs_cmd_bits(self, ch_defs, ch_list):
        command_num = 0
        for ch in ch_list:
            command_num = command_num + int(ch_defs[ch], 2)
        return command_num

    def end_sequence(self, dur):
        if pb is not None:
            pb.pb_inst_pbonly(0, pb.Inst.STOP, 0, dur)

    def add_instruction(self, active_chs, dur=0, delay=None, loop=None, num=0, inst=None, const_chs=(), **kwargs):
        inst_out = None
        if len(const_chs) > 0:
            active_chs.append(const_chs[0])
        if dur < self.shortest_dur:
            old_dur = dur
            if dur == 0:
                dur = 0
            else:
                dur = self.shortest_dur
            logger.error("Pulse with channels {} rounded from {} ns to {} ns.", active_chs, old_dur, dur)
        if dur >= self.shortest_dur and pb is not None:
            dur = np.round(dur / 2) * 2
            ctl = self.get_chs_cmd_bits(self.ch_defs, active_chs)
            if loop == "start":
                inst_out = self.inst_pbonly(ctl, pb.Inst.LOOP, num, dur)
            elif loop == "end":
                inst_out = self.inst_pbonly(ctl, pb.Inst.END_LOOP, inst, dur)
            else:
                inst_out = self.inst_pbonly(ctl, pb.Inst.CONTINUE, 0, dur)
        else:
            logger.error("Pulse duration too short, not adding pulse.")
            logger.error("Did not add {} for {} ns.", active_chs, dur)
        return inst_out

    def add_kernel(self, pulse_kernel, num_loop, const_chs=[], **kwargs):
        pulse_kernel.convert_to_instructions(const_chs=const_chs)
        insts = pulse_kernel.insts
        n_insts = len(insts)
        if n_insts == 1:
            self.add_instruction(**insts[0])
            return
        # NOTE: must use the loop position (enumerate), not insts.index(inst) -
        # value-based .index() returns the FIRST matching instruction whenever
        # two segments share identical active_chs/dur/levels (e.g. two pulses
        # on the same channel with the same duration, as in Ramsey's/
        # Spinlock's signal kernels). That previously caused the true last
        # instruction to be misidentified as a middle one, so the "loop end"
        # marker (closing the PulseBlaster hardware LOOP) was never emitted
        # for that kernel.
        loop_inst = None
        for idx, inst in enumerate(insts):
            if idx == 0:
                loop_inst = self.add_instruction(loop="start", num=num_loop, **inst)
            elif idx == n_insts - 1:
                self.add_instruction(loop="end", inst=loop_inst, **inst)
            else:
                self.add_instruction(**inst)
        return
