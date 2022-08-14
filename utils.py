
from datetime import datetime

def get_ts():
    """
    return a string of timestamp.
    """
    return datetime.now().strftime("%Y%m%d%H%M%S%f")

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

def get_test_list(opt_str, default):
    if opt_str is None:
        opt_str = default
    if opt_str.startswith("range:"):
        start_bw,end_bw,delta_bw = opt_str.removeprefix("range:").split(",")
        return [n for n in range(
                convert_xnum(start_bw),
                convert_xnum(end_bw)+1,
                convert_xnum(delta_bw))]
    else:
        return [convert_xnum(n) for n in opt_str.split(",")]
