#!/usr/bin/env python3
"""Figures + REPORT.md for the 10BASE-T1S bench, from what the :8813 console saved.

    python3 tools/make_report.py

Reads ~/.cache/t1s_hat_fulltests.json and ~/.cache/t1s_hat_demos.json, copies them into
data/ (so the report can be regenerated from the repo), and writes
figs/*.png and REPORT.md.

Demo runs are only used if they carry the PLCA readout ("plca" key) — older runs used a
sink sequence that the node could not answer during its own blast and are not comparable.
Of those, the last PLCA run and the last CSMA run are compared.
"""
import json
import os
import shutil
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, ".."))
FIGS = os.path.join(OUT, "figs")
DATA = os.path.join(OUT, "data")
CACHE = os.path.expanduser("~/.cache")

BLUE, GREEN, AMBER, GREY, RED = "#0064e0", "#248a3d", "#b25000", "#86868b", "#d70015"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "figure.dpi": 140, "savefig.bbox": "tight"})


def load(name):
    src = os.path.join(CACHE, name)
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(src):
        shutil.copy(src, os.path.join(DATA, name.replace("t1s_hat_", "")))
    p = os.path.join(DATA, name.replace("t1s_hat_", ""))
    return json.load(open(p)) if os.path.exists(p) else []


def save(fig, name):
    fig.savefig(os.path.join(FIGS, name))
    plt.close(fig)
    return "figs/" + name


