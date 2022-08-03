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

#
# measurement
#

def convert_xnum(n):
    if n.find(".") > 0:
        # float
        try:
            return float(n)
        except ValueError:
            if n[-1] in ["k", "K"]:
                return float(n[:-1])*1E3
            elif n[-1] in ["m", "M"]:
                return float(n[:-1])*1E6
            elif n[-1] in ["g", "G"]:
                return float(n[:-1])*1E9
    else:
        # int
        try:
            return int(n)
        except ValueError:
            if n[-1] in ["k", "K"]:
                return round(int(n[:-1])*1E3)
            elif n[-1] in ["m", "M"]:
                return round(int(n[:-1])*1E6)
            elif n[-1] in ["g", "G"]:
                return round(int(n[:-1])*1E9)

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

def measure_bw(opt):
    cmd_fmt = "iperf3 -u -c {name} -P {nb_parallel} -b {{bw}} -l {size}".format(**{
            "name": opt.server_name,
            "nb_parallel": opt.nb_parallel,
            "size": opt.psize})
    ofile_fmt = "{path}iperf-{name}-{dir}-bw-{{bw}}-ps-{psize}-{{id}}.txt".format(**{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr",
            "psize": opt.psize})
    if opt.reverse:
        cmd_fmt += " -R"
    for bw in opt.bw_list:
        cmd = cmd_fmt.format(**{"bw":bw})
        print(cmd)
        output_file = ofile_fmt.format(**{
                "bw": bw,
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f")
                })
        iperf(cmd, output_file)

def measure_pps(opt):
    cmd_fmt = "iperf3 -u -c {name} -P {nb_parallel} -b {bw} -l {{size}}".format(**{
            "name": opt.server_name,
            "nb_parallel": opt.nb_parallel,
            "bw": opt.target_bw})
    ofile_fmt = "{path}iperf-{name}-{dir}-bw-{bw}-ps-{{size}}-{{id}}.txt".format(**{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr",
            "bw": opt.target_bw})
    if opt.reverse:
        cmd_fmt += " -R"
    for size in opt.psize_list:
        cmd = cmd_fmt.format(**{"size":size})
        print(cmd)
        output_file = ofile_fmt.format(**{
                "size": size,
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f")
                })
        iperf(cmd, output_file)

#
# graph
#
re_cmdline = re.compile(
        "% iperf3 -u "
        "-c (?P<host>[^\s]+) "
        "-P (?P<nb_parallel>\d+) "
        "-b (?P<bw>\d+)(?P<bw_unit>(|[MKGmkg])) "
        "-l (?P<psize>\d+)"
        ".*")
re_begin = re.compile("^\[\s*ID]\s*Interval\s+.*Lost/Total Datagrams")
re_result = re.compile(
        "^\[\s*\d+\]\s*"
        "(?P<start>[\d\.]+)-(?P<end>[\d\.]+)\s+sec\s+"
        "(?P<transfer>[\d\.]+)\s+(?P<transfer_unit>(|[MKG]))Bytes\s+"
        "(?P<bitrate>[\d\.]+)\s+(?P<bitrate_unit>(|[MKG]))bits/sec\s+"
        "(?P<jitter>[\d\.]+)\s+ms\s+"
        "(?P<lost>[\d\.]+)/(?P<total>[\d\.]+)\s+"
        "\((?P<loss_rate>[\d\.]+)%\)\s+"
        "(?P<role>sender|receiver)"
        ".*")

