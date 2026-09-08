from __future__ import annotations

import logging

import numpy as np

try:
    from loguru import logger
except Exception:
    logger = logging.getLogger(__name__)


from RFBuilder import *


# Define the TTL lines used for controlling the MicroBlaster and other functions
RUN     = "SOFTWARE0"
TRIGGER = "SOFTWARE1"
RSTN    = "SOFTWARE2"
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

            self.rfbuilder = RFBuilder(self.board,self.address,8080)

            self.ub = MicroBlaster()
            self.rfbuilder.add(self.ub)

            self.dacs = self.rfbuilder.get_dacs()
            self.adcs = self.rfbuilder.get_adcs()

            self.rfbuilder.connect(self.ub,self.dacs[0])

            self.rfbuilder.ttl.reset()

            self.rfbuilder.ttl.connect(RUN, "MB_RUN") #allows a user to trigger 
            self.rfbuilder.ttl.connect(RSTN, "MB_RSTN") #allows a user to reset the MicroBlaster using software
            self.rfbuilder.ttl.connect("MB_FLAG0", MB_OUT0)
            self.rfbuilder.ttl.connect("MB_FLAG1", MB_OUT1)
            self.rfbuilder.ttl.connect("MB_FLAG2", MB_OUT2)
            self.rfbuilder.ttl.connect("MB_FLAG3", MB_OUT3)

            #below ANDs the TTL_IN0 (an external connection) signal and TRIGGER (a software controlled pin) signal, this is the connected to the MicroBlaster trigger line 
            # self.rfbuilder.ttl.connect([TTL_IN0,TRIGGER], "MB_TRIG")
            # self.rfbuilder.ttl.set_operation("MB_TRIG","AND") 
            self.rfbuilder.ttl.connect(TRIGGER, "MB_TRIG")
                       

            # A freshly created MicroBlaster block has no instructions loaded.
            # RFBuilder.update() validates/pushes any "dirty" block, and the
            # MicroBlaster requires its program to end with a STOP instruction,
            # so prime it with a harmless all-zero halt before the first update()
            # (also puts the DDS/TTL flags into a known, quiescent state).
            self.ub.end_program(0, 0, 0, 0, self.shortest_dur)

            # Push the block/connection setup to the board before issuing any
            # control-pin state changes, otherwise the TTL wiring above is never
            # actually transmitted.
            self.rfbuilder.update()

            #Initiate a reset, this ensures if the MicroBlaster is in an infinite loop it will break out, allowing reprogramming. Additionally ensure run and trig are low
            self.rfbuilder.ttl.update_state(RSTN, 0)
            self.rfbuilder.ttl.update_state(RSTN, 1)
            self.rfbuilder.ttl.update_state(RUN, 0)
            # self.rfbuilder.ttl.update_state(TRIGGER, 1)
            #enable the sinc filter to minimise rolloff from DAC
            self.rfbuilder.sinc_filters = 1

            self.connected = True

        except Exception:
            logger.exception("Error opening RFSoC board")
            self.connected = False
            return False, "Error opening RFSoC board"

        return True, f"Connected to RFSoC board at {self.address}"


    def disconnect(self):
        # turn off the running sequence before closing the connection
        self.stop()
        self.close()

    def close(self):
        # The RFSoC link is a stateless HTTP API (no persistent socket to tear
        # down), so "closing" just means stopping the running sequence/output
        # and marking ourselves as disconnected.
        if self.connected:
            try:
                self.rfbuilder.ttl.update_state(RUN, 0)
            except Exception:
                logger.exception("Error stopping RFSoC output during disconnect")
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def start(self):
        logger.info("Starting RFSoC sequence")
        # self.rfbuilder.ttl.update_state(RSTN, 0)
        self.rfbuilder.ttl.update_state(RSTN, 1)
        self.rfbuilder.ttl.update_state(RUN, 1)

        # self.rfbuilder.ttl.update_state(RSTN, 2)
        # self.rfbuilder.ttl.update_state(RUN, 2)

    def reset(self):
        logger.info("Resetting RFSoC sequence")
        # NOT SURE WHAT IS NEEDED HERE
        # self.rfbuilder.ttl.update_state(RSTN, 0)

    def stop(self):
        logger.info("Stopping RFSoC sequence")
        self.rfbuilder.ttl.update_state(RSTN, 0)
        self.rfbuilder.ttl.update_state(RUN, 0)

    # def is_finished(self):
    #     return self.board.is_finished()

    # def get_status(self):
    #     return self.board.get_status() if self.connected else {}

    def get_available_sequences(self):
        from seqgen.rfsoc.sequences.cw_esr import ODMRSequence
        return {
            "cw_odmr": ODMRSequence,
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

    def static_ttl_output(self, channel: str, state: bool):
        if not self.connected:
            raise RuntimeError("RFSoC is not connected")
        # Check if works
        if state:
            self.rfbuilder.ttl.update_state(channel, 1)
        else:
            self.rfbuilder.ttl.update_state(channel, 0)

    def constant_frequency_output(self, channel: str, frequency: float, phase: float = 0.0, amplitude: int | None = None):
        """Program the MicroBlaster DDS to hold a constant (CW) frequency output.

        Loads a single instruction that sets the DDS frequency/phase/amplitude
        then halts (mirrors the Monash-RFSoC ``end_program`` usage for static
        output), and re-arms/triggers the MicroBlaster so the new settings take
        effect immediately.

        Note: only a single DDS output (dacs[0]) is currently wired up in
        ``open()``, so ``channel`` is accepted for API symmetry with
        ``static_ttl_output`` but is not yet used to select between outputs.
        """
        if not self.connected:
            raise RuntimeError("RFSoC is not connected")

        amp = amplitude if amplitude is not None else self.ub.maxAmp

        # Clear any previously loaded sequence and program the static output.
        self.ub.instructionList = []
        self.ub.numInstructions = 0
        self.ub.labelDict = {}
        self.ub.end_program(0, frequency, phase, amp, self.shortest_dur, resync=1)
        self.rfbuilder.update()

        self.start()

    # functions that are used in other signal generators, but not used in the RFSoC adapter. These are here for compatibility with the PulseBlasterAdapter
    def reset_sweep(self):
        # not needed as the RFSoC is reset as the sequence is reset
        logger.warning("RFSoC does not support resetting a sweep, use reset() instead")
        return

    def start_sweep(self):
        # not needed as the RFSoC starts the sequence automatically when triggered
        logger.warning("RFSoC does not support starting a sweep, use start() instead")
        return

if __name__ == "__main__":
    # make a mock RFSoC adapter for testing loading 
    rfsoc = RFSOCAdapter()
    print("MOCK RFSoC Adapter created!")
    rfsoc.connect()

    