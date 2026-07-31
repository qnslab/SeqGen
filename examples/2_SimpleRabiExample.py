"""
Testing a camera rabi sequence with the Pulse Streamer. 

"""


#import JSON-RPC Pulse Streamer wrapper class, to use Google-RPC import from pulsestreamer.grpc
from pulsestreamer import PulseStreamer

#import enum types 
from pulsestreamer import TriggerStart, TriggerRearm

#import class Sequence and OutputState for advanced sequence building
from pulsestreamer import Sequence, OutputState

#python module for scientific computing only used for creating the random pulse and merging signals
import numpy as np

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


# now we need to program the sequence for varying times. 
# the camera is always on for signal, then off for camera readout time. 
# the sequence is: [laser pulse, wait, microwave pulse (varying time) ] repeated over the camera integration time.

time_values = np.linspace(0, 1e3, 10)  # varying microwave pulse times from 0 to 1e3 ns in 10 steps

# number of repetitions of the sequence to fill the camera integration time
base_sequence_time = round(laser_pulse_time + time_values[-1] + mw_x_delay)
print("Base sequence time: ", base_sequence_time)

n_repetitions = round(camera_on_time / base_sequence_time)
n_repetitions_readout = round(camera_readout_time / base_sequence_time)

print("Number of repetitions of the sequence to fill the camera integration time: ", n_repetitions)
print("Number of repetitions of the sequence to fill the camera readout time: ", n_repetitions_readout)


# initialize the sequence with the first time value
seq_laser = []
seq_mw_x = []
seq_camera = []

for t in time_values:
  # make sure that the time is rounded to an integer number of ns
  t = round(t)
  updated_camera_on_time = (round(laser_pulse_time + mw_x_delay + t ))

  # signal sequence
  seq_sig_laser = [(laser_pulse_time, HIGH), (mw_x_delay + t, LOW)]*(n_repetitions + n_repetitions_readout)
  seq_sig_mw_x = [(laser_pulse_time + mw_x_delay, LOW), (t, HIGH), ]*(n_repetitions + n_repetitions_readout)
  seq_sig_camera = [(updated_camera_on_time * n_repetitions, HIGH), (updated_camera_on_time*n_repetitions_readout, LOW)]

  # reference sequence
  seq_ref_laser = [(laser_pulse_time, HIGH), (mw_x_delay + t , LOW)]*(n_repetitions + n_repetitions_readout)
  seq_ref_mw_x = [(laser_pulse_time + mw_x_delay, LOW), (t, LOW)]*(n_repetitions + n_repetitions_readout)
  seq_ref_camera = [(updated_camera_on_time * n_repetitions, HIGH), (updated_camera_on_time*n_repetitions_readout, LOW)]

  seq_laser += seq_sig_laser + seq_ref_laser
  seq_mw_x += seq_sig_mw_x + seq_ref_mw_x
  seq_camera += seq_sig_camera + seq_ref_camera


#create the sequence
seq = Sequence()

#set digital channels
seq.setDigital(ch_laser, seq_laser)
seq.setDigital(ch_camera, seq_camera)
seq.setDigital(ch_x, seq_mw_x)
# seq.setAnalog(ch_analog_x, seq_mw_x)


#run the sequence only once 
n_runs = 1
# n_runs = 'INFIITE' # repeat the sequence all the time

#reset the device - all outputs 0V
pulser.reset()

#set constant state of the device
pulser.constant(OutputState.ZERO()) #all outputs 0V

# define the final state of the Pulsestreamer - the device will enter this state when the sequence is finished
final = OutputState.ZERO()

#Start via the trigger input and enable the retrigger-function
#start = Start.HARDWARE_RISING
#mode = Mode.NORMAL

#Start the sequence after the upload and disable the retrigger-function
start = TriggerStart.IMMEDIATE
rearm = TriggerRearm.MANUAL

pulser.setTrigger(start=start, rearm=rearm)

print ("\nGenerated sequence pulse list:")
print ("Data format: Sequence as a list of sequence steps (duration [ns], digital bit pattern, analog 0, analog 1)")
print(seq.getData())
print("\nThe channel pulse pattern are shown in a Pop-Up window. To proceed with streaming the sequence, please close the sequence plot.")
seq.plot()
#upload the sequence and arm the device
pulser.stream(seq, n_runs, final)
print ("\nOutput running on Pulse Streamer")