def main():
    os.makedirs(FIGS, exist_ok=True)
    full = load("t1s_hat_fulltests.json")
    demos = [d for d in load("t1s_hat_demos.json") if d.get("plca")]
    by_spi = {}
    for r in full:
        spi = r["setup"]["hat"].get("hat_spi")
        if spi and "summary" in r:
            by_spi[spi] = r                      # last run per clock wins
    spis = sorted(by_spi)
    figs = {}

    # 1. throughput by SPI clock
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    w = 0.36
    a = [by_spi[s]["summary"]["max_clean_pc2hat_mbit"] for s in spis]
    b = [by_spi[s]["summary"]["max_hat2pc_mbit"] for s in spis]
    x = range(len(spis))
    ax.bar([i - w / 2 for i in x], a, w, label="PC → HAT, < 1 % loss", color=BLUE)
    ax.bar([i + w / 2 for i in x], b, w, label="HAT → PC, max", color=GREEN)
    for i, (u, v) in enumerate(zip(a, b)):
        ax.text(i - w / 2, u + 0.15, "%.1f" % u, ha="center", fontsize=9)
        ax.text(i + w / 2, v + 0.15, "%.1f" % v, ha="center", fontsize=9)
    ax.axhline(10, color=GREY, ls="--", lw=1)
    ax.text(len(spis) - 0.5, 10.15, "10 Mbit/s line rate", ha="right", color=GREY, fontsize=8)
    ax.set_xticks(list(x), ["SPI %d MHz" % s for s in spis])
    ax.set_ylabel("Mbit/s (UDP payload + headers)")
    ax.set_ylim(0, 11.5)
    ax.set_title("Throughput through converter ═ T1S ═ LAN8651 HAT, by HAT SPI clock")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    figs["tput"] = save(fig, "01_throughput_by_spi.png")

    # 2. load sweep
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.4))
    cols = {12: GREY, 20: AMBER, 25: BLUE}
    for s in spis:
        L = by_spi[s]["load"]
        t = [r["target_mbit"] for r in L]
        ax1.plot(t, [r["delivered_mbit"] for r in L], "o-", color=cols.get(s, BLUE), label="SPI %d MHz" % s, ms=4)
        ax2.plot(t, [r["loss_pct"] for r in L], "o-", color=cols.get(s, BLUE), label="SPI %d MHz" % s, ms=4)
    ax1.plot([0, 10], [0, 10], color=GREY, ls=":", lw=1)
    ax1.set_xlabel("offered PC → HAT (Mbit/s)")
    ax1.set_ylabel("delivered (Mbit/s)")
    ax1.set_title("Offered vs delivered")
    ax1.legend(frameon=False)
    ax2.axhline(1, color=RED, ls="--", lw=1)
    ax2.set_xlabel("offered PC → HAT (Mbit/s)")
    ax2.set_ylabel("loss (%)")
    ax2.set_title("Loss (1 % line dashed)")
    figs["load"] = save(fig, "02_load_sweep.png")

    # 3. latency by size (fastest clock)
    if spis:
        s = spis[-1]
        lat = by_spi[s]["latency"]
        fig, ax = plt.subplots(figsize=(6.4, 3.2))
        for i, r in enumerate(lat):
            ax.plot([r["min"], r["max"]], [i, i], color=GREY, lw=1)
            ax.plot([r["p50"], r["p99"]], [i, i], color=BLUE, lw=6, solid_capstyle="butt")
            ax.plot(r["avg"], i, "o", color="white", mec=BLUE, ms=6)
            ax.text(r["max"] + 0.1, i, "avg %.2f · p99 %.2f ms · loss %s %%" % (r["avg"], r["p99"], r["loss_pct"]),
                    va="center", fontsize=8)
        ax.set_yticks(range(len(lat)), ["%d B" % r["size"] for r in lat])
        ax.set_xlabel("PC → HAT ping RTT (ms) — line: min–max, bar: p50–p99, dot: mean")
        ax.set_xlim(0, max(r["max"] for r in lat) * 1.9)
        ax.set_title("Round-trip latency by size (SPI %d MHz, 200 pings each)" % s)
        figs["lat"] = save(fig, "03_latency_by_size.png")

    plca = next((d for d in reversed(demos) if "PLCA" in d["mode"]["converter"]), None)
    csma = next((d for d in reversed(demos) if "CSMA" in d["mode"]["converter"]), None)

    # 4. gap histograms, PLCA vs CSMA
    if plca and csma:
        names = ["HAT alone", "quiet keeps slot", "both flood"]
        fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.2), sharey=False)
        for ax, n in zip(axes, names):
            for run, col, lab in ((plca, GREEN, "PLCA"), (csma, AMBER, "CSMA/CD")):
                ph = next((p for p in run["phases"] if p["name"] == n), None)
                if not ph or not ph.get("hat2pc", {}).get("hist"):
                    continue
                h = ph["hat2pc"]["hist"]
                tot = sum(h) or 1
                xs = [0.1 * i + 0.05 for i in range(len(h))]
                ax.step(xs, [100 * v / tot for v in h], where="mid", color=col, label=lab, lw=1.6)
                fm = ph["hat2pc"]["frame_ms"]
            ax.axvline(fm, color=GREY, ls="--", lw=1)
            ax.axvline(2 * fm, color=GREY, ls=":", lw=1)
            ax.set_title({"HAT alone": "HAT alone", "quiet keeps slot": "HAT floods + PC sends 1 Mbit/s",
                          "both flood": "both flood"}[n], fontsize=10)
            ax.set_xlabel("gap between HAT frames at the PC (ms)")
            ax.set_xlim(0, 4)
        axes[0].set_ylabel("% of gaps")
        axes[0].legend(frameon=False)
        fig.suptitle("Inter-frame gaps (1000 B UDP; dashed = 1 frame time on 10 Mbit/s, dotted = 2)", fontsize=10)
        figs["gaps"] = save(fig, "04_gap_histograms_plca_vs_csma.png")

        # 5. PLCA vs CSMA summary
        def ph(run, n):
            return next((p for p in run["phases"] if p["name"] == n), {})
        rows = [("ping loss behind own flood", lambda r: ph(r, "own flood").get("ping", {}).get("loss_pct")),
                ("HAT→PC loss, HAT floods + PC 1 Mbit/s", lambda r: ph(r, "quiet keeps slot").get("hat2pc", {}).get("loss_pct")),
                ("HAT→PC loss, both flood", lambda r: ph(r, "both flood").get("hat2pc", {}).get("loss_pct")),
                ("PC→HAT loss, HAT floods + PC 1 Mbit/s", lambda r: ph(r, "quiet keeps slot").get("pc2hat", {}).get("loss_pct"))]
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 3.4), gridspec_kw={"width_ratios": [2.2, 1]})
        y = range(len(rows))
        pv = [f(plca) or 0 for _, f in rows]
        cv = [f(csma) or 0 for _, f in rows]
        ax1.barh([i + 0.2 for i in y], pv, 0.38, color=GREEN, label="PLCA")
        ax1.barh([i - 0.2 for i in y], cv, 0.38, color=AMBER, label="CSMA/CD")
        for i, (p_, c_) in enumerate(zip(pv, cv)):
            ax1.text(p_ + 1, i + 0.2, "%.1f %%" % p_, va="center", fontsize=8)
            ax1.text(c_ + 1, i - 0.2, "%.1f %%" % c_, va="center", fontsize=8)
        ax1.set_yticks(list(y), [r[0] for r in rows])
        ax1.invert_yaxis()
        ax1.set_xlabel("loss (%)")
        ax1.set_xlim(0, 110)
        ax1.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
        ax1.set_title("Loss — last row is the converter's own stream (vendor issue 4.3)", fontsize=10)
        st = [ph(plca, "both flood").get("hat2pc", {}).get("gap_max", 0),
              ph(csma, "both flood").get("hat2pc", {}).get("gap_max", 0)]
        ax2.bar(["PLCA", "CSMA/CD"], st, color=[GREEN, AMBER])
        ax2.set_yscale("log")
        for i, v in enumerate(st):
            ax2.text(i, v * 1.15, "%.0f ms" % v, ha="center", fontsize=9)
        ax2.set_ylabel("ms (log)")
        ax2.set_title("Longest stall of the HAT, both flooding", fontsize=10)
        figs["cmp"] = save(fig, "05_plca_vs_csma.png")

    # ---- REPORT.md
    now = time.strftime("%Y-%m-%d %H:%M")
    s25 = by_spi.get(max(spis)) if spis else None
    L = ["# 10BASE-T1S bench report", "", "_Generated %s by `pc/t1s_console/make_report.py` from `data/`._" % now, "",
         "```", "PC enp4s0 ─RJ45─ TSN Lab 10Base-T1S Converter ═10BASE-T1S═ TSN Lab LAN8651 HAT ─SPI─ ESP32-S3 (t1s_node)",
         "```", "",
         "The HAT runs `t1s_node` (elite-t1s-hat repo): Espressif's LAN865x driver on SPI3, lwIP, UDP echo/sink, "
         "and optionally zenoh-pico over the T1S interface. The converter is the PLCA coordinator (dial ID 0 / count 2) "
         "unless stated; the HAT is ID 1.", ""]
    if s25:
        su = s25["summary"]
        L += ["## Headline (SPI %d MHz)" % max(spis), "",
              "| | |", "|---|---|",
              "| ping RTT, 64 B | %s ms avg, p99 %s ms, 0 loss |" % (su["rtt_avg_ms_64B"], su["rtt_p99_ms_64B"]),
              "| PC → HAT without loss | %s Mbit/s |" % su["max_clean_pc2hat_mbit"],
              "| HAT → PC | %s Mbit/s |" % su["max_hat2pc_mbit"],
              "| 60 s at 10 pings/s | %s %% loss |" % su["stability_loss_pct"], ""]
    if "tput" in figs:
        L += ["## Throughput by SPI clock", "", "![](%s)" % figs["tput"], "",
              "Every frame crosses the ESP32↔LAN8651 SPI link (OPEN Alliance TC6), so its clock sets the ceiling: "
              "12 MHz tops out near 6.4 Mbit/s, 25 MHz reaches ~95 % of the 10 Mbit/s line.", ""]
    if "load" in figs:
        L += ["## Load sweep", "", "![](%s)" % figs["load"], ""]
    if "lat" in figs:
        L += ["## Latency", "", "![](%s)" % figs["lat"], "",
              "RTT grows with size because each frame is clocked onto the 10 Mbit/s wire twice (request and reply): "
              "a 1400 B ping spends ~2.3 ms on the wire alone.", ""]
    if "gaps" in figs:
        p = plca["plca"]
        L += ["## PLCA vs CSMA/CD", "",
              "PLCA as read from the HAT: %s nodes, transmit opportunity %s bit times (%s µs), max burst %s → idle cycle "
              "≈ %s µs, worst wait behind one 1518 B frame ≈ %s ms." % (p["node_count"], p["to_bits"], p["to_us"],
                                                                         p["max_burst"], p["idle_cycle_us"], p["worst_wait_ms_1518B"]), "",
              "![](%s)" % figs["gaps"], "", "![](%s)" % figs["cmp"], "",
              "PLCA removes collisions: the node with a PLCA-capable MAC (the LAN8651 HAT) lost nothing in any phase, "
              "where CSMA/CD lost up to 27 % and stalled it for seconds under contention. The converter's own stream is "
              "starved in both modes — the vendor's manual lists bidirectional traffic through the converter as a "
              "LAN8670 issue not fixable in software (issue 4.3).", ""]
    L += ["## Files", "", "- per-run reports: `t1s_hat_*.md` (full tests), `t1s_plca_*.md` (PLCA demo)",
          "- comparison table: `PLCA_vs_CSMA_20261001.md`", "- raw data: `data/`", ""]
    open(os.path.join(OUT, "REPORT.md"), "w").write("\n".join(L))
    print("wrote", os.path.join(OUT, "REPORT.md"), "and", len(figs), "figures")


if __name__ == "__main__":
    main()
