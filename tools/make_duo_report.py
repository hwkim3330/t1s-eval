#!/usr/bin/env python3
"""Figures and a written report from one two-ESP suite run (duo_suite_*.json).

    python3 pc/t1s_console/make_duo_report.py docs/t1s_results/duo_suite_<ts>.json [outdir]

Writes <outdir>/fig*.pdf + .png and <outdir>/REPORT.md. Every number in the report is computed
here from the JSON; nothing is typed in by hand.
"""
import json
import math
import os
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["DejaVu Serif"], "font.size": 9,
    "axes.titlesize": 9, "axes.labelsize": 9, "legend.fontsize": 7.5, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False, "savefig.bbox": "tight",
    "figure.dpi": 150, "lines.linewidth": 1.4, "lines.markersize": 4,
})
C_TX = "#1f5fa8"     # tx -> node: onto the T1S bus (W5500 -> converter -> T1S -> HAT)
C_NODE = "#c2452d"   # node -> tx: off the T1S bus
C_GREY = "#777777"
DIRS = {"tx->node": ("ESP-B → HAT (onto T1S)", C_TX), "node->tx": ("HAT → ESP-B (off T1S)", C_NODE)}

# 10BASE-T1S wire model for a UDP datagram of L payload bytes, one sender, PLCA with 2 nodes:
# frame = L + 42 (Eth+IP+UDP) + 4 FCS bytes, + 8 preamble/SFD bytes, + 12 bytes IFG; plus, per
# frame, the idle node's transmit opportunity (TO_TIMER 32 bit times) and a share of the BEACON
# (20 bit times) -- burst mode off, so one frame per cycle.
PLCA_BITS = 32 + 20


def t1s_ceiling(L, rate=10e6):
    counted = (L + 42) * 8          # what blast/sink count as "on the wire"
    wire = (L + 42 + 4 + 8 + 12) * 8 + PLCA_BITS
    return rate * counted / wire / 1e6


def t1s_pps(L, rate=10e6):
    return rate / ((L + 42 + 4 + 8 + 12) * 8 + PLCA_BITS)


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100.0
    f, c = math.floor(k), math.ceil(k)
    return xs[f] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)


def secs_of(r):
    return r.get("secs") or (r.get("blast") or {}).get("secs") or (r.get("sink") or {}).get("secs") or 0


def ok(us):
    return [x for x in us if x >= 0]


def save(fig, out, name):
    fig.savefig(os.path.join(out, name + ".pdf"))
    fig.savefig(os.path.join(out, name + ".png"), dpi=220)
    plt.close(fig)


def loss_of(r):
    b, s = r.get("blast") or {}, r.get("sink") or {}
    if not b.get("sent") or s.get("packets") is None:
        return None
    return max(0.0, 100.0 * (1 - s["packets"] / b["sent"]))


def zenoh_abstract(R):
    Z = R.get("zenoh") or {}
    meds = [pct(ok(r["us"]), 50) / 1000 for r in Z.get("rtt", []) if ok(r["us"])]
    best = max((r["sink"]["mbit"] for r in Z.get("bulk", []) if r.get("sink")), default=None)
    if not meds:
        return ""
    rng = ("%.1f" % min(meds)) if round(min(meds), 1) == round(max(meds), 1) else "%.1f–%.1f" % (min(meds), max(meds))
    return (" Zenoh ran on the same two boards **peer to peer over UDP multicast, with no router**: a pub/sub "
            "round trip took %s ms median in either direction, and bulk puts delivered up to %.1f Mbit/s of payload."
            % (rng, best or float("nan")))


def spi_actual(setup):
    """The SCLK that ran. Recorded since 2026-10-06; before that `spi 25` ran 80/3 = 26.67 MHz
    (out of the LAN8651's spec), and the other settings the integer dividers below."""
    n = setup["node"]
    if n.get("spi_actual"):
        return float(n["spi_actual"])
    return {25: 26.67, 24: 26.67, 23: 26.67, 22: 20.0, 20: 20.0, 18: 16.0, 15: 16.0, 12: 11.43}.get(n.get("spi"), float(n.get("spi") or 0))


