"""The two-board measurement campaign (esp32-5 = T1S node, esp32-7 = W5500 peer), run inside the
console server so its own polling stays off the boards while it runs.

What it adds over the single-pass suite (and why):
  repeats      the core metrics R times, both boards rebooted between repeats -> mean +- 95 % CI
  spi_sweep    the node's SPI clock 12..25 MHz; the service-time model is fitted on 12/20/25 and
               checked on 15/18/22, which it never saw
  burst        PLCA burst (MAXBC) on the coordinator: throughput and the other node's latency
  periodic     CAN-like small messages (16/64 B) every 1..10 ms, idle and under bulk load:
               latency distribution and deadline misses
  tail         a long 64 B round-trip run for p99.9 / p99.99 / max
  recovery     the coordinator rebooted while the peer probes it: outage length
Everything is measured by the boards; raw samples are kept in the JSON.
"""
import json
import os
import re
import statistics
import time

STATE = {"running": False, "phase": None, "step": None, "progress": 0, "file": None, "error": None}


def _ip(H, role):
    _, c, _ = H.esp(role)
    return (c or {}).get("hat_ip")


def _wait_up(H, role, want_mode=None, timeout=40):
    """After a reboot: the board is back, answers `status`, and its link is up."""
    end = time.time() + timeout
    while time.time() < end:
        k, c, prt = H.esp(role)
        if c and prt:
            lines = H.cmd_lines(role, "status", r"^link: ", 4, settle=0.3)
            ok = any(re.search(r"^link: up", t) for t in lines) or any("LINKED" in t for t in lines)
            if role == "tx":
                ok = any("LINKED" in t for t in lines)
            if ok and (not want_mode or any(t.startswith("mode: " + want_mode) for t in lines)):
                return True
        time.sleep(1.5)
    return False


def _reboot(H, roles):
    for r in roles:
        H.hat_send("reboot", echo=False, role=r)
    time.sleep(8)
    for r in roles:
        _wait_up(H, r)
    for r in roles:
        H.cmd_lines(r, "zenoh pause", r"^zenoh: ", 3, settle=0.05)
    time.sleep(1)


def _rtt(H, role, ip, n, size, iv):
    r = H.suite_rtt(role, ip, n, size, iv)
    return r["us"]


def _tput(H, src, dst, ip, secs, size, mbit):
    r = H.suite_flow(src, dst, ip, secs, size, mbit)
    b, s = r.get("blast") or {}, r.get("sink") or {}
    return {"offered": b.get("offered"), "sent": b.get("sent"), "got": s.get("packets"),
            "delivered": s.get("delivered"), "secs": s.get("secs"), "gap_p99": s.get("gap_p99"),
            "gap_max": s.get("gap_max"), "seq_lost": s.get("seq_lost")}


def _step(name, frac):
    STATE["step"] = name
    STATE["progress"] = int(frac * 100)


