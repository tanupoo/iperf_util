#!/usr/bin/env python

from subprocess import Popen, DEVNULL, PIPE
import shlex
import matplotlib.pyplot as plt
import glob
import os
from datetime import datetime
import re
from argparse import ArgumentParser
from argparse import ArgumentDefaultsHelpFormatter
from utils import convert_xnum, get_test_list
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
    print("bandwidth:",
            ",".join([str(n) for n in opt.bw_list]))
    print("payload size:",
            ",".join([str(n) for n in opt.psize_list]))
    cmd_fmt = "iperf3 -u -c {name} -P {nb_parallel} -b {{bw}} -l {{psize}}".format(**{
            "name": opt.server_name,
            "nb_parallel": opt.nb_parallel})
    ofile_fmt = "{path}iperf-{name}-{dir}-bw-{{bw}}-ps-{{psize}}-{{id}}.txt".format(**{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr"})
    if opt.reverse:
        cmd_fmt += " -R"
    for bw in opt.bw_list:
        for psize in opt.psize_list:
            cmd = cmd_fmt.format(**{"bw":bw, "psize":psize})
            print(cmd)
            output_file = ofile_fmt.format(**{
                    "bw": bw,
                    "psize": psize,
                    "id": datetime.now().strftime("%Y%m%d%H%M%S%f")
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
                bw = k2
                psize = k1
            else:
                bw = k1
                psize = k2
            print(fmt.format(
                round(bw/1e6,2),
                psize,
                round(d["send_br"]/1e6,2),
                round(d["recv_br"]/1e6,2),
                round(d["send_pps"]/1e6,2),
                round(d["recv_pps"]/1e6,2),
                round(d["lost"],3),
                round(d["jitter"],3)))

def read_result(opt, x_axis):
    assert x_axis in ["br", "psize"]
    template = "{path}iperf-{name}-{dir}-bw-{{bw}}-ps-{{psize}}-*.txt".format(
            **{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr"
            })
    base_list = []
    for bw in opt.bw_list:
        for psize in opt.psize_list:
            glob_name = template.format(**{"bw": bw, "psize": psize})
            base_list.extend(glob.glob(glob_name))
    result = {}
    for fname in base_list:
        r = re.match(".*iperf-"
                     "[^-]+-"
                     "[^-]+-"
                     "bw-([^-]+)-"
                     "ps-([^-]+)-"
                     ".*.txt", fname)
        if r:
            if x_axis == "br":
                k1 = r.group(2) # psize
                k2 = r.group(1) # bw
            else:
                k1 = r.group(1) # bw
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

def save_graph(opt):
    if opt.make_bw_graph:
        ofile = "{path}iperf-{name}-{dir}-bw.png".format(**{
                "path": f"{opt.result_dir}/" if opt.result_dir else "",
                "name": opt.server_name,
                "dir": "rs" if opt.reverse else "sr"})
        plt.savefig(ofile)
    if opt.make_psize_graph:
        ofile = "{path}iperf-{name}-{dir}-psize.png".format(**{
                "path": f"{opt.result_dir}/" if opt.result_dir else "",
                "name": opt.server_name,
                "dir": "rs" if opt.reverse else "sr"})
        plt.savefig(ofile)

def make_pps_graph(opt):
    result = read_result(opt, "br")

    fig = plt.figure()
    fig.suptitle(f"M BW")
    ax = fig.add_subplot(1,1,1)
    """
    # reference
    x0 = sorted([i/1e6 for i in sorted(result[list(result.keys())[0]])])
    line0 = ax.plot(x0, x0, label="tx_br", color="k", alpha=0.2,
                    linestyle="dashed")
    """

    ax.set_xlabel("Tx PPS")
    ax.set_ylabel("Rx Lost (%)")
    for psize in sorted(result.keys()):
        brs = result[psize]
        line1 = ax.plot([brs[br]["send_pps"]/1e6 for br in sorted(brs)],
                        [brs[br]["lost"]/1e6 for br in sorted(brs)],
                        label=f"{psize}")
    plt.legend()

    ax.grid()
    fig.tight_layout()
    if opt.save_graph:
        save_graph(opt)
    if opt.show_graph:
        plt.show()

def make_bw_graph(opt):
    result = read_result(opt, "br")

    if len(result.keys()) == 1:
        psize = list(result.keys())[0]
        brs = result[psize]
        #
        fig = plt.figure()
        fig.suptitle(f"{psize} B")
        ax = fig.add_subplot(1,1,1)
        # reference
        x0 = sorted([i/1e6 for i in sorted(brs)])
        line0 = ax.plot(x0, x0, label="tx_br", color="k", alpha=0.2,
                        linestyle="dashed")
        ax.set_xlabel("Tx Rate (Mbps)")

        x = [brs[br]["send_br"]/1e6 for br in sorted(brs)]

        line1 = ax.plot(x,
                        [brs[br]["recv_br"]/1e6 for br in sorted(brs)],
                        label="rx_br", color="#d55e00",
                        marker="o",
                        linestyle="solid")
        ax.set_ylabel("Rx Rate (Mbps)", color=line1[0].get_color())

        ax2 = ax.twinx()
        line2 = ax2.plot(x,
                        [brs[br]["lost"] for br in sorted(brs)],
                        label="lost%", color="#f0e442")
        ax2.set_ylabel("Lost%", color=line2[0].get_color())

        ax3 = ax.twinx()
        line3 = ax3.plot(x,
                        [brs[br]["jitter"] for br in sorted(brs)],
                        label="jitter", color="#009e73", alpha=0.5)
        ax3.set_ylabel("Jitter(ms)", color=line3[0].get_color())
        ax3.spines["right"].set_position(("outward", 50))

        ax4 = ax.twinx()
        line4 = ax4.plot(x,
                        [brs[br]["recv_pps"] for br in sorted(brs)],
                        label="pps", color="#d022d5", alpha=0.5)
        ax4.spines["left"].set_visible(True)
        ax4.spines["left"].set_position(("outward", 50))
        ax4.yaxis.set_label_position('left')
        ax4.yaxis.set_ticks_position('left')
        ax4.set_ylabel("pps", color=line4[0].get_color())

    else:
        fig = plt.figure()
        fig.suptitle(f"M BW")
        ax = fig.add_subplot(1,1,1)
        # reference
        x0 = sorted([i/1e6 for i in sorted(result[list(result.keys())[0]])])
        line0 = ax.plot(x0, x0, label="tx_br", color="k", alpha=0.2,
                        linestyle="dashed")
        ax.set_xlabel("Tx Rate (Mbps)")

        for psize in sorted(result.keys()):
            brs = result[psize]
            x = [brs[br]["send_br"]/1e6 for br in sorted(brs)]
            """
            line0 = ax.plot(x0, x0,
                            label=f"send_br_{psize}", color="k", alpha=0.2)
            """

            line1 = ax.plot([brs[br]["send_br"]/1e6 for br in sorted(brs)],
                            [brs[br]["recv_br"]/1e6 for br in sorted(brs)],
                            label=f"recv_br_{psize}")
            ax.set_ylabel("Rx Rate (Mbps)", color=line1[0].get_color())
        plt.legend()

    ax.grid()
    fig.tight_layout()
    if opt.save_graph:
        save_graph(opt)
    if opt.show_graph:
        plt.show()

def make_psize_graph(opt):
    result = read_result(opt, "psize")

    if len(result.keys()) == 1:
        bw = list(result.keys())[0]
        pss = result[bw]
        #
        fig = plt.figure()
        fig.suptitle("PPS {}Mbps: {}".format(
                result["target_br"][0]/1e6,
                "server to client" if opt.reverse else "client to server"))
        ax = fig.add_subplot(1,1,1)
        ax.set_xlabel("Packet Size(bytes)")

        line1 = ax.plot(result["base_psize"], result["receiver_bps"],
                        label="bps", color="#d55e00")
        ax.set_ylabel("Receiver (bps)", color=line1[0].get_color())

        ax2 = ax.twinx()
        line2 = ax2.plot(result["base_psize"], result["lost_percent"],
                        label="lost%", color="#f0e442")
        ax2.set_ylabel("Lost%", color=line2[0].get_color())

        ax3 = ax.twinx()
        line3 = ax3.plot(result["base_psize"], result["jitter_ms"],
                        label="jitter", color="#009e73", alpha=0.5)
        ax3.set_ylabel("Jitter(ms)", color=line3[0].get_color())
        ax3.spines["right"].set_position(("outward", 50))
    else:
        raise NotImplemented("ERROR")

    ax.grid()
    fig.tight_layout()
    if opt.save_graph:
        save_graph(opt)
    if opt.show_graph:
        plt.show()

bw_profile = {
    "1g": "1m,100m,200m,400m,600m,700m,800m,900m,1000m",
    "100m": "1m,10m,20m,40m,60m,70m,80m,90m,100m",
    "50m": "1m,10m,20m,30m,35m,40m,45m,50m",
    "10m": "1m,2m,4m,6m,7m,8m,9m,10m",
    }

def main():
    ap = ArgumentParser(
            description="a utility for iperf3",
            formatter_class=ArgumentDefaultsHelpFormatter)
    ap.add_argument("server_name", help="server name")
    ap.add_argument("--profile", action="store", dest="bw_profile",
                    choices=["1g","100m","50m","10m"],
                    default="100m",
                    help="specify not to test.")
    ap.add_argument("--bw-list", metavar="BW_SPEC", action="store",
                    dest="bw_list_str",
                    help="specify the list of the bandwidths.")
    ap.add_argument("--psize-list", metavar="PSIZE_SPEC", action="store",
                    dest="psize_list_str",
                    help="specify the list of the payload sizes.")
    ap.add_argument("--reverse", action="store_true", dest="reverse",
                    help="specify to test reversely.")
    ap.add_argument("--parallel", action="store", dest="nb_parallel",
                    type=int, default=1,
                    help="specify the number of parallel clients to run.")
    ap.add_argument("--graph-bw", action="store_true", dest="make_bw_graph",
                    help="specify to make a bw graph.")
    ap.add_argument("--graph-psize", action="store_true", dest="make_psize_graph",
                    help="specify to make a psize graph.")
    ap.add_argument("--graph-pps", action="store_true", dest="make_pps_graph",
                    help="specify to make a pps graph.")
    ap.add_argument("-x", action="store_true", dest="enable_test",
                    help="specify to run test. it's for use of graph mode.")
    ap.add_argument("--save-dir", action="store", dest="result_dir",
                    help="specify the directory to save the result files.")
    ap.add_argument("--save-graph", action="store_true", dest="save_graph",
                    help="specify to save the graph. can be used with the --save-dir option.")
    ap.add_argument("--no-show-graph", action="store_false", dest="show_graph",
                    help="specify not to show the graph.")
    ap.add_argument("--verbose", action="store_true", dest="verbose",
                    help="enable verbose mode.")
    opt = ap.parse_args()
    # make directory if needed.
    if opt.result_dir is not None and not os.path.exists(opt.result_dir):
        os.mkdir(opt.result_dir)
    # set bw_list and psize_list
    opt.bw_list = get_test_list(opt.bw_list_str,
        bw_profile[opt.bw_profile])
    opt.psize_list = get_test_list(opt.psize_list_str,
        "16,32,64,128,256,512,768,1024,1280,1448")
    # do measure
    if not(opt.make_bw_graph or opt.make_psize_graph or opt.make_pps_graph) or opt.enable_test:
        measure(opt)
    # make a graph.
    if opt.make_bw_graph or opt.make_psize_graph or opt.make_pps_graph:
        if opt.bw_list_str is None:
            opt.bw_list = "*"
        if opt.psize_list_str is None:
            opt.psize_list = "*"
        print("bandwidth:",
            ",".join([str(n) for n in opt.bw_list]))
        print("payload size:",
            ",".join([str(n) for n in opt.psize_list]))
        if opt.make_bw_graph:
            make_bw_graph(opt)
        if opt.make_psize_graph:
            make_psize_graph(opt)
        if opt.make_pps_graph:
            make_pps_graph(opt)

if __name__ == "__main__" :
    main()