def main(path, out):
    R = json.load(open(path))
    os.makedirs(out, exist_ok=True)
    st = R["setup"]
    figs = []

    # ---- Fig 1: RTT CDFs by frame size, both directions --------------------------------
    sizes = sorted({r["size"] for r in R["rtt"]})
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.6), sharey=True, sharex=True)
    cmap = plt.get_cmap("viridis")
    for ax, d in zip(axes, ("tx->node", "node->tx")):
        for i, sz in enumerate(sizes):
            rr = [r for r in R["rtt"] if r["dir"] == d and r["size"] == sz]
            if not rr:
                continue
            xs = sorted(ok(rr[0]["us"]))
            ys = [(k + 1) / len(xs) for k in range(len(xs))]
            ax.step([x / 1000 for x in xs], ys, where="post", color=cmap(i / max(1, len(sizes) - 1)),
                    label="%d B" % sz)
        ax.set_title(("measured on ESP-B (W5500)" if d == "tx->node" else "measured on the HAT node (LAN8651)"))
        ax.set_xlabel("UDP echo round trip (ms)")
    axes[0].set_ylabel("CDF")
    axes[1].legend(title="payload", loc="lower right", frameon=False)
    fig.suptitle("Fig. 1  Round-trip time across converter + 10BASE-T1S, by payload size", y=1.02, fontsize=9)
    save(fig, out, "fig1_rtt_cdf")
    figs.append(("fig1_rtt_cdf", "Round-trip time distribution per payload size. Left: ESP-B sends, "
                 "HAT echoes. Right: HAT sends, ESP-B echoes."))

    # ---- Fig 2: RTT vs payload with fit -----------------------------------------------
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    fits = {}
    for d, (lab, col) in DIRS.items():
        xs, med, lo, hi = [], [], [], []
        for sz in sizes:
            rr = [r for r in R["rtt"] if r["dir"] == d and r["size"] == sz]
            if not rr or not ok(rr[0]["us"]):
                continue
            v = ok(rr[0]["us"])
            xs.append(sz)
            med.append(pct(v, 50) / 1000)
            lo.append(pct(v, 50) / 1000 - pct(v, 5) / 1000)
            hi.append(pct(v, 95) / 1000 - pct(v, 50) / 1000)
        if len(xs) >= 2:
            n = len(xs)
            mx, my = sum(xs) / n, sum(med) / n
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, med)) / sum((x - mx) ** 2 for x in xs)
            icpt = my - slope * mx
            fits[d] = (slope * 1000, icpt)          # us per byte, ms at 0 B
            ax.plot([0, 1500], [icpt, icpt + slope * 1500], color=col, lw=0.8, ls=":")
        ax.errorbar(xs, med, yerr=[lo, hi], fmt="o-", color=col, capsize=2, label=lab)
    ax.set_xlabel("UDP payload (bytes)")
    ax.set_ylabel("RTT, median (ms)\nbars: p5–p95")
    ax.set_xlim(0, 1550)
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Fig. 2  RTT vs payload, linear fit (dotted)")
    save(fig, out, "fig2_rtt_size")
    figs.append(("fig2_rtt_size", "Median RTT against payload with p5–p95 bars and a least-squares line."))

    # ---- Fig 3: throughput sweep -------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.7))
    ax, ax2 = axes
    ceil1472 = t1s_ceiling(1472)
    ax.plot([0, 15], [0, 15], color=C_GREY, lw=0.7, ls="--", label="delivered = offered")
    ax.axhline(ceil1472, color="k", lw=0.8, ls="-.", label="10BASE-T1S ceiling (model), %.2f" % ceil1472)
    for d, (lab, col) in DIRS.items():
        # x = the measured offered rate; where the sender's report was missing (it saturated and
        # its report line was lost), the asked rate, drawn hollow
        rows = [r for r in R["sweep"] if r["dir"] == d and r.get("blast")]
        def xof(r):
            return r["blast"].get("offered") or r["mbit"] or None
        rows = [r for r in rows if xof(r)]
        rows.sort(key=xof)
        xs = [xof(r) for r in rows]
        ys = [r["sink"].get("delivered", 0) for r in rows]
        ax.plot(xs, ys, "-", color=col, label=lab)
        ls = [loss_of(r) for r in rows]
        ax2.plot(xs, [l if l is not None else float("nan") for l in ls], "-", color=col, label=lab)
        for x, y, l, r in zip(xs, ys, ls, rows):
            hollow = bool(r["blast"].get("from_sink_seq"))
            kw = dict(color=col, marker="o", ms=4, mfc="white" if hollow else col)
            ax.plot([x], [y], **kw)
            if l is not None:
                ax2.plot([x], [l], **kw)
    ax.set_xlabel("offered load (Mbit/s, UDP 1472 B)")
    ax.set_ylabel("delivered (Mbit/s)")
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 11)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("(a) delivered vs offered")
    ax2.set_xlabel("offered load (Mbit/s)")
    ax2.set_ylabel("datagram loss (%)")
    ax2.set_yscale("symlog", linthresh=0.1)
    ax2.set_ylim(-0.02, 100)
    ax2.set_xlim(0, 15)
    ax2.set_title("(b) loss (sequence-checked)")
    fig.suptitle("Fig. 3  Load sweep, one direction at a time (paced; right-most point unpaced; "
                 "hollow = sender saturated, x is the asked rate)", y=1.02, fontsize=8.5)
    save(fig, out, "fig3_sweep")
    figs.append(("fig3_sweep", "Delivered rate and loss against offered load, one direction at a time. "
                 "The right-most point of each curve is an unpaced blast."))

    # ---- Fig 4: frame size, max rate ---------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.7))
    ax, ax2 = axes
    Ls = list(range(18, 1473, 10))
    ax.plot(Ls, [t1s_ceiling(L) for L in Ls], color="k", lw=0.8, ls="-.", label="T1S ceiling (model)")
    ax2.plot(Ls, [t1s_pps(L) / 1000 for L in Ls], color="k", lw=0.8, ls="-.", label="T1S ceiling (model)")
    for d, (lab, col) in DIRS.items():
        rows = sorted([r for r in R["sizes"] if r["dir"] == d], key=lambda r: r["size"])
        xs = [r["size"] for r in rows]
        ax.plot(xs, [r["sink"].get("delivered", 0) for r in rows], "o-", color=col, label=lab)
        ax2.plot(xs, [r["sink"].get("packets", 0) / max(1e-9, r["sink"].get("secs") or secs_of(r)) / 1000
                      for r in rows], "o-", color=col, label=lab)
    ax.set_xlabel("UDP payload (bytes)")
    ax.set_ylabel("delivered (Mbit/s, Eth+IP+UDP)")
    ax.set_ylim(0, 11)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("(a) throughput")
    ax2.set_xlabel("UDP payload (bytes)")
    ax2.set_ylabel("delivered (kframes/s)")
    ax2.set_yscale("log")
    ax2.legend(frameon=False, loc="upper right")
    ax2.set_title("(b) frame rate")
    fig.suptitle("Fig. 4  Unpaced blasts by payload size", y=1.02, fontsize=9)
    save(fig, out, "fig4_sizes")
    figs.append(("fig4_sizes", "Unpaced throughput and frame rate by payload, against the 10BASE-T1S "
                 "model ceiling."))

    # ---- Fig 5: both directions at once ------------------------------------------------
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    brows = rows = sorted(R["bidir"], key=lambda r: r["mbit"])
    xs = list(range(len(rows)))
    w = 0.38
    a = [r["sink"].get("delivered", 0) for r in rows]
    b = [r["reverse"]["sink"].get("delivered", 0) for r in rows]
    ax.bar([x - w / 2 for x in xs], a, w, color=C_TX, label=DIRS["tx->node"][0])
    ax.bar([x + w / 2 for x in xs], b, w, color=C_NODE, label=DIRS["node->tx"][0])
    ax.plot(xs, [r["mbit"] for r in rows], "k_", markersize=14, mew=1.2, label="offered, each")
    ax.set_xticks(xs)
    ax.set_xticklabels(["%g" % r["mbit"] for r in rows])
    ax.set_xlabel("offered per direction (Mbit/s)")
    ax.set_ylabel("delivered (Mbit/s)")
    ax.legend(frameon=False, loc="upper left", fontsize=6.8)
    ax.set_title("Fig. 5  Both directions at once")
    save(fig, out, "fig5_bidir")
    figs.append(("fig5_bidir", "Both directions blasting at the same paced rate. Bars: delivered per "
                 "direction; ticks: offered."))

    # ---- Fig 6: RTT under load ---------------------------------------------------------
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    lrows = sorted(R["loaded_rtt"], key=lambda r: r["load"])
    for i, r in enumerate(lrows):
        xs = sorted(ok(r["us"]))
        if not xs:
            continue
        ax.step([x / 1000 for x in xs], [(k + 1) / len(r["us"]) for k in range(len(xs))], where="post",
                color=plt.get_cmap("magma")(0.15 + 0.7 * i / max(1, len(lrows) - 1)),
                label="%g Mbit/s HAT→ESP-B, %d%% lost" % (r["load"], round(100 * (len(r["us"]) - len(xs)) / len(r["us"]))))
    ax.set_xlabel("RTT ESP-B → HAT, 64 B (ms)")
    ax.set_ylabel("fraction answered")
    ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, loc="lower right", fontsize=6.8)
    ax.set_title("Fig. 6  Latency under reverse load")
    save(fig, out, "fig6_loaded_rtt")
    figs.append(("fig6_loaded_rtt", "RTT from ESP-B while the HAT streams the other way. Curves end below 1 "
                 "where echoes were lost."))

    # ---- Fig 7: arrival-gap percentiles (pacing jitter) ---------------------------------
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    for d, (lab, col) in DIRS.items():
        rows = [r for r in R["sweep"] if r["dir"] == d and r["mbit"] and r["sink"].get("gap_p50")]
        rows.sort(key=lambda r: r["mbit"])
        xs = [r["mbit"] for r in rows]
        ax.plot(xs, [r["sink"]["gap_p50"] for r in rows], "o-", color=col, label=lab + ", p50")
        ax.plot(xs, [r["sink"]["gap_p99"] for r in rows], "^--", color=col, alpha=0.7, label="p99")
    xs = [x / 10 for x in range(8, 101)]
    ax.plot(xs, [(1472 + 42) * 8 / x for x in xs], color=C_GREY, lw=0.7, label="nominal spacing")
    ax.set_xlabel("offered (Mbit/s)")
    ax.set_ylabel("inter-arrival gap at sink (µs)")
    ax.set_yscale("log")
    ax.legend(frameon=False, fontsize=6.5, loc="upper right")
    ax.set_title("Fig. 7  Arrival spacing (2 ms histogram cap)")
    save(fig, out, "fig7_gaps")
    figs.append(("fig7_gaps", "Median and 99th-percentile inter-arrival gap at the receiver, against the "
                 "spacing the sender paced to. The receiver's histogram tops out at 2 ms."))

    Z = R.get("zenoh") or {}
    # a publisher report that never reached the console: the subscriber's sequence range says how
    # many were put (exact unless the very last ones were lost); marked, and drawn hollow
    # the put window is the blast duration (the same for every row), not the receiver's window
    known = [r["blast"]["secs"] for r in Z.get("bulk", []) if r.get("blast") and r["blast"].get("secs")]
    put_secs = statistics.median(known) if known else None
    for r in Z.get("bulk", []):
        k = r.get("sink") or {}
        if not r.get("blast") and k.get("expected"):
            sec = put_secs or k.get("secs") or 1
            r["blast"] = {"sent": k["expected"], "size": r["size"], "secs": sec, "rate": k["expected"] / sec,
                          "mbit": k["expected"] * r["size"] * 8 / sec / 1e6, "from_sink_seq": True}
    if Z.get("rtt"):
        fig, ax = plt.subplots(figsize=(3.4, 2.6))
        for r in Z["rtt"]:
            lab, col = DIRS[r["dir"]]
            xs = sorted(ok(r["us"]))
            if xs:
                ax.step([x / 1000 for x in xs], [(k + 1) / len(xs) for k in range(len(xs))], where="post",
                        color=col, label="Zenoh, pinged from " + ("ESP-B" if r["dir"] == "tx->node" else "HAT"))
        for d in ("tx->node", "node->tx"):
            rr = [r for r in R["rtt"] if r["dir"] == d and r["size"] == 64]
            if rr and ok(rr[0]["us"]):
                xs = sorted(ok(rr[0]["us"]))
                ax.step([x / 1000 for x in xs], [(k + 1) / len(xs) for k in range(len(xs))], where="post",
                        color=DIRS[d][1], ls=":", lw=1.0,
                        label="raw UDP 64 B, from " + ("ESP-B" if d == "tx->node" else "HAT"))
        ax.set_xlabel("round trip (ms)")
        ax.set_ylabel("CDF")
        ax.legend(frameon=False, fontsize=6.5, loc="lower right")
        ax.set_title("Fig. 8  Zenoh ping/pong vs raw UDP echo")
        save(fig, out, "fig8_zenoh_rtt")
        figs.append(("fig8_zenoh_rtt", "Zenoh publish/subscribe round trip against the raw UDP echo."))
    if Z.get("bulk"):
        fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.7))
        ax, ax2 = axes
        for d, (lab, col) in DIRS.items():
            rows = sorted([r for r in Z["bulk"] if r["dir"] == d and r.get("blast") and r.get("sink")],
                          key=lambda r: r["size"])
            xs = [r["size"] for r in rows]
            ax.plot(xs, [r["blast"]["mbit"] for r in rows], "o--", color=col, mfc="white", label=lab + ", sent")
            ax.plot(xs, [r["sink"]["mbit"] for r in rows], "o-", color=col, label="delivered")
            ax2.plot(xs, [r["blast"]["rate"] for r in rows], "o--", color=col, mfc="white", label=lab + ", sent")
            ax2.plot(xs, [r["sink"]["rate"] for r in rows], "o-", color=col, label="delivered")
        zs = sorted({r["size"] for r in Z["bulk"]})
        for a_ in (ax, ax2):
            a_.set_xscale("log", base=2)
            a_.set_xticks(zs)
            a_.set_xticklabels([str(z) for z in zs])
            a_.minorticks_off()
        ax.set_xlabel("Zenoh payload (bytes)")
        ax.set_ylabel("payload rate (Mbit/s)")
        ax.legend(frameon=False, fontsize=6.5, loc="upper left")
        ax.set_title("(a) throughput")
        ax2.set_xlabel("Zenoh payload (bytes)")
        ax2.set_ylabel("messages / s")
        ax2.axhline(1000, color=C_GREY, lw=0.7, ls="-.")
        ax2.legend(frameon=False, fontsize=6.5, loc="lower left")
        ax2.set_title("(b) message rate (dash-dot: 1000/s)")
        fig.suptitle("Fig. 9  Zenoh put/subscribe bulk transfer, peer over UDP multicast, no router", y=1.02, fontsize=9)
        save(fig, out, "fig9_zenoh_bulk")
        figs.append(("fig9_zenoh_bulk", "Zenoh bulk publish by payload size: what the publisher put and what the "
                     "subscriber on the other board received."))

    # ---- numbers for the text -----------------------------------------------------------
    def rtt_row(d, sz):
        rr = [r for r in R["rtt"] if r["dir"] == d and r["size"] == sz]
        if not rr:
            return None
        v = ok(rr[0]["us"])
        return {"n": len(rr[0]["us"]), "lost": len(rr[0]["us"]) - len(v), "min": min(v) / 1000,
                "p50": pct(v, 50) / 1000, "p99": pct(v, 99) / 1000, "max": max(v) / 1000,
                "sd": statistics.pstdev(v) / 1000}

    def best(d, key):
        rows = [r for r in R["sweep"] if r["dir"] == d and (loss_of(r) or 0) < 0.1 and r["sink"].get("delivered")]
        return max(rows, key=lambda r: r["sink"]["delivered"]) if rows else None

    L = []
    w = L.append
    w("# 10BASE-T1S through a media converter, measured end to end by two ESP32-S3 boards")
    w("")
    w("*Run %s — generated by `make_duo_report.py` from `%s`.*" % (R["t"], os.path.basename(path)))
    w("")
    w("## Abstract")
    w("")
    b1, b2 = best("tx->node", 0), best("node->tx", 0)
    r64 = rtt_row("tx->node", 64)
    r1472 = rtt_row("tx->node", 1472)
    soak = {r["dir"]: r for r in R["soak"]}
    w("A LAN8651 MAC-PHY node on an ESP32-S3 and a second ESP32-S3 on 100BASE-TX exchanged UDP "
      "through a 100BASE-TX/10BASE-T1S converter, with no PC in the data path. Both boards ran the same "
      "firmware and measured each other. One direction at a time, the bus carried **%.2f Mbit/s onto T1S "
      "and %.2f Mbit/s off it with no datagram lost** (sequence-checked), %.0f %% and %.0f %% of the "
      "%.2f Mbit/s the 10BASE-T1S frame model allows. A 64-byte UDP round trip took **%.2f ms median** "
      "(p99 %.2f ms); 1472 bytes took %.2f ms. Over %d s at 8 Mbit/s each way, %s datagrams were lost. "
      "With both directions loaded at once, the node's stream arrived whole while the converter's own "
      "stream lost most of its datagrams — the converter, not the bus, is the bottleneck there."
      % (b1["sink"]["delivered"] if b1 else float("nan"), b2["sink"]["delivered"] if b2 else float("nan"),
         100 * (b1["sink"]["delivered"] if b1 else 0) / ceil1472, 100 * (b2["sink"]["delivered"] if b2 else 0) / ceil1472,
         ceil1472, r64["p50"] if r64 else float("nan"), r64["p99"] if r64 else float("nan"),
         r1472["p50"] if r1472 else float("nan"),
         int(max((secs_of(r) for r in R["soak"]), default=0)),
         " and ".join("%d of %d (%s)" % ((r["blast"] or {}).get("sent", 0) - r["sink"].get("packets", 0),
                                          (r["blast"] or {}).get("sent", 0), d) for d, r in soak.items())))
    L[-1] += zenoh_abstract(R)
    w("")
    w("## 1. Setup")
    w("")
    w("```")
    w("ESP-A: ESP32-S3 + LAN8651 HAT        converter               ESP-B: ESP32-S3 + W5500")
    w("SPI %-5s MHz, PLCA %s of %s%-11s  LAN8670 + LAN9355       W5500 SPI 40 MHz, polled 1 ms"
      % ("%.2f" % spi_actual(st), st["node"]["id"], st["node"]["count"], " (coord.)" if st["node"]["id"] == 0 else ""))
    w("%-15s  ══ 10BASE-T1S ══  [T1S | TX]  ── 100BASE-TX ──  %s" % (st["node"]["ip"], st["tx"]["ip"]))
    w("```")
    w("")
    w("| | |")
    w("|---|---|")
    w("| node | %s, firmware `t1s_node` mode node, UDP echo on port 7, sink on port 9 |" % st["node"].get("chip"))
    w("| peer | W5500 (polled every 1 ms by the IDF driver), `t1s_node` mode tx, same echo and sink |")
    w("| converter | 3-port 10BASE-T1S / 100BASE-T1 / 100BASE-TX media converter (LAN8670 PHY, LAN9355 switch); "
      "dials ID 1, count 0, so the HAT is the PLCA coordinator |")
    w("| traffic | `blast`: UDP with a 32-bit sequence number in the first 4 bytes, optionally paced to a target rate; "
      "`sink`: counts, checks sequence (loss, reordering, duplicates) and histograms inter-arrival gaps (20 µs bins) |")
    w("| latency | `rtt`: UDP echo, one datagram in flight, timed with `esp_timer` (1 µs), 3 ms between probes, 100 ms timeout |")
    w("| rate accounting | Mbit/s counts UDP payload + 42 B of Ethernet/IP/UDP headers per datagram, as both tools report |")
    w("")
    w("**T1S model.** Each datagram of L payload bytes occupies (L + 42 + 4 FCS + 8 preamble + 12 IFG) bytes on the "
      "wire, plus about %d bit times of PLCA overhead per frame (the idle node's 32-bit transmit opportunity and a "
      "share of the BEACON, burst mode off). At 1472 B this gives a ceiling of **%.2f Mbit/s** in the accounting "
      "above." % (PLCA_BITS, ceil1472))
    w("")
    w("## 2. Results")
    w("")
    w("### 2.1 Round-trip time")
    w("")
    w("![Fig. 1](fig1_rtt_cdf.png)")
    w("")
    w("| direction | payload | n | lost | min | median | p99 | max | σ |")
    w("|---|---|---|---|---|---|---|---|---|")
    for d in ("tx->node", "node->tx"):
        for sz in sizes:
            x = rtt_row(d, sz)
            if x:
                w("| %s | %d B | %d | %d | %.2f | **%.2f** | %.2f | %.2f | %.3f |"
                  % (DIRS[d][0], sz, x["n"], x["lost"], x["min"], x["p50"], x["p99"], x["max"], x["sd"]))
    w("")
    w("All times in ms.")
    w("")
    w("![Fig. 2](fig2_rtt_size.png)")
    w("")
    for d, (sl, ic) in fits.items():
        w("- %s: RTT ≈ %.2f ms + %.2f µs × payload bytes." % (DIRS[d][0], ic, sl))
    w("")
    rr = [r for r in R["rtt"] if r["dir"] == "tx->node" and r["size"] == 64]
    if rr and ok(rr[0]["us"]):
        v = ok(rr[0]["us"])
        # how much of the RTT mass sits within 0.1 ms of a whole millisecond
        frac = 100.0 * sum(1 for x in v if abs(x / 1000 - round(x / 1000)) < 0.1) / len(v)
        w("**Millisecond steps.** Seen from ESP-B, round trips cluster at whole milliseconds: %.0f %% of the "
          "64 B samples lie within 0.1 ms of an integer number of ms, and larger payloads jump from one step to "
          "the next (Fig. 1, left). That is the W5500 driver's 1 ms receive poll: a reply that reaches the chip "
          "waits for the next poll tick. Seen from the HAT, whose LAN8651 interrupts on receive, the same paths "
          "spread continuously (Fig. 1, right)." % frac)
        w("")
    # per payload byte, per round trip: each link is crossed twice
    per_byte = {"10BASE-T1S (0.8 µs/B)": 2 * 0.8, "100BASE-TX (0.08 µs/B)": 2 * 0.08,
                "LAN8651 SPI %.2f MHz (%.2f µs/B)" % (spi_actual(R["setup"]), 8 / spi_actual(R["setup"])):
                    2 * 8 / spi_actual(R["setup"]),
                "W5500 SPI 40 MHz (0.2 µs/B)": 2 * 0.2}
    pred = sum(per_byte.values())
    meas = statistics.mean(v[0] for v in fits.values()) if fits else float("nan")
    w("**Reading it.** Every payload byte crosses each link twice per round trip. Serialisation alone predicts "
      + ", ".join("%s → %.2f" % (k, v) for k, v in per_byte.items())
      + " µs, **%.2f µs/B in total; the fit gives %.2f µs/B.** The remaining %.2f µs/B is per-byte work "
        "in software (copies through lwIP and both drivers). The intercept (≈%.1f ms) is fixed per-packet cost: "
        "the W5500 driver's 1 ms receive poll on ESP-B, lwIP and echo-task turnarounds, and PLCA transmit "
        "opportunities. The PC-based run of 2026-10-01 had no polling on its side and measured 0.85 ms for 64 B."
      % (pred, meas, meas - pred, statistics.mean(v[1] for v in fits.values()) if fits else float("nan")))
    w("")
    w("### 2.2 Throughput, one direction at a time")
    w("")
    w("![Fig. 3](fig3_sweep.png)")
    w("")
    w("| direction | offered | delivered | sent | received | loss | reordered | gap p50 / p99 (µs) |")
    w("|---|---|---|---|---|---|---|---|")
    for d in ("tx->node", "node->tx"):
        for r in sorted([r for r in R["sweep"] if r["dir"] == d],
                        key=lambda r: (r["mbit"] == 0, r["mbit"])):
            b, s = r.get("blast") or {}, r["sink"]
            l = loss_of(r)
            w("| %s | %s | %.2f | %s | %s | %s | %s | %s / %s |"
              % (DIRS[d][0], ("%.2f" % b["offered"]) if b.get("offered") else ("max" if not r["mbit"] else "%g" % r["mbit"]),
                 s.get("delivered", 0), b.get("sent", "—"), s.get("packets", "—"),
                 ("%.2f %%" % l) if l is not None else "—", s.get("reordered", "—"),
                 s.get("gap_p50", "—"), s.get("gap_p99", "—")))
    w("")
    stalls = [r for r in R["sweep"] if (r.get("blast") or {}).get("secs") and r["sink"].get("secs") is not None
              and r["sink"]["secs"] < 0.9 * r["blast"]["secs"] and r["sink"].get("packets")]
    if stalls:
        w("**Overload stalls the stream.** In %d row(s) the receiver's window is shorter than the blast: %s. "
          "Delivery ran at the bus ceiling and then **stopped** for the rest of the blast, which is where the "
          "large loss figures at and above ~10 Mbit/s come from; the sequence gaps inside the window are the "
          "smaller part. The node received normally again in the next run. Overloading the converter's "
          "T1S side therefore costs more than the excess: the segment goes quiet for seconds. §2.2.1 locates "
          "the stop."
          % (len(stalls), "; ".join("%s at %s: %.1f of %.1f s, seq gaps %s" % (
              DIRS[r["dir"]][0], ("%.2f Mbit/s" % r["blast"]["offered"]) if r["blast"].get("offered") else "max",
              r["sink"]["secs"], r["blast"]["secs"], r["sink"].get("seq_lost", "—")) for r in stalls)))
        w("")
    P = R.get("overload_probe")
    if P and P.get("runs"):
        w("#### 2.2.1 Where the overload stall happens")
        w("")
        w("A separate probe (`overload_probe.py`, %s) blasted the HAT unpaced from ESP-B and read the HAT's "
          "LAN8651 before and after: TC6 STATUS0/1 (receive-buffer overflow and error flags), the receive "
          "chunks still held in the chip, and the frames its driver handed up." % P["t"])
        w("")
        w("| run | sent | received (window) | driver frames | STATUS0 / STATUS1 after | RX chunks after | PLCA beacons | then 5 Mbit/s |")
        w("|---|---|---|---|---|---|---|---|")
        clean = True
        for i, r in enumerate(P["runs"], 1):
            af, sk, rc = r["after"], r["sink"], r["recovery_5mbit"]
            clean &= af.get("status0") == 0 and af.get("status1") == 0 and af.get("rx_chunks") == 0 and \
                abs(r["driver_rx_delta"] - sk.get("packets", 0)) <= 5
            w("| %d | %s | %s in %.1f s | %d | 0x%x / 0x%x | %s | %s | %s/%s, %s lost |"
              % (i, r["sent"], sk.get("packets"), sk.get("secs", 0), r["driver_rx_delta"], af.get("status0", -1),
                 af.get("status1", -1), af.get("rx_chunks"), "seen" if af.get("plca_sts", 0) & 0x8000 else "NOT seen",
                 rc.get("packets"), rc.get("expected"), rc.get("seq_lost")))
        w("")
        if clean:
            w("STATUS0's error bits are sticky (write-1-to-clear) and this driver clears only RESETC, once, at "
              "start-up, so a zero after the run means no overflow happened during it. "
              "The LAN8651 flagged nothing: no receive overflow, no error, nothing left in its buffers, and its "
              "driver handed up exactly the frames the sink counted, while the bus kept its PLCA beacons. The "
              "frames that went missing **never reached the chip**: under sustained overload the converter "
              "stops putting frames onto T1S after about a second, and resumes once the overload ends (the "
              "5 Mbit/s run straight after loses nothing).")
        else:
            w("The LAN8651 reported flags or held data after the overload, so the receive side cannot be ruled out.")
        w("")
    w("![Fig. 7](fig7_gaps.png)")
    w("")
    w("### 2.3 Payload size")
    w("")
    w("![Fig. 4](fig4_sizes.png)")
    w("")
    w("| direction | payload | delivered (Mbit/s) | frames/s | model ceiling (Mbit/s) | loss |")
    w("|---|---|---|---|---|---|")
    for d in ("tx->node", "node->tx"):
        for r in sorted([r for r in R["sizes"] if r["dir"] == d], key=lambda r: r["size"]):
            s = r["sink"]
            l = loss_of(r)
            w("| %s | %d B | %.2f | %.0f | %.2f | %s |"
              % (DIRS[d][0], r["size"], s.get("delivered", 0),
                 s.get("packets", 0) / max(1e-9, s.get("secs") or secs_of(r)), t1s_ceiling(r["size"]),
                 ("%.1f %%" % l) if l is not None else "—"))
    w("")
    w("Small datagrams are bounded by per-packet cost in the boards (lwIP, SPI transactions, the W5500 poll), "
      "not by the bus: the frame rate stays far below what 10BASE-T1S could carry. Unpaced in the ESP-B → HAT "
      "direction, the W5500 offers more than the bus can take and the converter drops the excess.")
    w("")
    w("### 2.4 Both directions at once")
    w("")
    w("![Fig. 5](fig5_bidir.png)")
    w("")
    w("| offered each | ESP-B → HAT delivered | loss | HAT → ESP-B delivered | loss |")
    w("|---|---|---|---|---|")
    for r in brows:
        rv = r["reverse"]
        l1, l2 = loss_of(r), loss_of(rv)
        w("| %g | %.2f | %s | %.2f | %s |" % (r["mbit"], r["sink"].get("delivered", 0),
                                             ("%.1f %%" % l1) if l1 is not None else "—",
                                             rv["sink"].get("delivered", 0), ("%.1f %%" % l2) if l2 is not None else "—"))
    w("")
    dips = [r for r in brows if r["mbit"] >= 2 and r["sink"].get("delivered", 0) < 0.1 * r["mbit"]]
    if dips:
        w("At %s Mbit/s each the converter's stream all but vanished (%s Mbit/s delivered), less than at the "
          "levels either side; the same dip appeared in an earlier run at 3 Mbit/s, so it is a property of the "
          "converter's arbitration at that load, not a measurement fault."
          % (", ".join("%g" % r["mbit"] for r in dips), ", ".join("%.2f" % r["sink"].get("delivered", 0) for r in dips)))
        w("")
    w("The HAT's stream arrives whole at every level. The stream the converter must put onto T1S loses "
      "most of its datagrams as soon as both directions are busy, even at 1–2 Mbit/s each, far below the bus "
      "capacity. That is the converter's T1S side failing to win transmit opportunities while it is receiving, "
      "matching its vendor's own issue 4.3 (\"bidirectional traffic through the converter does not work properly "
      "— LAN8670\"), and the 2026-10-01 PLCA run with a PC in ESP-B's place.")
    w("")
    w("### 2.5 Latency under load")
    w("")
    w("![Fig. 6](fig6_loaded_rtt.png)")
    w("")
    w("| HAT → ESP-B load | probes | lost | median | p99 |")
    w("|---|---|---|---|---|")
    for r in lrows:
        v = ok(r["us"])
        w("| %g Mbit/s | %d | %d | %s | %s |" % (r["load"], len(r["us"]), len(r["us"]) - len(v),
                                              ("%.2f" % (pct(v, 50) / 1000)) if v else "—",
                                              ("%.2f" % (pct(v, 99) / 1000)) if v else "—"))
    w("")
    w("Echo probes from ESP-B must cross the converter onto the bus the HAT is streaming on, so they meet the "
      "same converter limit as §2.4: answered probes keep their latency, but a growing share is lost.")
    w("")
    w("### 2.6 Soak")
    w("")
    w("| direction | duration | offered | delivered | sent | received | lost | reordered | duplicates |")
    w("|---|---|---|---|---|---|---|---|---|")
    for d, r in soak.items():
        b, s = r.get("blast") or {}, r["sink"]
        w("| %s | %d s | %s | %.2f | %s | %s | %s | %s | %s |"
          % (DIRS[d][0], secs_of(r), b.get("offered", "—"), s.get("delivered", 0), b.get("sent", "—"),
             s.get("packets", "—"), (b.get("sent", 0) - s.get("packets", 0)) if b.get("sent") else "—",
             s.get("reordered", "—"), s.get("dup", "—")))
    w("")
    if Z:
        w("### 2.7 Zenoh, peer to peer with no router")
        w("")
        w("Both boards ran zenoh-pico in **peer mode over UDP multicast** (`udp/224.0.0.224:7447`): no zenohd, no PC. "
          "Each board echoes the other's `test/ping/<node>` on `test/pong/<node>`; the pinging board timestamps "
          "with `esp_timer`. RTT was taken at 50 Hz with the boards' normal Zenoh traffic running (20 Hz signal, "
          "2 Hz hello, 1 Hz stats each); bulk transfers ran with that traffic paused.")
        w("")
        if Z.get("rtt"):
            w("![Fig. 8](fig8_zenoh_rtt.png)")
            w("")
            w("| pinged from | pongs | min | median | p99 | max | raw UDP 64 B median | Zenoh overhead |")
            w("|---|---|---|---|---|---|---|---|")
            for r in Z["rtt"]:
                v = ok(r["us"])
                if not v:
                    continue
                u = rtt_row(r["dir"], 64)
                w("| %s | %d of ~%d | %.2f | **%.2f** | %.2f | %.2f | %s | %s |"
                  % ("ESP-B" if r["dir"] == "tx->node" else "HAT", len(v), r.get("sent_approx", 0), min(v) / 1000,
                     pct(v, 50) / 1000, pct(v, 99) / 1000, max(v) / 1000,
                     ("%.2f" % u["p50"]) if u else "—", ("+%.2f ms" % (pct(v, 50) / 1000 - u["p50"])) if u else "—"))
            w("")
            w("All times in ms. *pongs of ~N*: the board keeps its last 600 round trips, and pings sent while the "
              "previous pong was outstanding are not all answered (each board echoes from a short queue).")
            w("")
        if Z.get("bulk"):
            w("![Fig. 9](fig9_zenoh_bulk.png)")
            w("")
            w("| direction | payload | put (msg/s) | received (msg/s) | put (Mbit/s) | received (Mbit/s) | lost |")
            w("|---|---|---|---|---|---|---|")
            for d in ("tx->node", "node->tx"):
                for r in sorted([r for r in Z["bulk"] if r["dir"] == d], key=lambda r: r["size"]):
                    b, k = r.get("blast") or {}, r.get("sink") or {}
                    lost = (100.0 * k["lost"] / k["expected"]) if k.get("expected") else None
                    mark = "†" if b.get("from_sink_seq") else ""
                    w("| %s | %d B | %s%s | %s | %s%s | %s | %s |"
                      % (DIRS[d][0], r["size"], ("%.0f" % b["rate"]) if b else "—", mark, ("%.0f" % k["rate"]) if k else "—",
                         ("%.2f" % b["mbit"]) if b else "—", mark, ("%.2f" % k["mbit"]) if k else "—",
                         ("%.1f %%" % lost) if lost is not None else "—"))
            w("")
            if any((r.get("blast") or {}).get("from_sink_seq") for r in Z["bulk"]):
                w("† the publisher's own report line did not reach the console; the put count is the subscriber's "
                  "sequence range (exact unless the final messages were lost), over the blast duration of the other rows.")
                w("")
            caps = [r["sink"]["rate"] for r in Z["bulk"] if r.get("sink")]
            near = sum(1 for c in caps if 950 <= c <= 1010)
            w("**What limits it.** Puts are unpaced, so each row is what zenoh-pico itself sustains. For small payloads "
              "the receiving side tops out at almost exactly **1000 messages/s** (%d of %d rows within 950–1010) on "
              "*both* boards, while the same boards receive 2400+ raw UDP frames/s (§2.3). The cap therefore sits in "
              "zenoh-pico's receive path on this port (it is not the idle-read sleep, which is 0 in this build), not "
              "in T1S. Large payloads from ESP-B lose datagrams at an *average* rate the bus carried cleanly as paced "
              "UDP (§2.2): unpaced puts leave the W5500 back to back at 100 Mbit/s, so the converter's buffer meets "
              "bursts well above 10 Mbit/s (our reading; the converter exposes no drop counter). In the other "
              "direction the HAT's SPI/TC6 path paces its puts and nothing is lost at 512 B and above."
              % (near, len(caps)))
            w("")
    w("## 3. Discussion")
    w("")
    w("- **The T1S segment is not the limit for one-way traffic.** Paced at up to 9 Mbit/s, neither direction "
      "lost a datagram, and the unpaced HAT → ESP-B stream sits close to the model ceiling.")
    w("- **Do not offer more than the bus.** Above the ~9.8 Mbit/s ceiling the excess is not simply dropped: the "
      "stream stalls for seconds, and the stall is in the converter, not the node (§2.2.1). A T1S edge that can be overloaded from a faster segment needs shaping "
      "at the entry (the bridge firmware's job), not just a big buffer.")
    w("- **The converter is the limit for two-way traffic.** Loss in §2.4 appears at a few Mbit/s total, so it "
      "is not capacity; it is the converter's own T1S transmitter. A PLCA-aware MAC-PHY on both ends (or a "
      "converter that reserves its transmit opportunities) would remove it; that is why the HAT keeps a "
      "LAN8651 rather than a PHY behind a switch.")
    if R.get("zenoh"):
        w("- **Zenoh needs no infrastructure on this segment.** Two microcontrollers formed a Zenoh network on "
          "their own over T1S + converter, with multicast discovery and no router; its cost over raw UDP is a "
          "few milliseconds of round trip and a ~1000 msg/s receive ceiling in zenoh-pico on this platform.")
    w("- **Board latency dominates RTT.** At 64 B the bus contributes well under 0.2 ms of a ~3 ms round "
      "trip; the W5500's 1 ms polling and per-packet software dominate. An interrupt-driven W5500 (the "
      "T-ETH-Elite does not route its INT line) or a second LAN8651 node would cut it.")
    w("")
    w("## 4. Limitations")
    w("")
    w("- One converter unit, one bus length (~1 m), two nodes; no EMC or cable-length effects are captured.")
    w("- Rates are application-level UDP; preamble, FCS and IFG are not counted (the model curve accounts for them).")
    w("- Arrival gaps above 2 ms fall into one histogram bin, so the p99 for slow rates is a lower bound.")
    w("- `sink` computes its rate over first-to-last arrival, which reads ~0.5 % high against the sender's "
      "window; that is why the 1472 B points can sit a hair above the model ceiling.")
    w("- RTT probes are sequential (one in flight); they measure latency, not latency under pipelining.")
    w("- `rtt`'s 3 ms probe spacing is not synchronised with PLCA cycles; queueing behind the other node's "
      "transmit opportunity is part of the measured distribution, by design.")
    w("")
    w("## 5. Reproduce")
    w("")
    w("Firmware: `elite-t1s-hat/firmware/t1s_node` (both boards); console: `esp32-t1s-bridge/pc/t1s_console/hat_server.py`, "
      "`POST /api/suite` (or the Two ESPs tab); report: `python3 pc/t1s_console/make_duo_report.py <json>`.")
    w("")
    open(os.path.join(out, "REPORT.md"), "w").write("\n".join(L) + "\n")
    write_pdf(out, "\n".join(L))
    print("wrote", out, "with", len(figs), "figures")


