"""Natural ordering for numeric values, IP addresses and labels."""
import ipaddress
import re


def sort_key(value):
    text = str(value).strip()
    try:
        ip = ipaddress.ip_address(text)
        return (1, ip.version, int(ip))
    except ValueError:
        pass
    if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', text):
        return (0, float(text))
    return (2, tuple((0,int(part)) if part.isdigit() else (1,part.casefold()) for part in re.split(r'(\d+)', text)))
