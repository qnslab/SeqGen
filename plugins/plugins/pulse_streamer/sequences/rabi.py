"""
Testing a camera rabi sequence with the Pulse Streamer. 

Programmed in the pulsestreamer method

"""

import numpy as np
from seqgen.pulse_kernel import PulseKernel
from loguru import logger
import matplotlib.pyplot as plt

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


mw_x_delay = 200 #ns
camera_on_time = 1e6
camera_readout_time = 1e6


#define digital levels
HIGH=1
LOW=0


laser_dur = 3e-6
laser_initialization_time = 3*laser_dur
laser_delay = 300e-9
laser_to_rf_delay = 50e-9
rf_delay = 50e-9
ref_mode = "no_rf"
exp_t = 1e-3
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

time_list = np.linspace(250, 500, 2) * 1e-9
  
if ref_mode == ("" or None):
    b_ref = False
    logger.info("Setting up Rabi sequence with no reference")
else:
    b_ref = True
    logger.info("Setting up Rabi sequence with {} as a reference", ref_mode)

# convert times to ns assuming the user inputs in s
laser_initialization_time = int(laser_initialization_time * 1e9)
laser_dur         = int(laser_dur * 1e9)
laser_delay       = int(laser_delay * 1e9)
laser_to_rf_delay = int(laser_to_rf_delay * 1e9)
rf_delay          = int(rf_delay * 1e9)
exp_t             = int(exp_t * 1e9)
trigger_time      = int(camera_trig_time * 1e9)

time_list = 1e9 * time_list
time_list = [int(i) for i in time_list.tolist()]

# number of repetitions of the sequence to fill the camera integration time
base_sequence_time = round(laser_dur + time_list[-1] + mw_x_delay)
# print("Base sequence time: ", base_sequence_time)

n_repetitions = round(camera_on_time / base_sequence_time)
n_repetitions_readout = round(camera_readout_time / base_sequence_time)

# print("Number of repetitions of the sequence to fill the camera integration time: ", n_repetitions)
# print("Number of repetitions of the sequence to fill the camera readout time: ", n_repetitions_readout)

n_repetitions = 1
n_repetitions_readout = 0


# initialize the sequence with the first time value
seq_laser = []
seq_mw_x = []
seq_camera = []

# make an initalisation pulse with the laser on to make sure the system is in a known state before the sequence starts. 
seq_laser += [(laser_initialization_time, HIGH)]
seq_mw_x += [(laser_initialization_time, LOW)]
seq_camera += [(laser_initialization_time, LOW)]

for t in time_list:
  # make sure that the time is rounded to an integer number of ns
  t = round(t)

  updated_camera_on_time = (round(laser_dur + mw_x_delay + t ))

  # signal sequence
  seq_sig_laser = [
      (laser_dur, HIGH), 
      (mw_x_delay + t, LOW)
    ]*(n_repetitions + n_repetitions_readout)

  seq_sig_mw_x = [
      (laser_dur + mw_x_delay, LOW), 
      (t, HIGH), 
    ]*(n_repetitions + n_repetitions_readout)

  seq_sig_camera = [
      (updated_camera_on_time * n_repetitions, HIGH), 
      (updated_camera_on_time*n_repetitions_readout, LOW)
    ]

  # reference sequence
  seq_ref_laser = [
      (laser_dur, HIGH), 
      (mw_x_delay + t , LOW)
    ]*(n_repetitions + n_repetitions_readout)
  seq_ref_mw_x = [
      (laser_dur + mw_x_delay, LOW), 
      (t, LOW)
    ]*(n_repetitions + n_repetitions_readout)
  seq_ref_camera = [
      (updated_camera_on_time * n_repetitions, HIGH), 
      (updated_camera_on_time*n_repetitions_readout, LOW)
    ]

  seq_laser += seq_sig_laser + seq_ref_laser
  seq_mw_x += seq_sig_mw_x + seq_ref_mw_x
  seq_camera += seq_sig_camera + seq_ref_camera

print(f"Time {t} ns: Laser sequence: {seq_laser}")

def plot_sequence(sequences, channel_names, title=None):
  """Render duration/state lists with the same filled pulse style as PulseKernel."""

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
  baselines = [idx * plt_offset for idx in range(len(sequences))]
  total_time = max((sum(dur for dur, _ in seq) for seq in sequences), default=0)

  for idx, (seq, ch_name) in enumerate(zip(sequences, channel_names)):
    baseline = baselines[idx]
    line_color = line_colors[idx % len(line_colors)]
    fill_color = fill_colors[idx % len(fill_colors)]
    time = 0
    for dur, state in seq:
      if state:
        top = baseline + plt_height
        plt.plot([time, time + dur], [top, top], color=line_color)
        plt.fill_between([time, time + dur], baseline, top, color=fill_color)
        plt.plot([time, time], [baseline, top], color=line_color)
        plt.plot([time + dur, time + dur], [baseline, top], color=line_color)
      else:
        plt.plot([time, time + dur], [baseline, baseline], color=line_color)
      time += dur

  plt.yticks([baseline + plt_height / 2 for baseline in baselines], channel_names)
  plt.ylim(-0.2, (baselines[-1] + plt_height + 0.2) if baselines else 1.0)
  plt.xlim(0, total_time * 1.02 if total_time else 1.0)
  plt.xlabel("Time (ns)")
  if title is not None:
    plt.title(title)
  plt.tight_layout()
  plt.show()


plot_sequence(
  [seq_laser, seq_mw_x, seq_camera],
  ["Laser", "MW X", "Camera"],
  title="Pulse Streamer sequence",
)
# to introduce the laser delay we can just subtract the delay from the duration of the first laser pulse. 
# This works provided that the initalisation pulse is long enough to account for the delay. 
if laser_initialization_time < laser_delay:
  # raise a warning that the laser initialization time is less than the laser delay.
  logger.warning("Laser initialization time is less than the laser delay. The first laser pulse may not be properly delayed.")

seq_laser[0] = (seq_laser[0][0] - laser_delay, seq_laser[0][1])

plot_sequence(
  [seq_laser, seq_mw_x, seq_camera],
  ["Laser", "MW X", "Camera"],
  title="Pulse Streamer sequence with channel delays",
)