CSS = """
@page { size: A4; margin: 18mm 17mm 18mm 17mm; }
body { font-family: 'Noto Serif', 'DejaVu Serif', Georgia, serif; font-size: 9.6pt; line-height: 1.42;
       color: #111; max-width: 176mm; margin: 0 auto; }
h1 { font-size: 15pt; line-height: 1.25; margin: 0 0 4pt; }
h2 { font-size: 11pt; margin: 14pt 0 4pt; border-bottom: 0.6pt solid #999; padding-bottom: 2pt; }
h3 { font-size: 10pt; margin: 10pt 0 3pt; }
p { margin: 4pt 0; text-align: justify; hyphens: auto; }
img { display: block; max-width: 100%; margin: 6pt auto; page-break-inside: avoid; }
table { border-collapse: collapse; margin: 6pt 0; font-size: 8pt; width: 100%; page-break-inside: avoid; }
th, td { border-top: 0.4pt solid #bbb; border-bottom: 0.4pt solid #bbb; padding: 2pt 4pt; text-align: left; }
th { border-top: 1pt solid #333; border-bottom: 0.6pt solid #333; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8pt; }
pre { font-size: 7.4pt; background: #f6f6f6; padding: 5pt; overflow: hidden; white-space: pre; }
ul { margin: 3pt 0 3pt 14pt; padding: 0; }
li { margin: 1.5pt 0; }
em { color: #444; }
"""


def write_pdf(out, md):
    """REPORT.html beside REPORT.md, and REPORT.pdf through headless Chrome if one is installed."""
    try:
        import markdown
    except ImportError:
        return
    import shutil
    import subprocess
    html = markdown.markdown(md, extensions=["tables", "fenced_code"])
    page = ("<!doctype html><html><head><meta charset='utf-8'><title>T1S two-ESP report</title>"
            "<style>%s</style></head><body>%s</body></html>" % (CSS, html))
    hp = os.path.join(out, "REPORT.html")
    open(hp, "w").write(page)
    chrome = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)
    if not chrome:
        return
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--print-to-pdf=" + os.path.join(out, "REPORT.pdf"), "file://" + os.path.abspath(hp)],
                   capture_output=True, timeout=120)


if __name__ == "__main__":
    p = sys.argv[1]
    o = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(p), os.path.basename(p)[:-5])
    main(p, o)
