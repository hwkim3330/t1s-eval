#!/usr/bin/env python3
"""Where does an overloaded T1S stream stop? Run against a live :8813 console.

    python3 pc/t1s_console/overload_probe.py docs/t1s_results/duo_suite_<ts>.json

ESP-B blasts the HAT unpaced (above the bus ceiling). Before and after, the HAT reports its TC6
STATUS0/1 (RX buffer overflow and error flags), the receive chunks still inside the LAN8651, and
the frames its driver handed up. If the LAN8651 shows no overflow, no pending chunks, and its
driver count equals what the sink got, the missing frames never reached the chip: the stall is
upstream, in the converter. Stores the result under "overload_probe" in the suite JSON.
"""
import json
import re
import sys
import time
import urllib.request

BASE = "http://localhost:8813"
A, B = "esp-28:84:85:80:9C:3C", "esp-28:84:85:80:9B:D0"   # HAT node, ESP-B


def send(port, text):
    req = urllib.request.Request(BASE + "/api/send", data=json.dumps({"port": port, "text": text, "eol": "CRLF"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req).read()


def lines(port):
    for c in json.load(urllib.request.urlopen(BASE + "/api/state"))["converters"]:
        if c["port"] == port:
            return c["lines"]
    return []


def ask(port, cmd, pat, wait=3.0):
    s0 = lines(port)[-1][0]
    send(port, cmd)
    end = time.time() + wait
    while time.time() < end:
        new = [t for n, _, t in lines(port) if n > s0]
        hit = [t for t in new if re.search(pat, t)]
        if hit:
            time.sleep(0.3)
            return [t for n, _, t in lines(port) if n > s0]
        time.sleep(0.1)
    return [t for n, _, t in lines(port) if n > s0]


def tc6(port):
    out = {}
    for t in ask(port, "counters", r"^tc6 "):
        m = re.search(r"status0 0x([0-9a-f]+) status1 0x([0-9a-f]+)\s+tx credits (\d+) rx chunks (\d+)\s+plca_sts 0x([0-9a-f]+)", t)
        if m:
            out = {"status0": int(m.group(1), 16), "status1": int(m.group(2), 16), "tx_credits": int(m.group(3)),
                   "rx_chunks": int(m.group(4)), "plca_sts": int(m.group(5), 16)}
    for t in ask(port, "status", r"^rx t1s"):
        m = re.search(r"^rx t1s: (\d+) frames", t)
        if m:
            out["driver_rx"] = int(m.group(1))
    return out


def sink(port):
    r = {}
    for t in ask(port, "sink", r"^sinkx?: "):
        m = re.search(r"^sink: (\d+) packets, \d+ B in ([\d.]+) s", t)
        if m:
            r.update(packets=int(m.group(1)), secs=float(m.group(2)))
        m = re.search(r"expected (\d+) got (\d+) lost (-?\d+)", t)
        if m:
            r.update(expected=int(m.group(1)), seq_lost=int(m.group(3)))
    return r


def main(path):
    for p in (A, B):
        send(p, "zenoh pause")
    time.sleep(1)
    runs = []
    for secs in (6, 6):
        before = tc6(A)
        ask(A, "sink reset", r"counters reset")
        bl = ask(B, "blast 192.168.100.65 %d 1472 9 0" % secs, r"^blast: \d+", secs + 8)
        sent = next((int(m.group(1)) for t in bl for m in [re.search(r"^blast: (\d+) x", t)] if m), None)
        after = tc6(A)
        sk = sink(A)
        ask(A, "sink reset", r"counters reset")
        ok = ask(B, "blast 192.168.100.65 3 1472 9 5", r"^blast: \d+", 12)
        rec = sink(A)
        runs.append({"secs": secs, "sent": sent, "before": before, "after": after, "sink": sk,
                     "driver_rx_delta": (after.get("driver_rx", 0) - before.get("driver_rx", 0)),
                     "recovery_5mbit": rec})
        print(json.dumps(runs[-1]))
    for p in (A, B):
        send(p, "zenoh resume")
    R = json.load(open(path))
    R["overload_probe"] = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": runs}
    json.dump(R, open(path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
