"""
Testing a camera rabi sequence with the Pulse Streamer. 

"""

import numpy as np
from seqgen.pulse_kernel import PulseKernel
from loguru import logger

from pulsestreamer import PulseStreamer
from pulsestreamer import TriggerStart, TriggerRearm
from pulsestreamer import Sequence, OutputState

ip_or_serial='169.254.8.2' # edit this line to connect to a specific Pulse Streamer via its IP address, hostname or serial number

pulser = PulseStreamer(ip_or_serial)

#define channel names 
ch_laser     = 0 # output channel 0
ch_camera    = 1 # output channel 1
ch_x         = 2 # output channel 2
ch_y         = 3 # output channel 3

ch_analog_x   = 0 # analog channel 0
ch_analog_y   = 1 # analog channel 1

laser_pulse_time = 1000 #ns
mw_x_delay = laser_pulse_time + 200 #ns
camera_on_time = 1e6
camera_readout_time = 1e6


#define digital levels
HIGH=1
LOW=0


# def seq_rabi(
#     seqgen,
#     sequence_params: dict[str, float],
#     sweep_x: np.ndarray = None,
#     laser_dur: float = 3e-6,
#     laser_delay: float = 0,
#     laser_to_rf_delay: float = 200e-9,
#     rf_delay: float = 0,
#     ref_mode: str = "no_rf",
#     exp_t: float = 30e-3,
#     avg_per_point: int = 1,
#     camera_trig_time: float = 0,
#     **kwargs,
# ):

laser_dur = 1e-6
laser_delay = 300e-9
laser_to_rf_delay = 50e-9
rf_delay = 50e-9
ref_mode = "no_rf"
exp_t = 30e-3
avg_per_point = 1
camera_trig_time = 1e-3

ch_defs = {
    "laser": 0,
    "rf_x": 2,
    "rf_-x": 3,
    "rf_y": 4,
    "rf_-y": 5,
    "rf_trig": 6,
    "camera": 1,
    "rf2_trig": 7,
}

sweep_x = np.linspace(20, 500, 11) * 1e-9
  
if ref_mode == ("" or None):
    b_ref = False
    logger.info("Setting up Rabi sequence with no reference")
else:
    b_ref = True
    logger.info("Setting up Rabi sequence with {} as a reference", ref_mode)

# convert times to ns assuming the user inputs in s
laser_dur = int(laser_dur * 1e9)
laser_delay = int(laser_delay * 1e9)
laser_to_rf_delay = int(laser_to_rf_delay * 1e9)
rf_delay = int(rf_delay * 1e9)
exp_t = int(exp_t * 1e9)
trigger_time = int(camera_trig_time * 1e9)

time_list = 1e9 * sweep_x
time_list = [int(i) for i in time_list.tolist()]

# Program the kernel pulses

pk_sig = PulseKernel(ch_defs)
pk_sig.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
pk_sig.append_delay(laser_to_rf_delay)
pk_sig.append_pulse(["rf_x"], 1, ch_delay=rf_delay, var_dur=True)
# Finish the kernel and shift the channel delays to account for the variable duration of the RF pulse
pk_sig.finish_kernel()
# pk_sig.shift_ch_delays()
# pk_sig.wrap_pulses()

pk_ref = PulseKernel(ch_defs)
pk_ref.add_pulse(["laser"], 0, laser_dur, ch_delay=laser_delay)
pk_ref.append_delay(laser_to_rf_delay)
pk_ref.append_delay(1, var_dur=True)
pk_ref.finish_kernel()
# pk_ref.shift_ch_delays()
# pk_ref.wrap_pulses()


# Set up the number of loops for the sequence based on the total experiment time and the base time of the kernel

# Define the shortest time of the kernel, which is the end time of the signal kernel minus the variable duration of the RF pulse (which is 1 ns in this case)
base_time = pk_sig.get_end_time() - 1

# define the number of loops for the sequence based on the total experiment time and the base time of the kernel
num_loops = int(exp_t / base_time)
trigger_loops = int(1.05*trigger_time / base_time) # 1.05 factor is to make sure that the trigger time is long enough to cover the entire experiment time, with some margin

# print out the parameters for the sequence
logger.info(
  "Programming Rabi sequence with the following parameters:" +
  f"\nLaser duration: {laser_dur} ns" +
  f"\nFirst RF pulse duration: {time_list[0]} ns" +
  f"\nLast RF pulse duration: {time_list[-1]} ns" +
  f"\nLaser delay: {laser_delay} ns" +
  f"\nRF delay: {rf_delay} ns" +
  f"\nReference mode: {ref_mode}" +
  f"\nBase time: {base_time} ns" +
  f"\nCamera exposure time: {exp_t * 1e-6} ms" +
  f"\nNumber of loops: {num_loops}" +
  f"\nCamera trigger time: {trigger_time * 1e-6} ms" +
  f"\nNumber of trigger loops: {trigger_loops}"
)

# print the kernel dictionary to check the pulses and delays

for pulse in pk_sig.kernel["laser"]:
  print(f"{pulse}")

# print(pk_sig.kernel["laser"])
  # we need to define each change in state as a tuple of the 
  # time and state in a list. 
for idx, pulse in enumerate(pk_sig.kernel["laser"]["start"]):
  print(f"Laser pulse {idx}: {pulse}")
