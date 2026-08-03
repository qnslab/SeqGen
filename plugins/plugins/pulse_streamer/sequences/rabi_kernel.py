"""
Testing a camera rabi sequence with the Pulse Streamer. 

Programmed in the pulsestreamer method

"""

import numpy as np
from seqgen.sequence_helpers import (
    extend_sequence, make_segment, plot_sequences, 
    repeated_block, shift_first_segment, get_total_block_duration
)
from loguru import logger

from pulsestreamer import PulseStreamer
from pulsestreamer import TriggerStart, TriggerRearm
from pulsestreamer import Sequence, OutputState

ip_or_serial='169.254.8.2' # edit this line to connect to a specific Pulse Streamer via its IP address, hostname or serial number
# pulser = PulseStreamer(ip_or_serial)
shortest_pulse_duration = 1 # ns

#define channel names 
ch_laser     = 0 # output channel 0
ch_camera    = 1 # output channel 1
ch_x         = 2 # output channel 2
ch_y         = 3 # output channel 3

ch_analog_x   = 0 # analog channel 0
ch_analog_y   = 1 # analog channel 1


#define digital levels
HIGH=1
LOW=0

laser_dur = 3e-6
laser_initialization_time = 3*laser_dur
laser_delay = 300e-9
laser_to_rf_delay = 50e-9
rf_delay = 50e-9
ref_mode = "no_rf"
camera_on_time = 0.1e-3
camera_readout_time = 0.01e-3


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
camera_on_time    = int(camera_on_time * 1e9)
camera_readout_time = int(camera_readout_time * 1e9)

time_list = 1e9 * time_list
time_list = [int(i) for i in time_list.tolist()]

print("tau values in ns: ", time_list)

def signal_sequence(t, repeats, cam_state=HIGH):
    # updated_camera_on_time is the time that the camera is on for each repetition of the sequence. 
    # It is the sum of the laser duration, the microwave delay, and the microwave pulse time.
    updated_camera_on_time = (round(laser_dur + rf_delay + t ))

    seq_sig_laser = repeated_block(
        (laser_dur, HIGH),
        (rf_delay + t, LOW),
        repeats=repeats,
        smallest_pulse_duration=shortest_pulse_duration
    )

    seq_sig_mw_x = repeated_block(
        (laser_dur + rf_delay, LOW),
        (t, HIGH),
        repeats=repeats,
        smallest_pulse_duration=shortest_pulse_duration
    )

    seq_sig_camera = repeated_block(
        (updated_camera_on_time*repeats, cam_state),
        smallest_pulse_duration=shortest_pulse_duration
    )

    return seq_sig_laser, seq_sig_mw_x, seq_sig_camera

def reference_sequence(t, repeats, cam_state=HIGH):
    updated_camera_on_time = (round(laser_dur + rf_delay + t ))

    seq_ref_laser = repeated_block(
        (laser_dur, HIGH),
        (rf_delay + t, LOW),
        repeats=repeats,
        smallest_pulse_duration=shortest_pulse_duration
    )

    seq_ref_mw_x = repeated_block(
        (laser_dur + rf_delay, LOW),
        (t, LOW),
        repeats=repeats,
        smallest_pulse_duration=shortest_pulse_duration
    )

    seq_ref_camera = repeated_block(
        (updated_camera_on_time*repeats, cam_state),
        smallest_pulse_duration=shortest_pulse_duration
    )

    return seq_ref_laser, seq_ref_mw_x, seq_ref_camera


# number of repetitions of the sequence to fill the camera integration time
base_block_time = get_total_block_duration(signal_sequence(time_list[0], 1))
# print("Base sequence time: ", base_sequence_time)

n_repetitions = round(camera_on_time / base_block_time)
n_repetitions_readout = round(camera_readout_time / base_block_time)

print("Number of repetitions of the sequence to fill the camera integration time: ", n_repetitions)
print("Number of repetitions of the sequence to fill the camera readout time: ", n_repetitions_readout)
# override the number of repetitions to 1 for testing purposes.
# n_repetitions = 1
# n_repetitions_readout = 1

# initialize the sequence with the first time value
seq_laser = [make_segment(laser_initialization_time, HIGH)]
seq_mw_x = [make_segment(laser_initialization_time, LOW)]
seq_camera = [make_segment(laser_initialization_time, LOW)]

# Program the sequence for varying times. The camera is always on for signal, then off for camera readout time.
for t in time_list:
  # make sure that the time is rounded to an integer number of ns
  t = round(t)

  updated_camera_on_time = (round(laser_dur + rf_delay + t ))

  # signal sequence
  seq_sig_laser, seq_sig_mw_x, seq_sig_camera = signal_sequence(t, n_repetitions, cam_state=HIGH)
  seq_sig_laser_readout, seq_sig_mw_x_readout, seq_sig_camera_readout = signal_sequence(t, n_repetitions_readout, cam_state=LOW)

  # reference sequence
  seq_ref_laser, seq_ref_mw_x, seq_ref_camera = reference_sequence(t, n_repetitions + n_repetitions_readout, cam_state=HIGH)
  seq_ref_laser_readout, seq_ref_mw_x_readout, seq_ref_camera_readout = reference_sequence(t, n_repetitions_readout, cam_state=LOW)

  # combine the signal and reference sequences for each channel
  seq_laser += seq_sig_laser + seq_sig_laser_readout + seq_ref_laser + seq_ref_laser_readout
  seq_mw_x += seq_sig_mw_x + seq_sig_mw_x_readout + seq_ref_mw_x + seq_ref_mw_x_readout
  seq_camera += seq_sig_camera + seq_sig_camera_readout + seq_ref_camera + seq_ref_camera_readout


# we make a fake sequence with the

plot_laser, plot_mw_x, plot_camera = signal_sequence(time_list[0], 1, cam_state=HIGH)
plot_laser_r, plot_mw_x_r, plot_camera_r = reference_sequence(time_list[0], 1, cam_state=HIGH)

plot_sequences(
  [plot_laser + plot_laser_r, plot_mw_x + plot_mw_x_r, plot_camera + plot_camera_r],
  ["Laser", "MW X", "Camera"],
  title="Pulse Streamer sequence",
)
# to introduce the laser delay we can just subtract the delay from the duration of the first laser pulse. 
# This works provided that the initalisation pulse is long enough to account for the delay. 
if laser_initialization_time < laser_delay:
  # raise a warning that the laser initialization time is less than the laser delay.
  logger.warning("Laser initialization time is less than the laser delay. The first laser pulse may not be properly delayed.")

shift_first_segment(seq_laser, -laser_delay)


