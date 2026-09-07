from __future__ import annotations

import logging

import numpy as np

try:
    from loguru import logger
except Exception:
    logger = logging.getLogger(__name__)


from RFBuilder import *


# Define the TTL lines used for controlling the MicroBlaster and other functions
RUN = "SOFTWARE0"
TRIGGER = "SOFTWARE1"
RSTN = "SOFTWARE2"
MB_OUT0 = "SYZYGY_OUT7"
MB_OUT1 = "SYZYGY_OUT6"
MB_OUT2 = "SYZYGY_OUT5"
MB_OUT3 = "SYZYGY_OUT4"
TTL_IN0 = "SYZYGY_IN0"
TTL_IN1 = "SYZYGY_IN1"


class RFSOCAdapter:
    connected: bool = False
    board_num: str
    ch_defs: dict[str, str]
    sequence_params: dict[str, float]

    def __init__(self, 
                 board_num: int = 0,
                 address: str = "169.254.127.84",
                 ch_defs: dict[str, str] = None, 
                 sequence_params: dict[str, float] = None, 
                 device_id: str | None = None, 
                 *args, 
                 **kwargs):
        ch_defs = ch_defs or {}
        sequence_params = sequence_params or {}
        self.board_num = board_num
        self.address = address
        self.ch_defs = ch_defs
        self.sequence_params = sequence_params
        self.shortest_dur = int(4)
        self.device_id = device_id
        self.loaded_sequence = None

    def connect(self):
        # for interacting with labdaemon
        self.open()

    def open(self) -> tuple[bool, str]:
        try:
            self.board = RFSOC4x2()

            rfbuilder = RFBuilder(self.board,self.address,8080)

            self.ub = MicroBlaster()
            rfbuilder.add(self.ub)

            dacs = rfbuilder.get_dacs()
            adcs = rfbuilder.get_adcs()

            rfbuilder.connect(self.ub,dacs[0])

            rfbuilder.ttl.reset()

            rfbuilder.ttl.connect(RUN,"MB_RUN") #allows a user to trigger 
            rfbuilder.ttl.connect(RSTN,"MB_RSTN") #allows a user to reset the MicroBlaster using software
            rfbuilder.ttl.connect("MB_FLAG0",MB_OUT0)
            rfbuilder.ttl.connect("MB_FLAG1",MB_OUT1)
            rfbuilder.ttl.connect("MB_FLAG2",MB_OUT2)
            rfbuilder.ttl.connect("MB_FLAG3",MB_OUT3)

            #below ANDs the TTL_IN0 (an external connection) signal and TRIGGER (a software controlled pin) signal, this is the connected to the MicroBlaster trigger line 
            rfbuilder.ttl.connect([TTL_IN0,TRIGGER],"MB_TRIG")
            rfbuilder.ttl.set_operation("MB_TRIG","AND") 

            #Initiate a reset, this ensures if the MicroBlaster is in an infinite loop it will break out, allowing reprogramming. Additionally ensure run and trig are low
            rfbuilder.ttl.update_state(RSTN,0)
            rfbuilder.ttl.update_state(RSTN,1)
            rfbuilder.ttl.update_state(RUN,0)
            rfbuilder.ttl.update_state(TRIGGER,0)

        except Exception:
            logger.exception("Error opening RFSoC board")
            return False, "Error opening RFSoC board"


    def disconnect(self):
        self.close()

    def close(self):
        if self.connected:
            self.board.close()
        self.connected = False

    def is_connected(self) -> bool:
        try:
            return self.board.is_connected()
        except:
            return False

    def start(self):
        logger.info("Starting RFSoC sequence")
        self.rfbuilder.ttl.update_state(RUN, 1)

    def reset(self):
        logger.info("Resetting RFSoC sequence")
        # NOT SURE WHAT IS NEEDED HERE
        # self.rfbuilder.ttl.update_state(RSTN, 0)

    def stop(self):
        logger.info("Stopping RFSoC sequence")
        self.rfbuilder.ttl.update_state(RUN, 0)

    # def is_finished(self):
    #     return self.board.is_finished()

    # def get_status(self):
    #     return self.board.get_status() if self.connected else {}

    def get_available_sequences(self):
        from seqgen.rfsoc.sequences.cw_esr import ODMRSequence
        return {
            "cw_esr": ODMRSequence,
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
    
if __name__ == "__main__":
    # make a mock RFSoC adapter for testing loading 
    rfsoc = RFSOCAdapter()
    print("MOCK RFSoC Adapter created!")
    rfsoc.connect()

    