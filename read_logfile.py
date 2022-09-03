import re
from utils import convert_xnum

"""
file name:
    e.g. iperf-host-sr-bw-940m-ps-512-20220803082844970472.txt
"""
re_cmdline = re.compile(
        "% iperf3 -u "
        "-c (?P<host>[^\s]+) "
        "-P (?P<nb_parallel>\d+) "
        "(-t (?P<time>\d+) )?"
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
        "\((?P<loss_rate>.+)%\)\s+"
        "(?P<role>sender|receiver)"
        ".*")
# assuming the span of each test is 1 sencond.
# [  5]   0.00-1.00   sec  1.22 MBytes  10.2 Mbits/sec
re_tcp_line = re.compile(
        "^\[\s*\d+\]\s*"
        "(?P<start>[\d\.]+)-(?P<end>[\d\.]+)\s+sec\s+"
        "(?P<transfer>[\d\.]+)\s+(?P<transfer_unit>(|[MKG]))Bytes\s+"
        "(?P<bitrate>[\d\.]+)\s+(?P<bitrate_unit>(|[MKG]))bits/sec\s+"
        )
# assuming the span of each test is 1 sencond.
# 64 bytes from 1.1.1.1: icmp_seq=109 ttl=63 time=2.196 ms
re_ping_line = re.compile(
        "^(?P<size>\d+) "
        "bytes from [\d\.a-fA-F:]+: "
        "icmp_seq=(?P<seq>\d+) "
        "ttl=(?P<ttl>\d+) "
        "time=(?P<rtt>[\d\.]+) ms"
        )

# parsing the iperf_util output.
def parse_log(lines, file_name="..."):
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

def read_logfile(file_name):
    return parse_log(open(file_name).read().splitlines(), file_name)

def parse_tcp_log(lines, file_name="..."):
    result = []
    line_no = 0
    for i,line in enumerate(lines):
        if (r := re_tcp_line.match(line)) is not None:
            result.append({
                    "start": float(r.group("start")),
                    "end": float(r.group("end")),
                    "bytes_sent": convert_xnum(
                            f'{r.group("transfer")}{r.group("transfer_unit")}'),
                    "bps": convert_xnum(
                            f'{r.group("bitrate")}{r.group("bitrate_unit")}'),
                    })
    return result

def read_tcp_logfile(file_name):
    return parse_tcp_log(open(file_name).read().splitlines(), file_name)

def parse_ping_log(lines, file_name="..."):
    result = []
    line_no = 0
    for i,line in enumerate(lines):
        if (r := re_ping_line.match(line)) is not None:
            result.append({
                    "size": int(r.group("size")),
                    "seq": int(r.group("seq")),
                    "ttl": int(r.group("ttl")),
                    "rtt": float(r.group("rtt")),
                    })
    return result

def read_ping_logfile(file_name):
    return parse_ping_log(open(file_name).read().splitlines(), file_name)

