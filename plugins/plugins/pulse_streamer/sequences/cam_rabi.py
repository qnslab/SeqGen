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

# pulser = PulseStreamer(ip_or_serial)

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

laser_dur = 3e-6
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
pk_sig.append_pulse(["rf_x"], 100, ch_delay=rf_delay, var_dur=False)
# Finish the kernel and shift the channel delays to account for the variable duration of the RF pulse
pk_sig.finish_kernel()
pk_sig.shift_ch_delays()
pk_sig.wrap_pulses()
# pk_sig.plot_pulses()

# pk_sig.convert_to_instructions()  # convert to instructions for the Pulse Streamer
# pk_sig.plot_inst_kernel()


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


# after wrapping the pulses we need to reorder based on the start times of the pulses. The PulseKernel class has a method to do this, but we can also do it manually here for demonstration purposes.
for ch in pk_sig.kernel:
  # sort the pulses based on the start times
  pk_sig.kernel[ch]["start"], pk_sig.kernel[ch]["dur"], pk_sig.kernel[ch]["state"] = zip(*sorted(zip(pk_sig.kernel[ch]["start"], pk_sig.kernel[ch]["dur"], pk_sig.kernel[ch]["state"])))
  pk_ref.kernel[ch]["start"], pk_ref.kernel[ch]["dur"], pk_ref.kernel[ch]["state"] = zip(*sorted(zip(pk_ref.kernel[ch]["start"], pk_ref.kernel[ch]["dur"], pk_ref.kernel[ch]["state"])))

# if the is a gap between the end of the last pulse and the start of the next pulse, 
# we need to add a pulse with a duration equal to the gap and a state of 0 (LOW) to fill in the gap. 
# This is necessary because the Pulse Streamer requires that each channel be completely defined for the entire duration of the sequence. 
for ch in pk_sig.kernel:
  for idx in range(len(pk_sig.kernel[ch]["start"]) - 1):
    end_time = pk_sig.kernel[ch]["start"][idx] + pk_sig.kernel[ch]["dur"][idx]
    next_start_time = pk_sig.kernel[ch]["start"][idx + 1]
    if next_start_time > end_time:
      gap_duration = next_start_time - end_time
      pk_sig.kernel[ch]["start"] += (end_time,)
      pk_sig.kernel[ch]["dur"] += (gap_duration,)
      pk_sig.kernel[ch]["state"] += (False,)

for ch in pk_sig.kernel:
  # sort the pulses based on the start times
  pk_sig.kernel[ch]["start"], pk_sig.kernel[ch]["dur"], pk_sig.kernel[ch]["state"] = zip(*sorted(zip(pk_sig.kernel[ch]["start"], pk_sig.kernel[ch]["dur"], pk_sig.kernel[ch]["state"])))
  pk_ref.kernel[ch]["start"], pk_ref.kernel[ch]["dur"], pk_ref.kernel[ch]["state"] = zip(*sorted(zip(pk_ref.kernel[ch]["start"], pk_ref.kernel[ch]["dur"], pk_ref.kernel[ch]["state"])))

# now to clean up the kernel we combine any consecutive pulses with the same state into a 
# single pulse with a duration equal to the sum of the durations of the consecutive pulses. 
# This is necessary because the Pulse Streamer requires that each channel be completely 
# defined for the entire duration of the sequence, and consecutive pulses with the same state 
# can be combined into a single pulse to reduce the number of instructions sent to the Pulse Streamer.

# to do this we make a new kernel as tuples don't allow for easy modification. 
# We will then convert the new kernel back to a dictionary of lists at the end.
new_kernel = {}
for ch in pk_sig.kernel:
  # check if there any pulses in the channel, if not we can skip it.
  # that is see if the state is all 0 (LOW), if so we can skip it.
  if not any(pk_sig.kernel[ch]["state"]):
    continue
  new_kernel[ch] = {"start": [], "dur": [], "state": []}
  # find pulses that have the same state and combine them into a single pulse with a duration equal to the sum of the durations of the consecutive pulses.
  for idx in range(len(pk_sig.kernel[ch]["start"])):
    if idx == 0:
      new_kernel[ch]["start"].append(pk_sig.kernel[ch]["start"][idx])
      new_kernel[ch]["dur"].append(pk_sig.kernel[ch]["dur"][idx])
      new_kernel[ch]["state"].append(pk_sig.kernel[ch]["state"][idx])
    else:
      if pk_sig.kernel[ch]["state"][idx] == new_kernel[ch]["state"][-1]:
        new_kernel[ch]["dur"][-1] += pk_sig.kernel[ch]["dur"][idx]
      else:
        new_kernel[ch]["start"].append(pk_sig.kernel[ch]["start"][idx])
        new_kernel[ch]["dur"].append(pk_sig.kernel[ch]["dur"][idx])
        new_kernel[ch]["state"].append(pk_sig.kernel[ch]["state"][idx])
  


all_pulses = {}
for ch in new_kernel:
  # make the list of pulses for each channel as a list of tuples of (duration, state)
  # Each channel needs to be completely defined, so the zero time start should be zero if the first instruction starts at a later time. The duration of the last instruction should be the end time of the last instruction minus the start time of the last instruction.
  ch_pulses = []
  for idx, start_time in enumerate(new_kernel[ch]["start"]):
    if idx == 0 and start_time > 0:
      ch_pulses.append((start_time, LOW))
    duration = new_kernel[ch]["dur"][idx]
    state = new_kernel[ch]["state"][idx]
    ch_pulses.append((duration, 1 if state else 0))
  all_pulses[ch] = ch_pulses

for ch in all_pulses:
  print(f"Channel {ch}: {all_pulses[ch]}")
  


  # print(f"  End times: {pk_sig.kernel[ch]['end']}")
  
  # print(pulse)
  # print(f"  State: {ch["state"]}")
  # print(f"  duration: {ch["end"] - ch["start"]} ns")