"""CSV export helpers with spreadsheet formula-injection protection."""
import csv
import io

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _DANGEROUS:
        return "'" + s
    return s


def to_csv(header, rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([safe_cell(h) for h in header])
    for r in rows:
        w.writerow([safe_cell(v) for v in r])
    return buf.getvalue()
