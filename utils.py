
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

