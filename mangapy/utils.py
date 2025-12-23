import re


def unpack(p, a, c, k, e=None, d=None):
    def baseN(num, b, numerals="0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        return ((num == 0) and numerals[0]) or (baseN(num // b, b, numerals).lstrip(numerals[0]) + numerals[num % b])

    while c:
        c -= 1
        if k[c]:
            p = re.sub("\\b" + baseN(c, a) + "\\b", k[c], p)
    return p