def read_file(file_name):
    lines = open(file_name).read().splitlines()
    line_no = 0
    for i,line in enumerate(lines):
        if (r := re_begin.match(line)) is not None:
            line_no = i
            break
    else:
        raise ValueError(f"invalid structure, {file_name}")
    #
    result = {"sender":None, "receiver":None}
    if (r := re_cmdline.match(lines[0])) is not None:
        psize = int(r.group("psize"))
        target_bw = convert_xnum(f'{r.group("bw")}{r.group("bw_unit")}')
    else:
        raise ValueError(f"invalid cmdline, {file_name}")
    if (r := re_result.match(lines[line_no+1])) is not None:
        if r.group("role") != "sender":
            raise ValueError(f'invalid role {r.group("role")}, {file_name}')
        result["sender"] = {
                "start": float(r.group("start")),
                "end": float(r.group("end")),
                "bytes_sent": convert_xnum(
                        f'{r.group("transfer")}{r.group("transfer_unit")}'),
                "bps": convert_xnum(
                        f'{r.group("bitrate")}{r.group("bitrate_unit")}'),
                "jitter_ms": float(r.group("jitter")),
                "lost": int(r.group("lost")),
                "packets_sent": int(r.group("total")),
                "lost_percent": float(r.group("loss_rate")),
                "payload_size": psize,
                "target_bw": target_bw,
                }
    else:
        raise ValueError(f"invalid structure, {file_name}")
    if (r := re_result.match(lines[line_no+2])) is not None:
        if r.group("role") != "receiver":
            raise ValueError(f'invalid role {r.group("role")}, {file_name}')
        result["receiver"] = {
                "start": float(r.group("start")),
                "end": float(r.group("end")),
                "bytes_received": convert_xnum(
                        f'{r.group("transfer")}{r.group("transfer_unit")}'),
                "bps": convert_xnum(
                        f'{r.group("bitrate")}{r.group("bitrate_unit")}'),
                "jitter_ms": float(r.group("jitter")),
                "lost": int(r.group("lost")),
                "packets_received": int(r.group("total")),
                "lost_percent": float(r.group("loss_rate")),
                }
    else:
        raise ValueError(f"invalid structure, {file_name}")
    return result

def print_result(result):
    column_size = [8,8,8,6,6,6]
    fmt = " ".join([f"{{:{n}}}" for n in column_size])
    print(fmt.format(
            "Tgt BW", "Snd BW", "PL Size", "Rcv BW", "lost%", "jitter"))
    print(" ".join(["-"*n for n in column_size]))
    for i in range(len(result["base_psize"])):
        print(fmt.format(
                round(result["target_bw"][i]/1e6,2),
                round(result["sender_bps"][i]/1e6,2),
                result["base_psize"][i],
                round(result["receiver_bps"][i]/1e6,2),
                round(result["lost_percent"][i],3),
                round(result["jitter_ms"][i],3)))

def read_result(file_list, key_no):
    """
    files:
        e.g.
        [
            "iperf-host-sr-bw-1000000-20210723164951001895.txt", 
            "iperf-host-sr-bw-1000000-20210723165001092010.txt",
            "iperf-host-sr-bw-2000000-20210723165021187028.txt", 
            "iperf-host-sr-bw-2000000-20210723165041727012.txt"
        ]
        e.g.
        [
            "iperf-host-sr-bw-940m-ps-512-20220803082844970472.txt
            "iperf-host-sr-bw-940m-ps-768-20220803082855012590.txt
            "iperf-host-sr-bw-940m-ps-256-20220803082834938697.txt
            "iperf-host-sr-bw-940m-ps-1024-20220803082905049313.txt
            "iperf-host-sr-bw-940m-ps-32-20220803082804841190.txt
        ]
    """
    result = {
            "target_bw": [],
            "base_psize": [],
            "sender_bps": [],
            "receiver_bps": [],
            "lost_percent": [],
            "jitter_ms": []
            }
    if len(file_list) == 0:
        raise ValueError("ERROR: the target file list is empty.")
    # init
    prev_key = None
    target_bw = None
    target_psize = None
    sender_bps = 0
    receiver_bps = 0
    lost_percent = 0
    jitter_ms = 0
    n = 0
    # loop
    def __get_key(file_name):
        basename = os.path.basename(file_name)
        return convert_xnum(basename[:basename.find(".txt")].split("-")[key_no])
    for file_name in sorted(file_list, key=lambda v: __get_key(v)):
        x = read_file(file_name)
        key = __get_key(file_name)
        if prev_key is not None and prev_key != key:
            result["target_bw"].append(target_bw)
            result["base_psize"].append(target_psize)
            result["sender_bps"].append(sender_bps/n)
            result["receiver_bps"].append(receiver_bps/n)
            result["lost_percent"].append(lost_percent/n)
            result["jitter_ms"].append(jitter_ms/n)
            # init
            target_bw = None
            target_psize = None
            sender_bps = 0
            receiver_bps = 0
            lost_percent = 0
            jitter_ms = 0
            n = 0
        #
        prev_key = key
        target_bw = x["sender"]["target_bw"]
        target_psize = x["sender"]["payload_size"]
        sender_bps += x["sender"]["bps"]
        receiver_bps += x["receiver"]["bps"]
        lost_percent += x["receiver"]["lost_percent"]
        jitter_ms += x["receiver"]["jitter_ms"]
        n += 1
    # final
    result["target_bw"].append(target_bw)
    result["base_psize"].append(target_psize)
    result["sender_bps"].append(sender_bps/n)
    result["receiver_bps"].append(receiver_bps/n)
    result["lost_percent"].append(lost_percent/n)
    result["jitter_ms"].append(jitter_ms/n)
    return result

