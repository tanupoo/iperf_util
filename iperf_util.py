#!/usr/bin/env python

from subprocess import Popen, DEVNULL, PIPE
import shlex
import matplotlib.pyplot as plt
import glob
import os
import re
from argparse import ArgumentParser
from argparse import ArgumentDefaultsHelpFormatter
from utils import get_ts, convert_xnum, get_test_list
from read_logfile import read_logfile
import json
from statistics import mean

#
# measurement
#
def iperf(cmd, output_file):
    """
    the option --logfile doesn't save the command line.
    So, it uses Popen() to take the output of the command,
    save both the command line and the output into the result file.
    """
    with Popen(shlex.split(cmd),
                stdin=DEVNULL, stdout=PIPE, stderr=PIPE) as proc:
        outs, errs = proc.communicate()
        if len(errs) > 0:
            print(errs)
        if proc.returncode != 0:
            print(f"ERROR: {proc.returncode}")
            exit(0)
        # modify the output
        if not outs.startswith(b"{"):
            outs = b"\n".join(outs.split(b"\n")[1:])
        with open(output_file, "w") as fd:
            fd.write(f"% {cmd}\n")
            fd.write(outs.decode())

def measure(opt):
    cmd_fmt = "iperf3 -u -c {name} -P {nb_parallel} -t {time} -b {{br}} -l {{psize}}".format(**{
            "name": opt.server_name,
            "nb_parallel": opt.nb_parallel,
            "time": opt.measure_time})
    ofile_fmt = "{path}iperf-{name}-{dir}-br-{{br}}-ps-{{psize}}-{{id}}.txt".format(**{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr"})
    if opt.reverse:
        cmd_fmt += " -R"
    for br in opt.br_list:
        for psize in opt.psize_list:
            cmd = cmd_fmt.format(**{"br":br, "psize":psize})
            print(cmd)
            output_file = ofile_fmt.format(**{
                    "br": br,
                    "psize": psize,
                    "id": get_ts(),
                    })
            iperf(cmd, output_file)

#
# graph
#
def print_result(result, x_axis):
    assert x_axis in ["br", "psize"]
    column_size = [8,8,8,8,8,8,6,6]
    fmt = " ".join([f"{{:{n}}}" for n in column_size])
    if x_axis == "br":
        k1 = ""
    print(fmt.format(
            "Tgt Br", "PL Size",
            "Snd Br", "Rcv Br",
            "Snd PPS", "Rcv PPS",
            "lost%", "jitter"))
    print(" ".join(["-"*n for n in column_size]))
    for k1 in sorted(result.keys()):
        for k2 in sorted(result[k1].keys()):
            d = result[k1][k2]
            if x_axis == "br":
                br = k2
                psize = k1
            else:
                br = k1
                psize = k2
            print(fmt.format(
                round(br/1e6,2),
                psize,
                round(d["send_br"]/1e6,2),
                round(d["recv_br"]/1e6,2),
                round(d["send_pps"]/1e6,2),
                round(d["recv_pps"]/1e6,2),
                round(d["lost"],3),
                round(d["jitter"],3)))

def read_result(opt, x_axis):
    assert x_axis in ["br", "psize"]
    template = "{path}iperf-{name}-{dir}-br-{{br}}-ps-{{psize}}-*.txt".format(
            **{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr"
            })
    base_list = []
    for br in opt.br_list:
        for psize in opt.psize_list:
            glob_name = template.format(**{"br": br, "psize": psize})
            if opt.debug:
                print(f"glob: {glob_name}")
            base_list.extend(glob.glob(glob_name))
    result = {}
    for fname in base_list:
        r = re.match(".*iperf-"
                     "[^-]+-"
                     "[^-]+-"
                     "br-([^-]+)-"
                     "ps-([^-]+)-"
                     ".*.txt", fname)
        if r:
            if x_axis == "br":
                k1 = r.group(2) # psize
                k2 = r.group(1) # br
            else:
                k1 = r.group(1) # br
                k2 = r.group(2) # psize
            x0 = result.setdefault(convert_xnum(k1), {})
            x1 = x0.setdefault(convert_xnum(k2), {
                    "dataset": [],
                    "send_br": 0,
                    "recv_br": 0,
                    "send_pps": 0,
                    "recv_pps": 0,
                    "lost": 0,
                    "jitter": 0,
                    })
            d = read_logfile(fname)
            x1["dataset"].append({"name": fname, "data": d})
            ds = d["sender"]
            dr = d["receiver"]
            x1["send_br"] += ds["bps"]
            x1["recv_br"] += dr["bps"]
            x1["send_pps"] += (ds["bps"]/8/ds["payload_size"]*1e6)
            x1["recv_pps"] += (dr["bps"]/8/ds["payload_size"]*1e6)
            x1["lost"] += dr["lost_percent"]
            x1["jitter"] += dr["jitter_ms"]
    for k1 in result.keys():
        for k2 in result[k1].keys():
            x1 = result[k1][k2]
            nb_items = len(x1["dataset"])
            if nb_items > 1:
                x1["send_br"] /= nb_items
                x1["recv_br"] /= nb_items
                x1["send_pps"] /= nb_items
                x1["recv_pps"] /= nb_items
                x1["lost"] /= nb_items
                x1["jitter"] /= nb_items
    if len(result) == 0:
        raise ValueError("ERROR: the target file list is empty.")
    if opt.verbose:
        print(json.dumps(result, indent=4))
    print_result(result, x_axis)
    return result

def save_graph(opt, graph_name):
    ofile = "{path}iperf-{name}-{dir}-{gname}-{ts}.png".format(**{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr",
            "gname": graph_name,
            "ts": get_ts()})
    plt.savefig(ofile)
    print(f"saved to {ofile}")

def make_pps_graph(opt):
    """
    to show how many packets with a fixed size can be properly transmitted in a second.
    """
    if len(opt.br_list) == 1:
        result = read_result(opt, "psize")
        k1 = list(result.keys())[0]
        fig = plt.figure()
        fig.suptitle(f"PPS and Lost, bitrate = {k1} bps")
        ax1 = fig.add_subplot(1,1,1)

        ax1.set_xlabel("Tx PPS")
        ax1.set_ylabel("Rx Lost (%)")

        brs = result[k1]
        x = [brs[br]["send_pps"]/1e6 for br in sorted(brs)]
        line1 = ax1.plot(x,
                        [brs[br]["lost"] for br in sorted(brs)],
                        label=f"{k1}",
                        marker="o",
                        linestyle="solid")
        ax1.set_ylim(0)
        print(f"X axes: {ax1.get_xlim()}")
        print(f"Y axes: {ax1.get_ylim()}")
        ax1.grid()

        if opt.with_y2:
            ax2 = ax1.twinx()
            ax2.set_ylabel("Jitter(ms)")
            line2 = ax2.plot(x,
                            [brs[br]["jitter"] for br in sorted(brs)],
                            label=f"{k1}",
                            alpha=0.5)

    else:
        result = read_result(opt, "br")
        #fig = plt.figure(figsize=(9,5))
        fig = plt.figure(figsize=(12,7))
        fig.suptitle(f"PPS and Lost")
        ax = fig.add_subplot(1,1,1)

        ax.set_xlabel("Tx PPS")
        ax.set_ylabel("Rx Lost (%)")
        for psize in sorted(result.keys()):
            brs = result[psize]
            x = [brs[br]["send_pps"]/1e6 for br in sorted(brs)]
            line1 = ax.plot(x,
                            [brs[br]["lost"] for br in sorted(brs)],
                            label=f"{psize}",
                            marker="o",
                            linestyle="solid")
        ax.legend(title="lost", frameon=False, prop={'size':8},
                bbox_to_anchor=(-.11, 0.8), loc="center right")
        ax.set_ylim(0)
        print(f"X axes: {ax1.get_xlim()}")
        print(f"Y axes: {ax1.get_ylim()}")
        ax.grid()

        if opt.with_y2:
            ax3 = ax.twinx()
            ax3.set_ylabel("Jitter(ms)")
            for psize in sorted(result.keys()):
                brs = result[psize]
                x = [brs[br]["send_pps"]/1e6 for br in sorted(brs)]
                line3 = ax3.plot(x,
                                [brs[br]["jitter"] for br in sorted(brs)],
                                label=f"{psize}", alpha=0.5)
            ax3.legend(title="jitter", frameon=False, prop={'size':8},
                    bbox_to_anchor=(1.11, 0.8), loc="center left")

    fig.tight_layout()
    if opt.save_graph:
        save_graph(opt, "pps")
    if opt.show_graph:
        plt.show()

def make_br_graph(opt):
    """
    to show how much bitrate can be properly used with a certain packet size.
    """
    result = read_result(opt, "br")

    if len(result.keys()) == 1:
        psize = list(result.keys())[0]
        #
        fig = plt.figure()
        fig.suptitle(f"Tx and Rx bitrate, payload size = {psize} B")
        ax1 = fig.add_subplot(1,1,1)

        ax1.set_xlabel("Tx Rate (Mbps)")
        ax1.set_ylabel("Rx Rate (Mbps)")

        brs = result[psize]

        # reference
        x0 = sorted([i/1e6 for i in sorted(brs)])
        line0 = ax1.plot(x0, x0, label="Ref.", color="k", alpha=0.2,
                        linestyle="dashed")

        # result
        lines = []
        x = [brs[br]["send_br"]/1e6 for br in sorted(brs)]
        lines += ax1.plot(x,
                          [brs[br]["recv_br"]/1e6 for br in sorted(brs)],
                          label="Bitrate (bps)",
                          color=plt.cm.viridis(0.2),
                          marker="o",
                          linestyle="solid")
        ax1.set_xlim(0)
        ax1.set_ylim(0)
        print(f"X axes: {ax1.get_xlim()}")
        print(f"Y axes: {ax1.get_ylim()}")
        ax1.grid()

        if opt.with_y2:
            ax2 = ax1.twinx()
            ax2.set_ylabel("Rx Lost (%)")
            ax2.set_ylim(0,100)
            lines += ax2.plot(x,
                            [brs[br]["lost"] for br in sorted(brs)],
                            label="Lost (%)",
                            color=plt.cm.viridis(0.9),
                            alpha=0.5)

            ax3 = ax1.twinx()
            ax3.set_visible(True)
            ax3.set_ylabel("Avr. Jitter (ms)")
            ax3.set_ylim(0,10)
            ax3.spines["right"].set_position(("outward", 50))
            ax3.yaxis.set_label_position('right')
            ax3.yaxis.set_ticks_position('right')
            lines += ax3.plot(x,
                            [brs[br]["jitter"] for br in sorted(brs)],
                            label="Jitter (ms))",
                            color=plt.cm.viridis(0.5),
                            alpha=0.5)

        ax1.legend(handles=lines,
                   bbox_to_anchor=(0.5, 1.1), loc="upper center",
                   ncol=3, frameon=False)

    else:
        fig = plt.figure(figsize=(12,7))
        fig.suptitle(f"Tx and Rx bitrate")
        ax1 = fig.add_subplot(1,1,1)

        ax1.set_xlabel("Tx Rate (Mbps)")
        ax1.set_ylabel("Rx Rate (Mbps)")

        # reference
        brs = []
        for i in result.values():
            brs.extend(i.keys())
        x0 = sorted([i/1e6 for i in sorted(brs)])
        line0 = ax1.plot(x0, x0, label="Ref.", color="k", alpha=0.2,
                        linestyle="dashed")

        for psize in sorted(result.keys()):
            brs = result[psize]
            x = [brs[br]["send_br"]/1e6 for br in sorted(brs)]
            line1 = ax1.plot(x,
                             [brs[br]["recv_br"]/1e6 for br in sorted(brs)],
                             label=f"{psize}",
                             marker="o",
                             linestyle="solid")
            ax1.legend(title="Rx rate", frameon=False, prop={'size':8},
                    bbox_to_anchor=(-.11, 0.8), loc="center right")
        if opt.xlim_max == 0:
            ax1.set_xlim(0)
        else:
            ax1.set_xlim(0,opt.xlim_max)
        if opt.ylim_max == 0:
            ax1.set_ylim(0)
        else:
            ax1.set_ylim(0,opt.ylim_max)
        print(f"X axes: {ax1.get_xlim()}")
        print(f"Y axes: {ax1.get_ylim()}")
        ax1.grid()

        if opt.with_y2:
            ax2 = ax1.twinx()
            ax2.set_ylabel("Rx Lost (%)")
            for psize in sorted(result.keys()):
                brs = result[psize]
                x = [brs[br]["send_br"]/1e6 for br in sorted(brs)]
                line2 = ax2.plot(x,
                                [brs[br]["lost"] for br in sorted(brs)],
                                label=f"{psize}",
                                #alpha=0.5,
                                linestyle="dashed")
                ax2.legend(title="Lost", frameon=False, prop={'size':8},
                        bbox_to_anchor=(1.11, 0.8), loc="center left")
            ax2.set_ylim(0)

    fig.tight_layout()
    if opt.save_graph:
        save_graph(opt, "br")
    if opt.show_graph:
        plt.show()

def make_tx_graph(opt):
    """
    to show status of Tx, to show if Tx transmits the packets properly.
    """
    result = read_result(opt, "br")

    if len(result.keys()) == 1:
        psize = list(result.keys())[0]
        #
        fig = plt.figure()
        fig.suptitle(f"Expected Tx, and real Tx bitrate, payload size = {psize} B")
        ax1 = fig.add_subplot(1,1,1)

        ax1.set_xlabel("Expected Tx Rate (Mbps)")
        ax1.set_ylabel("Measured Tx Rate (Mbps)")

        brs = result[psize]

        # reference
        x0 = sorted([i/1e6 for i in sorted(brs)])
        line0 = ax1.plot(x0, x0, label="Ref.", color="k", alpha=0.2,
                        linestyle="dashed")

        # result
        lines = []
        x = x0
        lines += ax1.plot(x,
                          [brs[br]["send_br"]/1e6 for br in sorted(brs)],
                          label="Bitrate (bps)",
                          color=plt.cm.viridis(0.2),
                          marker="o",
                          linestyle="solid")
        ax1.set_xlim(0)
        ax1.set_ylim(0)
        print(f"X axes: {ax1.get_xlim()}")
        print(f"Y axes: {ax1.get_ylim()}")
        ax1.grid()

    else:
        fig = plt.figure(figsize=(12,7))
        fig.suptitle(f"Expected Tx, and real Tx bitrate")
        ax1 = fig.add_subplot(1,1,1)

        ax1.set_xlabel("Expected Tx Rate (Mbps)")
        ax1.set_ylabel("Measured Tx Rate (Mbps)")

        # reference
        brs = result[list(result)[0]]
        x0 = [i/1e6 for i in sorted(brs)]
        line0 = ax1.plot(x0, x0, label="Ref.", color="k", alpha=0.2,
                        linestyle="dashed")

        for psize in sorted(result.keys()):
            brs = result[psize]
            x = [i/1e6 for i in sorted(brs)]
            line1 = ax1.plot(x,
                             [brs[br]["send_br"]/1e6 for br in sorted(brs)],
                             label=f"{psize}",
                             marker="o",
                             linestyle="solid")
            ax1.legend(title="Rx rate", frameon=False, prop={'size':8},
                    bbox_to_anchor=(-.11, 0.8), loc="center right")

        ax1.set_xlim(0)
        ax1.set_ylim(0)
        print(f"X axes: {ax1.get_xlim()}")
        print(f"Y axes: {ax1.get_ylim()}")
        ax1.grid()

    fig.tight_layout()
    if opt.save_graph:
        save_graph(opt, "br")
    if opt.show_graph:
        plt.show()

br_profile = {
    "1g": "1m,100m,200m,400m,600m,800m,1000m",
    "x1g": "1m,100m,200m,300m,400m,500m,600m,700m,800m,900m,1000m",
    "100m": "1m,20m,40m,60m,80m,100m",
    "x100m": "1m,10m,20m,30m,40m,50m,60m,70m,80m,90m,100m",
    "50m": "1m,10m,20m,30m,40m,50m",
    "x50m": "1m,5m,10m,15m,20m,25m,30m,35m,40m,45m,50m",
    "20m": "1m,4m,8m,12m,16m,20m",
    "x20m": "1m,2m,4m,6m,8m,10m,12m,14m,16m,18m,20m",
    "10m": "1m,2m,4m,6m,8m,10m",
    "x10m": "1m,2m,3m,4m,5m,6m,7m,8m,9m,10m",
    }

def main():
    ap = ArgumentParser(
            description="a utility for iperf3",
            formatter_class=ArgumentDefaultsHelpFormatter,
            epilog="range can be used for specifying "
                "the bitrate and payload size. "
                "The format is like range:<start>,<end>,<inc>.  "
                "For example, --brate range:10m,20m,1m")
    ap.add_argument("server_name", help="server name")
    ap.add_argument("-x", action="store_true", dest="do_test",
                    help="specify to run test.")
    ap.add_argument("--profile", action="store", dest="br_profile",
                    choices=br_profile.keys(),
                    help="specify not to test.")
    ap.add_argument("--brate", metavar="BR_SPEC", action="store",
                    dest="br_list_str",
                    help="specify the list of the bitrate.")
    ap.add_argument("--psize", metavar="PSIZE_SPEC", action="store",
                    dest="psize_list_str",
                    help="specify the list of the payload sizes.")
    ap.add_argument("--reverse", action="store_true", dest="reverse",
                    help="specify to test reversely.")
    ap.add_argument("--parallel", action="store", dest="nb_parallel",
                    type=int, default=1,
                    help="specify the number of parallel clients to run.")
    ap.add_argument("--measure-time", action="store", dest="measure_time",
                    type=int, default=10,
                    help="specify a time to measure one.")
    ap.add_argument("--graph-br", action="store_true", dest="make_br_graph",
                    help="specify to make a br graph.")
    ap.add_argument("--graph-pps", action="store_true", dest="make_pps_graph",
                    help="specify to make a pps graph.")
    ap.add_argument("--graph-tx", action="store_true", dest="make_tx_graph",
                    help="specify to make a Tx graph.")
    ap.add_argument("--graph-y2", action="store_true", dest="with_y2",
                    help="specify to make a graph with the second Y axes.")
    ap.add_argument("--graph-xlim-max", action="store", dest="xlim_max",
                    type=float, default=0,
                    help="specify x max value of the graph.")
    ap.add_argument("--graph-ylim-max", action="store", dest="ylim_max",
                    type=float, default=0,
                    help="specify y max value of the graph.")
    ap.add_argument("--save-dir", action="store", dest="result_dir",
                    help="specify the directory to save the result files.")
    ap.add_argument("--save-graph", "-S",
                    action="store_true", dest="save_graph",
                    help="specify to save the graph. "
                        "can be used with the --save-dir option.")
    ap.add_argument("--no-show-graph", action="store_false", dest="show_graph",
                    help="specify not to show the graph.")
    ap.add_argument("--verbose", action="store_true", dest="verbose",
                    help="enable verbose mode.")
    ap.add_argument("--debug", action="store_true", dest="debug",
                    help="enable debug mode.")
    opt = ap.parse_args()
    # make directory if needed.
    if opt.result_dir is not None and not os.path.exists(opt.result_dir):
        os.mkdir(opt.result_dir)
    # set br_list and psize_list
    opt.br_list = get_test_list(opt.br_list_str,
                                br_profile["100m"] if opt.br_profile is None else
                                br_profile[opt.br_profile])
    opt.psize_list = get_test_list(opt.psize_list_str,
        "16,32,64,128,256,512,768,1024,1280,1448")
    if not (opt.make_br_graph or opt.make_pps_graph or opt.make_tx_graph):
        print("bitrate:",
            ",".join([str(n) for n in opt.br_list]))
        print("payload size:",
            ",".join([str(n) for n in opt.psize_list]))
        t = opt.measure_time * len(opt.br_list) * len(opt.psize_list)
        print(f"measure time: {t} seconds")
    # do measure
    if opt.do_test:
        measure(opt)
    # make a graph.
    if opt.make_br_graph or opt.make_pps_graph or opt.make_tx_graph:
        if opt.br_list_str is None and opt.br_profile is None:
            opt.br_list = "*"
        if opt.psize_list_str is None:
            opt.psize_list = "*"
        print("bitrate:", ",".join([str(n) for n in opt.br_list]))
        print("payload size:", ",".join([str(n) for n in opt.psize_list]))
        if opt.make_br_graph:
            make_br_graph(opt)
        if opt.make_pps_graph:
            make_pps_graph(opt)
        if opt.make_tx_graph:
            make_tx_graph(opt)

if __name__ == "__main__" :
    main()
