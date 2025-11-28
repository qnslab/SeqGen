import copy

import matplotlib.pyplot as plt
import numpy as np


class PulseKernel:
    def __init__(self, ch_defs):
        self.ch_defs = ch_defs
        self.kernel = {
            ch: {"start": [], "dur": [], "state": [], "var_dur": [], "ch_delay": []}
            for ch in ch_defs
        }

        colormap = plt.get_cmap("tab20")
        self.fill_colors = [colormap(i) for i in range(1, 20, 2)]
        self.line_colors = [
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

        self.plt_offset = 1
        self.plt_height = 0.9
        self.shortest_pulse = int(12)

    def finish_kernel(self):
        self.kernel_unaltered = copy.deepcopy(self.kernel)

    def check_duration(self, dur, var_dur):
        if var_dur:
            dur = 12
        if dur < self.shortest_pulse:
            if dur < self.shortest_pulse / 2:
                dur = 0
            else:
                dur = self.shortest_pulse
        return dur

    def append_pulse(self, chs, dur, var_dur=False, ch_delay=0):
        dur = self.check_duration(dur, var_dur)
        start_time = self.get_end_time()
        for ch in chs:
            self.kernel[ch]["start"].append(start_time)
            self.kernel[ch]["dur"].append(dur)
            self.kernel[ch]["state"].append(True)
            self.kernel[ch]["var_dur"].append(var_dur)
            self.kernel[ch]["ch_delay"].append(ch_delay)
        return

    def add_pulse(self, chs, start_time, dur, var_dur=False, ch_delay=0):
        dur = self.check_duration(dur, var_dur)
        if chs is None or chs == [] or chs == "":
            for ch in self.ch_defs:
                self.kernel[ch]["start"].append(start_time)
                self.kernel[ch]["dur"].append(dur)
                self.kernel[ch]["ch_delay"].append(ch_delay)
                self.kernel[ch]["var_dur"].append(var_dur)
                self.kernel[ch]["state"].append(False)
        else:
            for ch in chs:
                self.kernel[ch]["start"].append(start_time)
                self.kernel[ch]["dur"].append(dur)
                self.kernel[ch]["ch_delay"].append(ch_delay)
                self.kernel[ch]["var_dur"].append(var_dur)
                self.kernel[ch]["state"].append(True)
        return start_time + dur

    def append_delay(self, dur, var_dur=False):
        if dur > 0:
            dur = self.check_duration(dur, var_dur)
            start_time = self.get_end_time()
            for ch in self.ch_defs:
                self.kernel[ch]["start"].append(start_time)
                self.kernel[ch]["dur"].append(dur)
                self.kernel[ch]["ch_delay"].append(0)
                self.kernel[ch]["var_dur"].append(var_dur)
                self.kernel[ch]["state"].append(False)
            return

    def add_delay(self, start_time, dur, var_dur=False, kernel=None):
        if kernel is None:
            kernel = self.kernel
        dur = self.check_duration(dur, var_dur)
        for ch in self.ch_defs:
            kernel[ch]["start"].append(start_time)
            kernel[ch]["dur"].append(dur)
            kernel[ch]["ch_delay"].append(0)
            kernel[ch]["var_dur"].append(var_dur)
            kernel[ch]["state"].append(False)
        return kernel

    def reset_kernel(self):
        self.kernel = copy.deepcopy(self.kernel_unaltered)

    def update_var_durs(self, new_dur):
        self.reset_kernel()
        kernel = self.kernel
        var_dur_pulses = []
        for ch in kernel:
            for idx in range(len(kernel[ch]["start"])):
                if self.kernel[ch]["var_dur"][idx]:
                    var_dur_pulses.append((ch, idx, kernel[ch]["start"][idx], kernel[ch]["dur"][idx]))
        var_dur_pulses = sorted(var_dur_pulses, key=lambda x: x[2])
        var_dur_pulses = [var_dur_pulses[i] for i in range(len(var_dur_pulses)) if i == 0 or var_dur_pulses[i][2] != var_dur_pulses[i - 1][2]]
        pulse_idx = 0
        for ch, idx, start_time, dur in var_dur_pulses:
            orig_dur = kernel[ch]["dur"][idx]
            if pulse_idx > 0:
                start_time += new_dur - orig_dur
            for ch2 in self.kernel:
                for idx2 in range(len(self.kernel[ch2]["start"])):
                    start_time_2 = self.kernel[ch2]["start"][idx2]
                    if start_time_2 > start_time:
                        self.kernel[ch2]["start"][idx2] += new_dur - orig_dur
            self.kernel[ch]["dur"][idx] = new_dur
            pulse_idx += 1
        self.kernel = kernel

    def get_end_time(self):
        self.total_time = 0
        end_times = []
        for key in self.kernel:
            for idx in range(len(self.kernel[key]["start"])):
                end_times.append(self.kernel[key]["start"][idx] + self.kernel[key]["dur"][idx])
        self.total_time = np.max(end_times) if len(end_times) > 0 else 0
        return self.total_time

    def shift_ch_delays(self):
        prev_end_time = self.get_end_time()
        kernel = self.kernel
        for key in kernel:
            if len(kernel[key]["start"]) > 0:
                for idx in range(0, len(kernel[key]["start"])):
                    if kernel[key]["state"] and kernel[key]["ch_delay"][idx] > 0:
                        kernel[key]["start"][idx] -= kernel[key]["ch_delay"][idx]
                        kernel[key]["ch_delay"][idx] = 0
        if prev_end_time != self.get_end_time():
            dur = abs(prev_end_time - self.get_end_time())
            self.add_delay(prev_end_time, dur, kernel)
        self.kernel = kernel

    def wrap_pulses(self):
        prev_end_time = self.get_end_time()
        for key in self.kernel:
            negative_pulses = [(idx, start_time) for idx, start_time in enumerate(self.kernel[key]["start"]) if start_time < 0]
            for idx, start_time in negative_pulses:
                shift_time = abs(start_time)
                dur = self.kernel[key]["dur"][idx]
                dur_end = shift_time if dur > shift_time else dur
                self.add_pulse([key], prev_end_time + start_time, dur_end, 0)
                if self.kernel[key]["dur"][idx] > shift_time:
                    self.add_pulse([key], 0, self.kernel[key]["dur"][idx] - shift_time, 0)
        for key in self.kernel:
            negative_pulses = [(idx, start_time) for idx, start_time in enumerate(self.kernel[key]["start"]) if start_time < 0]
            for idx, start_time in negative_pulses[::-1]:
                self.kernel[key]["start"].pop(idx)
                self.kernel[key]["dur"].pop(idx)
                self.kernel[key]["ch_delay"].pop(idx)
                self.kernel[key]["state"].pop(idx)
                self.kernel[key]["var_dur"].pop(idx)
        self.pulses_shifted = True

    def convert_to_instructions(self, const_chs=[]):
        self.shift_ch_delays()
        self.wrap_pulses()
        insts = []
        unique_times = set()
        for ch in self.kernel:
            unique_times.update(self.kernel[ch]["start"])
            unique_times.update(
                self.kernel[ch]["start"][idx] + self.kernel[ch]["dur"][idx]
                for idx in range(len(self.kernel[ch]["start"]))
            )
        unique_times = sorted(unique_times)
        for time in unique_times:
            active_chs = []
            for ch in self.kernel:
                for idx in range(len(self.kernel[ch]["start"])):
                    start_time = self.kernel[ch]["start"][idx]
                    end_time = start_time + self.kernel[ch]["dur"][idx]
                    if start_time <= time < end_time:
                        if self.kernel[ch]["state"][idx]:
                            active_chs.append(ch)
            insts.append({"time": time, "active_chs": active_chs})
        for idx in range(len(insts) - 1):
            insts[idx]["dur"] = insts[idx + 1]["time"] - insts[idx]["time"]
        insts = insts[:-1]
        updated_insts = []
        for inst in insts:
            updated_insts.append({"active_chs": inst["active_chs"], "dur": inst["dur"], "const_chs": const_chs})
        self.insts = updated_insts
        combined_insts = []
        for idx in range(len(self.insts) - 1):
            if self.insts[idx]["active_chs"] == self.insts[idx + 1]["active_chs"]:
                self.insts[idx + 1]["dur"] += self.insts[idx]["dur"]
            else:
                combined_insts.append(self.insts[idx])
        combined_insts.append(self.insts[-1])
        self.insts = combined_insts
        return

    def plot_pulses(self, title=None):
        self.get_end_time()
        plt.figure(figsize=(10, 5))
        ch_states = [0] * len(self.ch_defs)
        for i in range(len(self.ch_defs)):
            ch_states[i] = ch_states[i] + i * self.plt_offset
        for ch in self.kernel:
            ch_index = list(self.kernel.keys()).index(ch)
            if len(self.kernel[ch]["start"]) > 0:
                for idx in range(len(self.kernel[ch]["start"])):
                    t = self.kernel[ch]["start"][idx]
                    dur = self.kernel[ch]["dur"][idx]
                    if self.kernel[ch]["state"][idx]:
                        plt.plot([t, t + dur], [ch_states[ch_index] + self.plt_height, ch_states[ch_index] + self.plt_height], color=self.line_colors[ch_index])
                        plt.fill_between([t, t + dur], ch_states[ch_index], ch_states[ch_index] + self.plt_height, color=self.fill_colors[ch_index])
                        plt.plot([t, t], [ch_states[ch_index], ch_states[ch_index] + self.plt_height], self.line_colors[ch_index])
                        plt.plot([t + dur, t + dur], [ch_states[ch_index], ch_states[ch_index] + self.plt_height], self.line_colors[ch_index])
                    else:
                        plt.plot([t, t + dur], [ch_states[ch_index], ch_states[ch_index]], self.line_colors[ch_index])
                if self.kernel[ch]["start"][-1] + self.kernel[ch]["dur"][-1] < self.total_time:
                    plt.plot([self.kernel[ch]["start"][-1] + self.kernel[ch]["dur"][-1], self.total_time], [ch_states[ch_index], ch_states[ch_index]], self.line_colors[ch_index])
            else:
                plt.plot([0, self.total_time], [ch_states[ch_index], ch_states[ch_index]], self.line_colors[ch_index])
        plt.yticks(np.linspace(0, len(ch_states), len(ch_states)), list(self.ch_defs.keys()))
        plt.xlabel("Time (s)")
        if title is not None:
            plt.title(title)
        plt.show()

    def plot_inst_kernel(self, title=None):
        insts = self.insts
        ch_defs = self.ch_defs
        plt.figure(figsize=(10, 5))
        total_time = 0
        for inst in insts:
            total_time += inst["dur"]
        t = 0
        chs = np.zeros(len(ch_defs))
        for i in range(len(ch_defs)):
            chs[i] = chs[i] + i * 1.1
        colormap = plt.get_cmap("tab20")
        line_colors = [colormap(i) for i in range(0, 20, 2)]
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
        prev_chs = []
        prev_const_chs = []
        for inst in insts:
            for ch in inst["active_chs"]:
                ch_index = list(ch_defs.keys()).index(ch)
                plt.plot([t, t + inst["dur"]], [chs[ch_index] + 1, chs[ch_index] + 1], color=line_colors[ch_index])
                plt.fill_between([t, t + inst["dur"]], chs[ch_index], chs[ch_index] + 1, color=fill_colors[ch_index])
                if ch not in prev_chs:
                    plt.plot([t, t], [chs[ch_index], chs[ch_index] + 1], line_colors[ch_index])
            for ch in inst["const_chs"]:
                ch_index = list(ch_defs.keys()).index(ch)
                dur = inst["dur"]
                plt.plot([t, t + dur], [chs[ch_index] + 1, chs[ch_index] + 1], line_colors[ch_index])
                plt.fill_between([t, t + dur], chs[ch_index], chs[ch_index] + 1, color=fill_colors[ch_index])
                if ch not in prev_const_chs:
                    plt.plot([t, t], [chs[ch_index], chs[ch_index] + 1], line_colors[ch_index])
            for ch in ch_defs:
                if ch not in inst["const_chs"]:
                    ch_index = list(ch_defs.keys()).index(ch)
                    plt.plot([t + inst["dur"], t + inst["dur"]], [chs[ch_index], chs[ch_index]], line_colors[ch_index])
                if ch in prev_const_chs and ch not in inst["const_chs"]:
                    ch_index = list(ch_defs.keys()).index(ch)
                    plt.plot([t, t], [chs[ch_index] + 1, chs[ch_index]], line_colors[ch_index])
            for ch in ch_defs:
                if ch not in inst["active_chs"] and ch not in inst["const_chs"]:
                    ch_index = list(ch_defs.keys()).index(ch)
                    plt.plot([t, t + inst["dur"]], [chs[ch_index], chs[ch_index]], line_colors[ch_index])
                if ch in prev_chs and ch not in inst["active_chs"]:
                    ch_index = list(ch_defs.keys()).index(ch)
                    plt.plot([t, t], [chs[ch_index] + 1, chs[ch_index]], line_colors[ch_index])
            prev_chs = inst["active_chs"]
            prev_const_chs = inst["const_chs"]
            t += inst["dur"]
        plt.yticks(chs + 0.5, list(ch_defs.keys()))
        plt.xlabel("Time (s)")
        if title is not None:
            plt.title(title)
        # plt.show()