def read_bw_result(opt):
    fmt = "{path}iperf-{name}-{dir}-bw-{{bw}}-ps-{psize}-*.txt".format(**{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr",
            "psize": opt.psize})
    if opt.bw_list is not None:
        file_list = []
        for bw in opt.bw_list:
            file_list.extend(glob.glob(fmt.format(**{"bw":bw})))
    else:
        file_list = glob.glob(fmt.format(**{"bw":"*"}))
    return read_result(file_list, key_no=4 if opt.make_bw_graph else 6)

def read_pps_result(opt):
    fmt = "{path}iperf-{name}-{dir}-bw-{bw}-ps-{{psize}}-*.txt".format(**{
            "path": f"{opt.result_dir}/" if opt.result_dir else "",
            "name": opt.server_name,
            "dir": "rs" if opt.reverse else "sr",
            "bw": opt.target_bw})
    if opt.psize_list:
        file_list = []
        for psize in opt.psize_list:
            file_list.append(fmt.format(**{"psize":psize}))
    else:
        file_list = glob.glob(fmt.format(**{"psize":"*"}))
    return read_result(file_list, key_no=4 if opt.make_bw_graph else 6)

def save_graph(opt):
    if opt.make_bw_graph:
        ofile = "{path}iperf-{name}-{dir}-bw-ps-{psize}.png".format(**{
                "path": f"{opt.result_dir}/" if opt.result_dir else "",
                "name": opt.server_name,
                "dir": "rs" if opt.reverse else "sr",
                "psize": opt.psize})
        plt.savefig(ofile)
    if opt.make_pps_graph:
        ofile = "{path}iperf-{name}-{dir}-bw-{bw}-ps.png".format(**{
                "path": f"{opt.result_dir}/" if opt.result_dir else "",
                "name": opt.server_name,
                "dir": "rs" if opt.reverse else "sr",
                "bw": opt.target_bw})
        plt.savefig(ofile)

def make_bw_graph(opt):
    result = read_bw_result(opt)
    print_result(result)
    fig = plt.figure()
    fig.suptitle("BW: {}".format("server to client" if opt.reverse else "client to server"))
    ax = fig.add_subplot(1,1,1)
    ax.set_xlabel("Sender Bandwidth(Mbps)")

    line0 = ax.plot(result["target_bw"], result["target_bw"],
                    label="bps", color="k", alpha=0.2)

    line1 = ax.plot(result["sender_bps"], result["receiver_bps"],
                    label="bps", color="#d55e00")
    ax.set_ylabel("Receiver (bps)", color=line1[0].get_color())

    ax2 = ax.twinx()
    line2 = ax2.plot(result["sender_bps"], result["lost_percent"],
                     label="lost%", color="#f0e442")
    ax2.set_ylabel("Lost%", color=line2[0].get_color())

    ax3 = ax.twinx()
    line3 = ax3.plot(result["sender_bps"], result["jitter_ms"],
                     label="jitter", color="#009e73", alpha=0.5)
    ax3.set_ylabel("Jitter(ms)", color=line3[0].get_color())
    ax3.spines["right"].set_position(("outward", 50))

    ax.grid()
    fig.tight_layout()
    if opt.save_graph:
        save_graph(opt)
    if opt.show_graph:
        plt.show()