def run(H, out_dir, repeats=5, tail_min=15, quick=False):
    STATE.update(running=True, phase=None, step="starting", progress=0, file=None, error=None)
    H.duo["running"] = True
    R = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "repeats": [], "spi_sweep": [], "burst": [], "periodic": [],
         "tail": None, "recovery": [], "notes": []}
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, "campaign_%s.json" % ts)
    STATE["file"] = os.path.basename(path)

    def save():
        json.dump(R, open(path, "w"), indent=0)

    try:
        A, B = _ip(H, "node"), _ip(H, "tx")
        if not A or not B:
            raise RuntimeError("need the T1S node and the W5500 board online with IPs")
        _, a, _ = H.esp("node")
        R["setup"] = {"node": {"ip": A, "spi": a.get("hat_spi"), "plca": [a.get("hat_plca"), a.get("hat_id"), a.get("hat_count")],
                               "chip": a.get("hat_chip"), "key": H.esp("node")[0]}, "tx": {"ip": B, "key": H.esp("tx")[0]}}
        for r in ("node", "tx"):
            H.cmd_lines(r, "zenoh pause", r"^zenoh: ", 3, settle=0.05)
        secs = 2 if quick else 4
        nR = 2 if quick else repeats

        # ---- 1. repeats, both boards rebooted in between --------------------------------------
        STATE["phase"] = "repeats"
        for i in range(nR):
            base = i / nR * 0.40
            if i:
                _step("repeat %d/%d: rebooting both boards" % (i + 1, nR), base)
                _reboot(H, ("node", "tx"))
            rep = {"i": i, "t": time.strftime("%H:%M:%S")}
            _step("repeat %d/%d: RTT" % (i + 1, nR), base + 0.05 / nR)
            rep["rtt64_tx"] = _rtt(H, "tx", A, 150 if quick else 300, 64, 3)
            rep["rtt64_node"] = _rtt(H, "node", B, 150 if quick else 300, 64, 3)
            rep["rtt1472_tx"] = _rtt(H, "tx", A, 100 if quick else 200, 1472, 3)
            rep["rtt1472_node"] = _rtt(H, "node", B, 100 if quick else 200, 1472, 3)
            _step("repeat %d/%d: throughput" % (i + 1, nR), base + 0.2 / nR)
            rep["onto_9_0"] = _tput(H, "tx", "node", A, secs, 1472, 9.0)
            rep["onto_9_5"] = _tput(H, "tx", "node", A, secs, 1472, 9.5)
            rep["off_max"] = _tput(H, "node", "tx", B, secs, 1472, 0)
            _step("repeat %d/%d: both ways" % (i + 1, nR), base + 0.3 / nR)
            r = H.suite_flow("tx", "node", A, secs, 1472, 3, other=(B, 3))
            rep["bidir3"] = {"onto": (r.get("sink") or {}).get("delivered"), "off": ((r.get("reverse") or {}).get("sink") or {}).get("delivered"),
                             "onto_lost": (r.get("sink") or {}).get("seq_lost"), "off_lost": ((r.get("reverse") or {}).get("sink") or {}).get("seq_lost")}
            _step("repeat %d/%d: Zenoh" % (i + 1, nR), base + 0.35 / nR)
            for rr in ("node", "tx"):
                H.cmd_lines(rr, "zenoh resume", r"^zenoh: ", 3, settle=0.05)
            time.sleep(1.5)
            rep["zenoh_tx"] = H.zenoh_rtt("tx", "node", 4 if quick else 8, 50)["us"]
            for rr in ("node", "tx"):
                H.cmd_lines(rr, "zenoh ping 5", r"^zenoh: ping", 3, settle=0.05)
                H.cmd_lines(rr, "zenoh pause", r"^zenoh: ", 3, settle=0.05)
            R["repeats"].append(rep)
            save()

        # ---- 2. SPI clock sweep (model fit 12/20/25, validation 15/18/22) -------------------
        STATE["phase"] = "spi_sweep"
        clocks = [12, 25] if quick else [12, 15, 18, 20, 22, 25]
        for j, mhz in enumerate(clocks):
            _step("SPI %d MHz: reboot" % mhz, 0.40 + 0.20 * j / len(clocks))
            H.cmd_lines("node", "spi %d" % mhz, r"^spi: ", 3, settle=0.05)
            H.cmd_lines("node", "save", r"^saved", 3, settle=0.05)
            _reboot(H, ("node",))
            got = H.cmd_lines("node", "status", r"^link: ", 5, settle=0.3)
            run_mhz = next((int(m.group(1)) for t in got for m in [re.search(r"spi (\d+) MHz", t)] if m), None)
            actual = next((float(m.group(1)) for t in got for m in [re.search(r"\(([\d.]+) actual\)", t)] if m), None)
            e = {"set": mhz, "running": run_mhz, "actual": actual}
            _step("SPI %d MHz: measuring" % mhz, 0.40 + 0.20 * (j + 0.5) / len(clocks))
            e["off_1472"] = _tput(H, "node", "tx", B, secs, 1472, 0)
            e["off_512"] = _tput(H, "node", "tx", B, secs, 512, 0)
            e["onto_1472"] = _tput(H, "tx", "node", A, secs, 1472, 9.5)
            e["rtt1472_node"] = _rtt(H, "node", B, 80 if quick else 150, 1472, 3)
            R["spi_sweep"].append(e)
            save()
        if clocks[-1] != 25:
            H.cmd_lines("node", "spi 25", r"^spi: ", 3)
            H.cmd_lines("node", "save", r"^saved", 3)
            _reboot(H, ("node",))

        # ---- 3. PLCA burst on the coordinator ------------------------------------------------
        STATE["phase"] = "burst"
        R["notes"].append("TO_TIMER not swept: the converter's TO cannot be set (its UART is output-only); "
                          "a TO differing between nodes desynchronises PLCA, which would measure the mismatch, not TO.")
        for j, maxbc in enumerate([0, 1, 3] if quick else [0, 1, 3, 7]):
            _step("PLCA burst MAXBC %d" % maxbc, 0.60 + 0.08 * j / 4)
            val = (maxbc << 8) | 0x80
            H.cmd_lines("node", "reg w 4 ca05 %x" % val, r"^reg w", 3, settle=0.1)
            rb = H.cmd_lines("node", "reg r 4 ca05", r"^reg r mms 4 0xca05", 3, settle=0.1)
            e = {"maxbc": maxbc, "btmr": 0x80, "readback": next((t for t in rb if t.startswith("reg r mms 4 0xca05")), None)}
            e["off_1472"] = _tput(H, "node", "tx", B, secs, 1472, 0)
            e["off_64"] = _tput(H, "node", "tx", B, secs, 64, 0)
            # the other node's latency while the coordinator bursts
            H.hat_send("blast %s %d 1472 9 0" % (B, 8), echo=False, role="node")
            time.sleep(0.5)
            e["rtt64_tx_loaded"] = _rtt(H, "tx", A, 300, 64, 3)
            H.cmd_lines("node", "status", r"^link: ", 15, settle=0.2)
            R["burst"].append(e)
            save()
        H.cmd_lines("node", "reg w 4 ca05 80", r"^reg w", 3, settle=0.1)

        # ---- 4. periodic small messages (CAN-like), idle and under bulk load --------------------
        STATE["phase"] = "periodic"
        sizes, periods = ([16, 64], [2, 10]) if quick else ([16, 64], [1, 2, 5, 10])
        k, total = 0, len(sizes) * len(periods) * 2
        for load in (0, 8):
            for size in sizes:
                for per in periods:
                    _step("periodic %d B every %d ms, load %d Mbit/s" % (size, per, load), 0.68 + 0.12 * k / total)
                    n = 200 if quick else 500
                    if load:
                        dur = int(n * (per + 4) / 1000) + 3
                        H.hat_send("blast %s %d 1472 9 %g" % (B, dur, load), echo=False, role="node")
                        time.sleep(0.5)
                    us = _rtt(H, "tx", A, n, size, per)
                    if load:
                        H.cmd_lines("node", "status", r"^link: ", dur + 6, settle=0.2)
                    R["periodic"].append({"size": size, "period_ms": per, "load_mbit": load, "us": us})
                    k += 1
                    save()

        # ---- 5. long tail -------------------------------------------------------------------
        STATE["phase"] = "tail"
        tmin = 1 if quick else tail_min
        end, tail = time.time() + 60 * tmin, []
        while time.time() < end:
            _step("tail: %d samples, %.0f min left" % (len(tail), (end - time.time()) / 60),
                  0.80 + 0.15 * (1 - (end - time.time()) / (60 * tmin)))
            tail += _rtt(H, "tx", A, 1000, 64, 2)
        R["tail"] = {"size": 64, "period_ms": 2, "minutes": tmin, "us": tail}
        save()

        # ---- 6. coordinator reboot while the peer probes it ------------------------------------
        STATE["phase"] = "recovery"
        for j in range(1 if quick else 3):
            _step("recovery %d: coordinator reboot under probing" % (j + 1), 0.95 + 0.04 * j / 3)
            H.hat_send("rtt %s 1000 64 10" % A, echo=False, role="tx")     # ~13 s of probes around the outage
            time.sleep(2.0)
            t_reboot = time.time()
            H.hat_send("reboot", echo=False, role="node")
            lines = H.cmd_lines("tx", "status", r"^link: ", 90, settle=0.5,
                                need=lambda ls: any(t.startswith("rtt: n") for t in ls))
            us = [int(x) for t in lines if t.startswith("rtts:") for x in t.split()[1:]]
            R["recovery"].append({"probe_ms": 10, "timeout_ms": 100, "us": us, "t_reboot_after_s": 2.0})
            _wait_up(H, "node")
            H.cmd_lines("node", "zenoh pause", r"^zenoh: ", 3, settle=0.05)
            save()
        STATE["progress"] = 100
    except Exception as e:
        STATE["error"] = str(e)
        R["error"] = str(e)
    finally:
        save()
        for r in ("node", "tx"):
            H.hat_send("zenoh resume", echo=False, role=r)
        H.duo["running"] = False
        STATE.update(running=False, phase=None, step=None)
    return path
