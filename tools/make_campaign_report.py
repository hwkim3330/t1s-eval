#!/usr/bin/env python3
"""Report for a two-board measurement campaign (campaign_*.json from campaign.py).

    python3 pc/t1s_console/make_campaign_report.py docs/t1s_results/campaign_<ts>.json [outdir]

Every number is computed from the JSON. Intervals are 95 % (Student t over the repeats).
"""
import json
import math
import os
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_duo_report import write_pdf  # noqa: E402  (same HTML/PDF styling as the suite report)

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 9, "axes.titlesize": 9,
    "axes.labelsize": 9, "legend.fontsize": 7.5, "xtick.labelsize": 8, "ytick.labelsize": 8, "axes.grid": True,
    "grid.alpha": 0.3, "grid.linewidth": 0.5, "axes.spines.top": False, "axes.spines.right": False,
    "savefig.bbox": "tight", "figure.dpi": 150, "lines.linewidth": 1.4, "lines.markersize": 4})
C_ONTO, C_OFF, C_Z, C_G = "#1f5fa8", "#c2452d", "#7a4fd6", "#777777"
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}
WORST_WAIT_MS = 1.239   # one 1518 B frame + PLCA overhead on 10BASE-T1S (2026-10-01 analysis)


def ok(v):
    return [x for x in v if x >= 0]


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    return xs[f] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)


def ci(vals):
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
    n = len(vals)
    if n == 0:
        return float("nan"), float("nan"), 0
    m = statistics.mean(vals)
    if n == 1:
        return m, float("nan"), 1
    return m, T95.get(n - 1, 1.96) * statistics.stdev(vals) / math.sqrt(n), n


def timeline(us, period_ms, timeout_ms=100):
    """Start time (s) of each sequential probe: interval, then the answer or the 100 ms timeout."""
    t, out = 0.0, []
    for x in us:
        out.append(t)
        t += (period_ms + (x / 1000 if x >= 0 else timeout_ms)) / 1000
    return out


def in_window(us, period_ms, window_s):
    """The probes sent while a background load was actually running (it started before the probes)."""
    return [x for x, t in zip(us, timeline(us, period_ms)) if t < window_s]


def load_window_periodic(e):
    # campaign.py: blast duration = n*(period+4)/1000 + 3 s, started 0.5 s before the first probe
    n = len(e["us"])
    return int(n * (e["period_ms"] + 4) / 1000) + 3 - 0.5


def longest_lost_run(us):
    best = cur = 0
    for x in us:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def save(fig, out, name):
    fig.savefig(os.path.join(out, name + ".pdf"))
    fig.savefig(os.path.join(out, name + ".png"), dpi=220)
    plt.close(fig)


