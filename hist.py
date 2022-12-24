#!/usr/bin/env python

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from read_logfile import read_tcp_logfile, read_ping_logfile
from argparse import ArgumentParser

def get_range(arg):
    p = arg.split(",")
    if len(p) == 3:
        v0, v1 = int(p[0]), int(p[1])
        skip = int(p[2])
    elif len(p) == 2:
        v0, v1 = int(p[0]), int(p[1])
        skip = 2
    elif len(p) == 1:
        v0 = 0
        v1 = int(p[0])
        skip = 2
    else:
        print("ERROR:")
        ap.print_help()
        exit(1)
    return v0, v1, range(v0, 1+v1, skip)

ap = ArgumentParser(description="this is example.")
ap.add_argument("log_file", metavar="LOG_FILE", help="a log file.")
ap.add_argument("-t", action="store", dest="log_type",
                choices=["tcp", "udp", "ping"],
                default="tcp",
                help="specify the mode to parse the iperf3 mode: tcp or udp.")
ap.add_argument("-m", action="store", dest="graph_mode",
                choices=["hist"], default="hist",
                help="specify the graph mode.")
ap.add_argument("--graph-yrange", action="store", dest="graph_yrange_str",
                help="specify yrange min,max number separated by a comma.")
ap.add_argument("--graph-xrange", action="store", dest="graph_xrange_str",
                help="specify xrange min,max number separated by a comma.")
ap.add_argument("--hist-bins", action="store", dest="nb_bins",
                type=int, default=11,
                help="specify a number of bins for histgram.")
ap.add_argument("--data-xrange", action="store", dest="data_xrange_str",
                help="specify xrange min,max number separated by a comma.")
ap.add_argument("--save-graph", action="store", dest="save_file",
                help="specify a filename to store the graph.")
opt = ap.parse_args()

if opt.log_type == "tcp":
    result = read_tcp_logfile(opt.log_file)
    sr = pd.Series([n["bps"] for n in result])
    xlabel = "Throughput (Mbps)"
    xscale = 1e6
elif opt.log_type == "ping":
    result = read_ping_logfile(opt.log_file)
    print(result)
    if opt.data_xrange_str:
        x0, x1, step = get_range(opt.data_xrange_str)
        sr = pd.Series([n["rtt"] for n in result if x0 <= n["rtt"] <= x1])
    else:
        sr = pd.Series([n["rtt"] for n in result])
    print(sr)
    xlabel = "RTT (ms)"
    xscale = 1
elif opt.log_type == "udp":
    raise NotImplementedError
else:
    raise ValueError
    ap.print_help()
    exit(1)

desc = sr.describe()
print(f"## Desciption:\n{desc}")

if opt.graph_xrange_str is not None:
    # NOTE: in the histgram mode, x_ticks must not be used, use x instead.
    x_min, x_max, x_ticks = get_range(opt.graph_xrange_str)
    bins = np.linspace(x_min, x_max, opt.nb_bins)
else:
    x_min, x_max = sr.min(), sr.max()
    bins = np.linspace(sr.min(), sr.max(), opt.nb_bins)
print("## bins:", bins)
bar_width = (x_max - x_min)/xscale/(opt.nb_bins + 5)
#print("bar_width =", bar_width)

freq = sr.value_counts(bins=bins, sort=False)
df = pd.DataFrame({
        xlabel: bins[1:],
        "freq": freq,
    }, index=freq.index)
print("## Freq", [n for n in df["freq"]])

fig, ax = plt.subplots()
x = [round(n/xscale,2) for n in df[xlabel]]
y = [n for n in df["freq"]]
ax.bar(x, y, width=bar_width)
ax.set_xticks(x,
              [str(i) for i in x],
              rotation=90)

if opt.graph_xrange_str is not None:
    # x_min, x_max are assigned above.
    ax.set_xlim(x_min/xscale, x_max/xscale)
x_min, x_max = ax.get_xlim()
print(f"x_min = {x_min}")
print(f"x_max = {x_max}")

if opt.graph_yrange_str is not None:
    y_min, y_max, y_ticks = get_range(opt.graph_yrange_str)
    ax.set_ylim(y_min, y_max)
    ax.set_yticks(y_ticks)
y_min, y_max = ax.get_ylim()
print(f"y_min = {y_min}")
print(f"y_max = {y_max}")

ax.set_xlabel(f"{xlabel}")
ax.set_ylabel("Frequency")
ax.grid()

fig.tight_layout()

if opt.save_file:
    plt.savefig(opt.save_file)
plt.show()

