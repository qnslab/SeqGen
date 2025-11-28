from __future__ import annotations

import numpy as np
from loguru import logger

try:
    from . import spinapi as pb
    from .spinapi import *
except Exception as e:
    pb = None


class PulseBlaster:
    connected: bool = False
    board_num: str
    ch_defs: dict[str, str]
    sequence_params: dict[str, float]

    def __init__(self, board_num: str, ch_defs: dict[str, str], sequence_params: dict[str, float]):
        self.board_num = board_num
        self.ch_defs = ch_defs
        self.sequence_params = sequence_params
        self.shortest_dur = int(12)

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

    def start(self):
        if pb is not None:
            pb.pb_start()

    def reset(self):
        if pb is not None:
            pb.pb_reset()

    def stop(self):
        if pb is not None:
            pb.pb_stop()

    def is_finished(self):
        return pb.pb_read_status() == 0 if pb is not None else True

    def get_status(self):
        return pb.pb_read_status() if pb is not None else {}

    def get_available_sequences(self):
        from camera_sequences.cw_esr import seq_cw_esr
        from camera_sequences.p_esr import seq_p_esr
        from camera_sequences.rabi import seq_rabi
        from camera_sequences.ramsey import seq_ramsey
        from camera_sequences.spin_echo import seq_spin_echo
        from camera_sequences.t1 import seq_t1
        return {
            "MockSGAndorCWESR": seq_cw_esr,
            "SGAndorCWESR": seq_cw_esr,
            "SGAndorPESR": seq_p_esr,
            "SGAndorRabi": seq_rabi,
            "SGAndorT1": seq_t1,
            "SGAndorRamsey": seq_ramsey,
            "SGAndorSpinEcho": seq_spin_echo,
        }

    def load_seq(self, seq_name, **seq_kwargs):
        logger.info("Loading {} sequence", seq_name)
        sequences = self.get_available_sequences()
        sequences[seq_name](self, self.sequence_params, **seq_kwargs)
        logger.info("Loaded {} sequence", seq_name)

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
        for inst in pulse_kernel.insts:
            if len(pulse_kernel.insts) == 1:
                self.add_instruction(**inst)
                return
            if pulse_kernel.insts.index(inst) == 0:
                loop_inst = self.add_instruction(loop="start", num=num_loop, **inst)
            elif pulse_kernel.insts.index(inst) == len(pulse_kernel.insts) - 1:
                self.add_instruction(loop="end", inst=loop_inst, **inst)
            else:
                self.add_instruction(**inst)
        return