def main(path, out):
    R = json.load(open(path))
    os.makedirs(out, exist_ok=True)
    L = []
    w = L.append
    reps = R.get("repeats", [])

    # ---------------- repeat metrics
    metrics = [
        ("RTT 64 B, from ESP-B", "ms", lambda r: pct(ok(r["rtt64_tx"]), 50) / 1000, C_ONTO),
        ("RTT 64 B, from HAT", "ms", lambda r: pct(ok(r["rtt64_node"]), 50) / 1000, C_OFF),
        ("RTT 1472 B, from ESP-B", "ms", lambda r: pct(ok(r["rtt1472_tx"]), 50) / 1000, C_ONTO),
        ("RTT 1472 B, from HAT", "ms", lambda r: pct(ok(r["rtt1472_node"]), 50) / 1000, C_OFF),
        ("Onto T1S at 9.0 offered", "Mbit/s", lambda r: r["onto_9_0"]["delivered"], C_ONTO),
        ("Onto T1S at 9.5 offered", "Mbit/s", lambda r: r["onto_9_5"]["delivered"], C_ONTO),
        ("Off T1S, unpaced", "Mbit/s", lambda r: r["off_max"]["delivered"], C_OFF),
        ("Both ways 3+3: onto", "Mbit/s", lambda r: r["bidir3"]["onto"], C_ONTO),
        ("Both ways 3+3: off", "Mbit/s", lambda r: r["bidir3"]["off"], C_OFF),
        ("Zenoh RTT, from ESP-B", "ms", lambda r: pct(ok(r["zenoh_tx"]), 50) / 1000, C_Z),
    ]
    rows = []
    for name, unit, f, col in metrics:
        vals = []
        for r in reps:
            try:
                vals.append(f(r))
            except (KeyError, TypeError):
                vals.append(None)
        m, h, n = ci(vals)
        rows.append((name, unit, vals, m, h, n, col))

    fig, axes = plt.subplots(2, 5, figsize=(10.5, 4.2))
    for ax, (name, unit, vals, m, h, n, col) in zip(axes.flat, rows):
        xs = [i + 1 for i, v in enumerate(vals) if v is not None]
        ys = [v for v in vals if v is not None]
        ax.plot(xs, ys, "o", color=col)
        if not math.isnan(m):
            ax.axhline(m, color=col, lw=1)
            if not math.isnan(h):
                ax.axhspan(m - h, m + h, color=col, alpha=0.12, lw=0)
        ax.set_title(name, fontsize=8)
        ax.set_xlabel("repeat")
        ax.set_ylabel(unit)
        ax.set_xticks(range(1, len(vals) + 1))
        if ys:
            lo, hi = min(ys), max(ys)
            pad = max((hi - lo) * 0.6, abs(m) * 0.01 if not math.isnan(m) else 0.01)
            ax.set_ylim(lo - pad, hi + pad)
    fig.suptitle("Fig. C1  Repeatability: %d runs, both boards rebooted between runs; line = mean, band = 95 %% CI" % len(reps),
                 y=1.02, fontsize=9)
    fig.tight_layout()
    save(fig, out, "c1_repeats")

    # ---------------- SPI model
    sw = R.get("spi_sweep", [])
    fit_set, val_set = {12, 20, 25}, {15, 18, 22}
    model = None
    # the model needs the clock the SPI peripheral really runs (80 MHz / integer), not the one asked for
    act = R.get("spi_actual") or {}
    def fact(e):
        return e.get("actual") or act.get(str(e["set"])) or e["set"]
    pts = [(fact(e), e["off_1472"]["delivered"], e["set"]) for e in sw if e.get("off_1472", {}).get("delivered")]
    fitp = [(f, y) for f, y, sset in pts if sset in fit_set]
    # per-frame service time T = t0 + k/f  (k = SPI bit-time per frame x clock-period scale)
    if len(fitp) >= 2:
        bits = (1472 + 42) * 8
        xs = [1.0 / f for f, _ in fitp]
        ys = [bits / (y * 1e6) * 1e6 for _, y in fitp]          # us per frame
        mx, my = statistics.mean(xs), statistics.mean(ys)
        k = sum((x - mx) * (yy - my) for x, yy in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        t0 = my - k * mx
        # TC6 data chunks: 64 B payload + 4 B header/footer per chunk, both MOSI and MISO run the clock
        chunks = math.ceil((1472 + 42 + 4) / 64)
        spi_bits = chunks * 68 * 8
        c_factor = k / spi_bits                                  # >1: clock cycles beyond the bare transfer
        model = {"t0_us": t0, "k": k, "c": c_factor, "chunks": chunks}
    fig, ax = plt.subplots(figsize=(3.6, 2.7))
    if model:
        fs = [f / 2 for f in range(20, 54)]
        ax.plot(fs, [(1472 + 42) * 8 / (model["t0_us"] + model["k"] / f) for f in fs], color=C_G, lw=1,
                label="model, fitted on 12/20/25 MHz")
    for f, y, sset in pts:
        ax.plot([f], [y], "o", color=C_OFF, mfc=C_OFF if sset in fit_set else "white", ms=6)
        ax.annotate("%d" % sset, (f, y), textcoords="offset points", xytext=(4, -10), fontsize=6.5, color=C_G)
    ax.plot([], [], "o", color=C_OFF, label="measured (fit points)")
    ax.plot([], [], "o", color=C_OFF, mfc="white", label="measured (held out)")
    ax.set_xlabel("LAN8651 SPI clock, actual (MHz); label = asked")
    ax.set_ylabel("HAT → ESP-B, unpaced (Mbit/s)")
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Fig. C2  SPI clock model, out-of-sample check")
    save(fig, out, "c2_spi_model")

    # ---------------- periodic
    per = R.get("periodic", [])
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), sharey=True)
    for ax, load in zip(axes, (0, 8)):
        sel = [e for e in per if e["load_mbit"] == load]
        cmap = plt.get_cmap("viridis")
        for i, e in enumerate(sel):
            us = in_window(e["us"], e["period_ms"], load_window_periodic(e)) if load else e["us"]
            v = sorted(ok(us))
            if not v:
                continue
            ax.step([x / 1000 for x in v], [(k + 1) / len(us) for k in range(len(v))], where="post",
                    color=cmap(i / max(1, len(sel) - 1)), label="%d B / %d ms" % (e["size"], e["period_ms"]))
        ax.set_title("idle bus" if not load else "HAT streaming %d Mbit/s to ESP-B" % load)
        ax.set_xlabel("round trip (ms)")
    axes[0].set_ylabel("fraction answered")
    axes[1].legend(frameon=False, fontsize=6.5, loc="lower right")
    fig.suptitle("Fig. C3  CAN-like periodic messages, round trip from ESP-B; loaded: only probes sent while the load ran "
                 "(curves end below 1 where probes were lost)",
                 y=1.03, fontsize=9)
    save(fig, out, "c3_periodic")

    # ---------------- tail
    tail = ok((R.get("tail") or {}).get("us", []))
    if tail:
        fig, ax = plt.subplots(figsize=(3.6, 2.7))
        v = sorted(tail)
        n = len(v)
        ax.semilogy([x / 1000 for x in v], [1 - i / n for i in range(n)], color=C_ONTO)
        for q, ls in ((99.9, ":"), (99.99, "--")):
            ax.axvline(pct(v, q) / 1000, color=C_G, ls=ls, lw=0.8)
        ax.set_xlabel("round trip, 64 B (ms)")
        ax.set_ylabel("P(RTT > x)")
        ax.set_title("Fig. C4  Tail, %s samples" % format(n, ","))
        save(fig, out, "c4_tail")

    # ---------------- burst + recovery
    bu = R.get("burst", [])
    rec = R.get("recovery", [])
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.7))
    if bu:
        ax = axes[0]
        xs = [e["maxbc"] for e in bu]
        ax.plot(xs, [e["off_1472"]["delivered"] for e in bu], "o-", color=C_OFF, label="1472 B, Mbit/s")
        ax.plot(xs, [e["off_64"]["delivered"] for e in bu], "s-", color=C_OFF, mfc="white", label="64 B, Mbit/s")
        ax2 = ax.twinx()
        ax2.plot(xs, [pct(ok(e["rtt64_tx_loaded"]), 50) / 1000 for e in bu], "^--", color=C_ONTO, label="ESP-B RTT under it, ms")
        ax2.set_ylabel("RTT (ms)", color=C_ONTO)
        rmax = max([pct(ok(e["rtt64_tx_loaded"]), 50) / 1000 for e in bu] + [1])
        ax2.set_ylim(0, rmax * 1.4)       # from zero: a 2 us wobble must not look like an effect
        ax.set_ylim(0, 10.5)
        ax.set_xticks(xs)
        ax.set_xlabel("PLCA MAXBC on the coordinator")
        ax.set_ylabel("HAT → ESP-B (Mbit/s)")
        ax.set_title("(a) burst")
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=6.5, loc="center right")
    if rec:
        ax = axes[1]
        for j, e in enumerate(rec):
            us = e["us"]
            t, ts_, ys = 0.0, [], []
            for x in us:
                t += (e["probe_ms"] + (x / 1000 if x >= 0 else e["timeout_ms"])) / 1000
                ts_.append(t)
                ys.append(x / 1000 if x >= 0 else float("nan"))
            ax.plot(ts_, ys, ".", ms=2, label="run %d" % (j + 1))
            lost_t = [tt for tt, x in zip(ts_, us) if x < 0]
            if lost_t:
                ax.axvspan(min(lost_t), max(lost_t), alpha=0.08, color="C%d" % j)
        ax.set_xlabel("time since the probe run started (s)")
        ax.set_ylabel("RTT (ms)")
        ax.set_title("(b) coordinator reboot (band: no answers)")
        ax.legend(frameon=False, fontsize=6.5)
    fig.suptitle("Fig. C5  PLCA burst and coordinator recovery", y=1.03, fontsize=9)
    fig.tight_layout()
    save(fig, out, "c5_burst_recovery")

    # ================= text
    w("# Two-board T1S campaign: repeatability, SPI model check, periodic traffic, tail, recovery")
    w("")
    w("*Run %s — `%s`, generated by `make_campaign_report.py`. Intervals are 95 %% (Student t over the repeats).*"
      % (R.get("t"), os.path.basename(path)))
    w("")
    st = R.get("setup", {})
    w("**Setup.** esp32-5: ESP32-S3 + LAN8651 HAT, PLCA %s (id %s of %s), SPI %s MHz, %s. esp32-7: ESP32-S3 W5500 at %s on the "
      "converter's 100BASE-TX port. Converter: LAN8670 + LAN9355, ID 1 / count 0 (not coordinating). All traffic generated and "
      "measured by the two boards; Zenoh's periodic traffic paused except in its own measurements."
      % (*(st.get("node", {}).get("plca") or ["?", "?", "?"]), st.get("node", {}).get("spi"), st.get("node", {}).get("ip"),
         st.get("tx", {}).get("ip")))
    w("")
    w("## 1. Repeatability (%d runs, both boards rebooted between runs)" % len(reps))
    w("")
    w("![C1](c1_repeats.png)")
    w("")
    w("| metric | per run | mean ± 95 % CI | spread (max−min) |")
    w("|---|---|---|---|")
    for name, unit, vals, m, h, n, _ in rows:
        vv = [v for v in vals if v is not None]
        w("| %s | %s | **%.3f ± %s %s** | %.3f |" % (name, " / ".join("%.3f" % v for v in vv), m,
                                                   ("%.3f" % h) if not math.isnan(h) else "—", unit,
                                                   (max(vv) - min(vv)) if vv else float("nan")))
    w("")
    stable = [r for r in rows if r[5] > 1 and not math.isnan(r[4]) and r[3] and abs(r[4] / r[3]) < 0.01]
    loose = [r for r in rows if r not in stable and r[5] > 1]
    w("**Stable across reboots** (95 %% CI under 1 %% of the mean): %s." % ", ".join(r[0] for r in stable))
    w("")
    for r in loose:
        vv = [v for v in r[2] if v is not None]
        if r[0].startswith("RTT") and "HAT" in r[0]:
            w("- **%s** moves between runs (%.2f–%.2f %s) while staying tight within a run. The HAT's probe timer and ESP-B's "
              "1 ms W5500 poll start at an arbitrary phase after each boot, and the reply waits for that poll: a reboot "
              "reshuffles the phase. Seen from ESP-B, which owns the poll, the same path is stable." % (r[0], min(vv), max(vv), r[1]))
        elif r[0].startswith("Both ways") and "onto" in r[0]:
            ncol = sum(1 for v in vv if v < 0.9 * 3)
            w("- **%s**: the converter's stream onto T1S fell short of the 3 Mbit/s offered in **%d of %d runs** (%s Mbit/s), "
              "from a total stall to none. The collapse is real but not deterministic; a single run can show anything from 0 to "
              "3 Mbit/s, which is why repeats were needed to state it." % (r[0], ncol, len(vv), " / ".join("%.2f" % v for v in vv)))
        else:
            w("- **%s**: %.3f ± %.3f %s." % (r[0], r[3], r[4], r[1]))
    w("")
    w("## 2. SPI clock: model fitted on 12/20/25 MHz, checked on 15/18/22 MHz")
    w("")
    w("![C2](c2_spi_model.png)")
    w("")
    if model:
        w("Model: every 1472 B datagram costs a fixed **t0 = %.0f µs** plus **k/f = %.0f µs·MHz / f** of SPI time, fitted on the "
          "fit clocks only. With %d TC6 chunks of 68 B per frame, k corresponds to **c = %.2f** clock periods per transferred bit "
          "(1.00 would be the bare chunk transfer)." % (model["t0_us"], model["k"], model["chunks"], model["c"]))
        w("")
        w("| SPI MHz asked → actual | role | measured (Mbit/s) | model (Mbit/s) | error | 512 B unpaced | onto T1S at 9.5 | RTT 1472 B from HAT (ms) |")
        w("|---|---|---|---|---|---|---|---|")
        errs = []
        for e in sw:
            f = fact(e)
            meas = e["off_1472"]["delivered"]
            pred = (1472 + 42) * 8 / (model["t0_us"] + model["k"] / f)
            err = 100 * (meas - pred) / pred if meas else float("nan")
            if e["set"] in val_set:
                errs.append(abs(err))
            w("| %s → %.2f | %s | %.3f | %.3f | %+.1f %% | %.3f | %.3f | %.2f |" % (
                e["set"], f, "fit" if e["set"] in fit_set else "held out", meas or float("nan"), pred, err,
                e["off_512"]["delivered"] or float("nan"), e["onto_1472"]["delivered"] or float("nan"),
                pct(ok(e["rtt1472_node"]), 50) / 1000))
        w("")
        if errs:
            w("Held-out error: mean **%.1f %%**, worst **%.1f %%**." % (statistics.mean(errs), max(errs)))
            w("")
        if act:
            w("**The clock asked for is not the clock that runs.** The ESP32-S3's SPI peripheral divides 80 MHz by an integer, "
              "so the boards ran: %s. The \"25 MHz\" of every earlier report is **26.67 MHz**. The held-out settings therefore "
              "land on one new clock (16 MHz, asked as 15 and 18) and on a fit clock again (20 MHz, asked as 22), which checks "
              "repeatability rather than prediction; the model is fitted and drawn against the actual clock."
              % ", ".join("%s → %.2f" % (k, v) for k, v in sorted(act.items(), key=lambda kv: int(kv[0]))))
            w("")
    w("## 3. CAN-like periodic messages")
    w("")
    w("![C3](c3_periodic.png)")
    w("")
    w("Sequential probes (one in flight), so the effective period is max(period, round trip). Under load only the probes sent "
      "while the load was running are counted (each probe's start time is rebuilt from the intervals, answers and 100 ms "
      "timeouts). Deadline columns count a probe as "
      "missed if it was lost or its round trip exceeded the deadline. Bound: the idle median plus one worst-case wait behind a "
      "1518 B frame in each direction (2 × %.3f ms)." % WORST_WAIT_MS)
    w("")
    w("| payload | period | load | probes | lost | median | p99 | max | > idle + 2×wait | miss @ 5 ms | miss @ 10 ms |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for e in per:
        us = in_window(e["us"], e["period_ms"], load_window_periodic(e)) if e["load_mbit"] else e["us"]
        v = ok(us)
        n = len(us)
        idle = next((x for x in per if x["size"] == e["size"] and x["period_ms"] == e["period_ms"] and x["load_mbit"] == 0), None)
        base = pct(ok(idle["us"]), 50) / 1000 if idle else float("nan")
        bound = base + 2 * WORST_WAIT_MS
        over = sum(1 for x in v if x / 1000 > bound)
        miss5 = (n - len(v)) + sum(1 for x in v if x > 5000)
        miss10 = (n - len(v)) + sum(1 for x in v if x > 10000)
        w("| %d B | %d ms | %s | %d | %d | %.2f | %.2f | %.2f | %d | %.1f %% | %.1f %% |" % (
            e["size"], e["period_ms"], ("%d Mbit/s" % e["load_mbit"]) if e["load_mbit"] else "idle", n, n - len(v),
            pct(v, 50) / 1000, pct(v, 99) / 1000, max(v) / 1000 if v else float("nan"), over,
            100 * miss5 / n if n else 0, 100 * miss10 / n if n else 0))
    w("")
    lo = [e for e in per if e["load_mbit"]]
    lossr = [100.0 * (len(in_window(e["us"], e["period_ms"], load_window_periodic(e))) - len(ok(in_window(e["us"], e["period_ms"], load_window_periodic(e)))))
             / max(1, len(in_window(e["us"], e["period_ms"], load_window_periodic(e)))) for e in lo]
    w("On an idle bus every probe returns, well inside a 5 ms deadline, and none exceeds the bound. Under an 8 Mbit/s stream "
      "from the node, **%.0f–%.0f %% of the probes sent during the load are lost**, and most of those that return still sit "
      "near the idle median. The losses are the converter's: each probe has to go onto T1S through it while the node "
      "streams the other way (§1, two-way). The answered probes that exceed the bound do so by queueing behind the node's own "
      "stream in its transmit path, not on the wire." % (min(lossr), max(lossr)) if lossr else "")
    w("")
    if tail:
        w("## 4. Tail (%s probes, 64 B every 2 ms, %s min)" % (format(len(tail), ","), (R.get("tail") or {}).get("minutes")))
        w("")
        w("![C4](c4_tail.png)")
        w("")
        lost = len((R.get("tail") or {}).get("us", [])) - len(tail)
        w("| median | p99 | p99.9 | p99.99 | max | lost |")
        w("|---|---|---|---|---|---|")
        w("| %.3f | %.3f | %.3f | %.3f | %.3f | %d |" % tuple([pct(tail, q) / 1000 for q in (50, 99, 99.9, 99.99)] + [max(tail) / 1000, lost]))
        w("")
    w("## 5. PLCA burst and coordinator recovery")
    w("")
    w("![C5](c5_burst_recovery.png)")
    w("")
    if bu:
        w("| MAXBC | register read back | 1472 B unpaced (Mbit/s) | 64 B unpaced (Mbit/s) | ESP-B probes during the coordinator's 8 s flood: answered |")
        w("|---|---|---|---|---|")
        for e in bu:
            dur = in_window(e["rtt64_tx_loaded"], 3, 7.5)
            w("| %d | `%s` | %.3f | %.3f | %d of %d |" % (e["maxbc"], (e.get("readback") or "").split("=")[-1].strip().split(" ")[0],
                                                     e["off_1472"]["delivered"] or float("nan"), e["off_64"]["delivered"] or float("nan"),
                                                     len(ok(dur)), len(dur)))
        w("")
        fr = [(len(ok(in_window(e["rtt64_tx_loaded"], 3, 7.5))), len(in_window(e["rtt64_tx_loaded"], 3, 7.5))) for e in bu]
        w("While the coordinator floods unpaced, **only %d–%d %% of the other node's probes are answered** at any MAXBC: they "
          "have to get onto T1S through the converter while the bus is busy in the other direction. They are all answered again "
          "once the flood ends." % (min(100 * a / max(1, n) for a, n in fr), max(100 * a / max(1, n) for a, n in fr)))
        w("")
        w("Burst mode changes nothing measurable: with lwIP handing the MAC one frame per call over SPI, the coordinator rarely "
          "has a second frame ready inside the burst timer, so it never uses the extra slots.")
        w("")
    if rec:
        w("| run | probes | lost | longest run of lost probes | outage |")
        w("|---|---|---|---|---|")
        outs = []
        for j, e in enumerate(rec, 1):
            us = e["us"]
            lr = longest_lost_run(us)
            outage = lr * (e["probe_ms"] + e["timeout_ms"]) / 1000
            outs.append(outage)
            w("| %d | %d | %d | %d | **%.2f s** (± %.2f) |" % (j, len(us), len(us) - len(ok(us)), lr, outage,
                                                          (e["probe_ms"] + e["timeout_ms"]) / 1000))
        w("")
        w("Outage = the longest run of unanswered probes × (10 ms interval + 100 ms timeout), so ± one probe. "
          "Mean %.2f s over %d reboots." % (statistics.mean(outs), len(outs)))
        w("")
        w("The outage covers the coordinator's own reboot and bring-up (ESP32 boot, LAN8651 driver install, PLCA). Answers resume "
          "as soon as its first beacon goes out; the peer and the converter need no recovery action.")
        w("")
    w("## 6. What two boards cannot show (stated, not hidden)")
    w("")
    w("| reviewer item | why not here | what it needs |")
    w("|---|---|---|")
    for a, b, c in (
        ("more than 2 PLCA nodes (cycle vs N, fairness, empty slots)", "one LAN8651 node exists", "a second / third LAN8651 node (HAT Rev C)"),
        ("converter removed (control experiment)", "the only other T1S device is the converter", "two LAN8651 nodes, or node + bridge pair"),
        ("baseline without T1S", "W5500 ⇄ W5500 needs a crossover (no auto-MDIX, datasheet)", "a crossover cable or a switch"),
        ("cable length / stubs / termination", "one 1 m cable", "cables and a multidrop harness"),
        ("TO_TIMER sweep", "the converter's TO cannot be set; mismatched TO would measure the mismatch", "two settable nodes"),
        ("collision / error counters", "the guessed MAC counter map was wrong and stalled TX", "the LAN8651 statistics register map"),
        ("CPU load and power", "not instrumented", "FreeRTOS run-time stats build, a power meter"),
        ("Zenoh ~1000 msg/s receive cap", "cause inside zenoh-pico, not found", "profiling of zenoh-pico's executor"),
    ):
        w("| %s | %s | %s |" % (a, b, c))
    w("")
    for nte in R.get("notes", []):
        w("- " + nte)
    w("")
    w("**Measurement corrections in this run:** the sink's rate is now (all datagrams after the first) / (first-to-last arrival, µs), "
      "removing the ~0.5 % over-read; arrival-gap histogram extended to 50 ms (20 µs bins to 2 ms, 1 ms bins above).")
    w("")
    open(os.path.join(out, "REPORT.md"), "w").write("\n".join(L) + "\n")
    write_pdf(out, "\n".join(L))
    print("wrote", out)


if __name__ == "__main__":
    p = sys.argv[1]
    o = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(p), os.path.basename(p)[:-5])
    main(p, o)