def make_pps_graph(opt):
    result = read_pps_result(opt)
    print_result(result)
    fig = plt.figure()
    fig.suptitle("PPS {}Mbps: {}".format(
            result["target_bw"][0]/1e6,
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

    ax.grid()
    fig.tight_layout()
    if opt.save_graph:
        save_graph(opt)
    if opt.show_graph:
        plt.show()

def get_test_list(measure, opt_str, default):
    if not measure and opt_str is None:
        return None
    if measure and opt_str is None:
        opt_str = default
    if opt_str.startswith("range:"):
        start_bw,end_bw,delta_bw = opt_str.removeprefix("range:").split(",")
        return [n for n in range(
                convert_xnum(start_bw),
                convert_xnum(end_bw)+1,
                convert_xnum(delta_bw))]
    else:
        return [convert_xnum(n) for n in opt_str.split(",")]

def main():
    ap = ArgumentParser(
            description="a utility for iperf3",
            formatter_class=ArgumentDefaultsHelpFormatter)
    ap.add_argument("server_name", help="server name")
    ap.add_argument("--measure-bw", action="store_true", dest="measure_bw",
                    help="specify to measure bandwidth.")
    ap.add_argument("--psize", action="store", dest="psize",
                    type=int, default=1448,
                    help="specify the payload size for the --measure-bw option.")
    ap.add_argument("--bw-list", metavar="BW_SPEC", action="store",
                    dest="bw_list_str",
                    help="specify the list of the bandwidths "
                        "for the --measure-bw option.")
    ap.add_argument("--measure-pps", action="store_true", dest="measure_pps",
                    help="specify to measure pps.")
    ap.add_argument("--psize-list", metavar="PSIZE_SPEC", action="store",
                    dest="psize_list_str",
                    help="specify the list of the packet sizes to be sent.")
    ap.add_argument("--target-bw", action="store", dest="target_bw",
                    help="specify the number of the target bandwidth "
                        "with the --measure-pps option.")
    ap.add_argument("--reverse", action="store_true", dest="reverse",
                    help="specify to measure reversely.")
    ap.add_argument("--parallel", action="store", dest="nb_parallel",
                    type=int, default=1,
                    help="specify the number of parallel clients to run.")
    ap.add_argument("--graph-bw", action="store_true", dest="make_bw_graph",
                    help="specify to make a bw graph.")
    ap.add_argument("--graph-pps", action="store_true", dest="make_pps_graph",
                    help="specify to make a pps graph.")
    ap.add_argument("--save-dir", action="store", dest="result_dir",
                    help="specify the directory to save the result files.")
    ap.add_argument("--save-graph", action="store_true", dest="save_graph",
                    help="specify to save the graph. can be used with the --save-dir option.")
    ap.add_argument("--no-show-graph", action="store_false", dest="show_graph",
                    help="specify not to show the graph.")
    opt = ap.parse_args()
    # make directory if needed.
    if opt.result_dir is not None and not os.path.exists(opt.result_dir):
        os.mkdir(opt.result_dir)
    # set bw list
    opt.bw_list = get_test_list(
            opt.measure_bw, opt.bw_list_str,
            "1m,10m,20m,40m,60m,80m,100m")
    # set psize list
    opt.psize_list = get_test_list(
            opt.measure_pps, opt.psize_list_str,
            "16,32,64,128,256,512,768,1024,1280,1448")
    #
    if opt.measure_bw:
        print("bandwidth test list:",
              ",".join([str(n) for n in opt.bw_list]))
        measure_bw(opt)
    if opt.make_bw_graph:
        if opt.bw_list is not None:
            print("bandwidth test list:",
                ",".join([str(n) for n in opt.bw_list]))
        else:
            print("bandwidth test list: all")
        make_bw_graph(opt)
    if opt.measure_pps:
        if opt.target_bw is None:
            print("ERROR: the --target-bw is required to measure the pps.")
            exit(-1)
        print("Target BW:", opt.target_bw)
        print("packet size test list:",
              ",".join([str(n) for n in opt.psize_list]))
        measure_pps(opt)
    if opt.make_pps_graph:
        if opt.psize_list is not None:
            print("packet size test list:",
                ",".join([str(n) for n in opt.psize_list]))
        else:
            print("packet size test list: all")
        make_pps_graph(opt)

if __name__ == "__main__" :
    try:
        main()
    except Exception as e:
        print(e)