if __name__ == "__main__":
    # test
    import sys
    import json
    testv = [
            [ """
% iperf3 -u -c 192.168.0.102 -P 1 -b 940m -l 1000 --logfile $d/128-$b.txt
[  6] local 192.168.0.103 port 65131 connected to 192.168.0.102 port 5201
[ ID] Interval           Transfer     Bitrate         Total Datagrams
[  6]   0.00-1.00   sec  1.62 KBytes  13.3 Kbits/sec  13  
[  6]   1.00-2.00   sec  1.50 KBytes  12.3 Kbits/sec  12  
[  6]   2.00-3.00   sec  1.62 KBytes  13.3 Kbits/sec  13  
[  6]   3.00-4.00   sec  1.50 KBytes  12.3 Kbits/sec  12  
[  6]   4.00-5.00   sec  1.62 KBytes  13.3 Kbits/sec  13  
[  6]   5.00-6.00   sec  1.50 KBytes  12.3 Kbits/sec  12  
[  6]   6.00-7.00   sec  1.62 KBytes  13.3 Kbits/sec  13  
[  6]   7.00-8.00   sec  1.50 KBytes  12.3 Kbits/sec  12  
[  6]   8.00-9.00   sec  1.62 KBytes  13.3 Kbits/sec  13  
[  6]   9.00-10.00  sec  1.50 KBytes  12.3 Kbits/sec  12  
- - - - - - - - - - - - - - - - - - - - - - - - -
[ ID] Interval           Transfer     Bitrate         Jitter    Lost/Total Datagrams
[  6]   0.00-10.00  sec  15.6 KBytes  12.8 Kbits/sec  0.000 ms  0/125 (0%)  sender
[  6]   0.00-10.00  sec  15.6 KBytes  12.8 Kbits/sec  0.818 ms  0/125 (0%)  receiver

iperf Done.
    """,
    """
{
    "sender": {
        "start": 0.0,
        "end": 10.0,
        "bytes_sent": 15600.0,
        "bps": 12800.0,
        "jitter_ms": 0.0,
        "lost": 0,
        "packets_sent": 125,
        "lost_percent": 0.0,
        "payload_size": 1000,
        "target_bw": 940000000
    },
    "receiver": {
        "start": 0.0,
        "end": 10.0,
        "bytes_received": 15600.0,
        "bps": 12800.0,
        "jitter_ms": 0.818,
        "lost": 0,
        "packets_received": 125,
        "lost_percent": 0.0
    }
}
    """ ],
            [ """
% iperf3 -u -c 192.168.0.102 -P 1 -t 10 -b 1000000 -l 16
[  5] local 192.168.0.103 port 62049 connected to 192.168.0.102 port 5201
[ ID] Interval           Transfer     Bitrate         Total Datagrams
[  5]   0.00-1.00   sec   122 KBytes   999 Kbits/sec  7808  
[  5]   1.00-2.00   sec   122 KBytes  1.00 Mbits/sec  7813  
[  5]   2.00-3.00   sec   122 KBytes  1000 Kbits/sec  7812  
[  5]   3.00-4.00   sec   122 KBytes  1000 Kbits/sec  7812  
[  5]   4.00-5.00   sec   122 KBytes  1000 Kbits/sec  7811  
[  5]   5.00-6.00   sec   122 KBytes  1.00 Mbits/sec  7814  
[  5]   6.00-7.00   sec   122 KBytes  1.00 Mbits/sec  7813  
[  5]   7.00-8.00   sec   122 KBytes  1000 Kbits/sec  7812  
[  5]   8.00-9.00   sec   122 KBytes  1.00 Mbits/sec  7813  
[  5]   9.00-10.00  sec   122 KBytes  1.00 Mbits/sec  7812  
- - - - - - - - - - - - - - - - - - - - - - - - -
[ ID] Interval           Transfer     Bitrate         Jitter    Lost/Total Datagrams
[  5]   0.00-10.00  sec  1.19 MBytes  1000 Kbits/sec  0.000 ms  0/78120 (0%)  sender
[  5]   0.00-10.00  sec  1.19 MBytes  1000 Kbits/sec  0.073 ms  0/78120 (0%)  receiver

iperf Done.
    """,
    """
{
    "sender": {
        "start": 0.0,
        "end": 10.0,
        "bytes_sent": 1190000.0,
        "bps": 1000000,
        "jitter_ms": 0.0,
        "lost": 0,
        "packets_sent": 78120,
        "lost_percent": 0.0,
        "payload_size": 16,
        "target_bw": 1000000
    },
    "receiver": {
        "start": 0.0,
        "end": 10.0,
        "bytes_received": 1190000.0,
        "bps": 1000000,
        "jitter_ms": 0.073,
        "lost": 0,
        "packets_received": 78120,
        "lost_percent": 0.0
    }
}
    """ ],
    ]
    if len(sys.argv) > 1:
        if sys.argv[1] == "tcp":
            print(json.dumps(parse_tcp_log(open(sys.argv[2]).read()
                                           .splitlines()), indent=4))
        else:
            print(json.dumps(parse_log(open(sys.argv[1]).read().splitlines()), indent=4))
    else:
        for t in testv:
            r = parse_log(t[0].splitlines()[1:])
            print(json.dumps(r, indent=4))
            print(r == json.loads(t[1]))
