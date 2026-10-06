"""Time synchronisation over the T1S bench: report from the raw console logs in docs/t1s_results/sync/.

    python3 make_ptp_report.py SYNC_DIR OUT_DIR

Two kinds of log:
  sync_*.txt   `sync` runs (ESP-B asks the node; t, offset, delay [, hardware offset, delay])
  lock*.txt    `ptp lock` runs (the node's PI servo on its LAN8651 clock; offset, delay, frequency per s)
The file names carry the configuration: lock = W5500 polled, lockj = polled + jittered spacing,
lockint = W5500 interrupt, lockdrv = + driver-level t2, lock2s = + post-send t3 (reverted),
lockfinal = the kept configuration; _kp_ki = the servo gains.
"""
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_campaign_report import C_OFF, C_ONTO, C_Z, plt, save  # noqa: E402
from make_duo_report import write_pdf  # noqa: E402

RE_L = re.compile(r"ptpl: (\d+) offset (-?\d+) ns delay (\d+) ns freq ([+-]?\d+) ppb")
RE_GAIN = re.compile(r"kp ([\d.]+) ki ([\d.]+)")


def read_lock(path):
    txt = open(path).read()
    rows = [(int(m.group(1)), int(m.group(2)) / 1000.0, int(m.group(3)) / 1000.0, float(m.group(4)) / 1000.0)
            for m in RE_L.finditer(txt)]
    name = os.path.basename(path)[:-4]
    g = re.search(r"_([\d.]+)_([\d.]+)$", name)
    kp, ki = (float(g.group(1)), float(g.group(2))) if g else (None, None)
    if kp is None:
        m = RE_GAIN.search(txt)
        kp, ki = (float(m.group(1)), float(m.group(2))) if m else (0.7, 0.3)
    if name.startswith("lockfinal"):
        kp, ki = 0.2, 0.02
    return name, kp, ki, rows


def stats(rows, after=20):
    late = [r for r in rows if r[0] >= after] or rows
    off = [r[1] for r in late]
    fr = [r[3] for r in late]
    return {"n": len(late), "mean": st.mean(off), "sd": st.pstdev(off), "max": max(abs(x) for x in off),
            "delay": st.median(r[2] for r in rows), "freq": st.mean(fr), "freq_sd": st.pstdev(fr)}


def read_sync(path):
    rows = []
    for line in open(path).read().splitlines():
        if line.startswith("syncs:"):
            for tok in line.split()[1:]:
                try:
                    rows.append(tuple(map(int, tok.split(","))))
                except ValueError:
                    pass
    return rows


def scatter(t, y):
    n = len(t)
    mt, my = sum(t) / n, sum(y) / n
    b = sum((a - mt) * (c - my) for a, c in zip(t, y)) / sum((a - mt) ** 2 for a in t)
    res = [c - (b * a + (my - b * mt)) for a, c in zip(t, y)]
    return b, st.pstdev(res)


def per_window(rows, ti, oi, di, w=2.0):
    best = {}
    for r in rows:
        k = int(r[ti] / 1e6 // w)
        if k not in best or r[di] < best[k][di]:
            best[k] = r
    return [best[k] for k in sorted(best)]


CONF = [  # (file prefix, label)
    ("lock_", "W5500 polled"),
    ("lockj_", "polled, jittered spacing"),
    ("lockint_", "W5500 interrupt (IO14)"),
    ("lockdrv_", "interrupt + driver-level t2"),
    ("lock2s_", "+ post-send t3 (reverted)"),
    ("lockfinal_", "kept: interrupt + driver t2"),
]


def label(name):
    for p, l in CONF:
        if name.startswith(p):
            return l
    return "W5500 polled (first run)" if name == "lock1" else name


def main(src, out):
    os.makedirs(out, exist_ok=True)
    locks = [read_lock(os.path.join(src, f)) for f in sorted(os.listdir(src)) if f.startswith("lock") and f.endswith(".txt")]
    locks = [x for x in locks if x[3]]

    # Fig P1: the master-side steps at the default gains
    pick = [x for x in locks if x[1] == 0.2 and x[2] == 0.02]
    order = ["lock_0.2_0.02", "lockj_0.2_0.02", "lockint_0.2_0.02", "lockdrv_0.2_0.02", "lockfinal_1"]
    pick = sorted([x for x in pick if x[0] in order], key=lambda x: order.index(x[0]))
    cols = ["#aaaaaa", "#888888", C_Z, C_OFF, C_ONTO]
    fig, ax = plt.subplots(figsize=(6.6, 2.8))
    for (name, kp, ki, rows), c in zip(pick, cols):
        ax.plot([r[0] for r in rows if r[0] >= 2], [r[1] for r in rows if r[0] >= 2], color=c, lw=1.0,
                label="%s (σ %.0f µs)" % (label(name), stats(rows)["sd"]))
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("time since lock (s)")
    ax.set_ylabel("offset master − node (µs)")
    ax.set_ylim(-300, 300)
    ax.legend(fontsize=6.8, frameon=False, ncol=2, loc="lower left")
    save(fig, out, "p1_offset_steps")

    # Fig P2: gains, interrupt-driven master
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.5))
    for (name, kp, ki, rows), c in zip(sorted([x for x in locks if x[0].startswith("lockint_")], key=lambda x: -x[1]),
                                       [C_OFF, C_ONTO, C_Z]):
        s = stats(rows)
        axs[0].plot([r[0] for r in rows if r[0] >= 2], [r[1] for r in rows if r[0] >= 2], color=c, lw=0.9,
                    label="kp %g ki %g (σ %.0f µs)" % (kp, ki, s["sd"]))
        axs[1].plot([r[0] for r in rows], [r[3] for r in rows], color=c, lw=0.9)
    axs[0].set_ylim(-250, 250)
    axs[0].set_xlabel("s")
    axs[0].set_ylabel("offset (µs)")
    axs[0].legend(fontsize=6.5, frameon=False)
    axs[1].set_xlabel("s")
    axs[1].set_ylabel("frequency correction (ppm)")
    axs[1].set_ylim(-120, 80)
    fig.tight_layout()
    save(fig, out, "p2_gains")

    # sync exchanges: software vs node hardware stamps
    sw = read_sync(os.path.join(src, "sync_sw_both.txt"))
    hw = [r for r in read_sync(os.path.join(src, "sync_hw_node.txt")) if len(r) == 5]
    ex = []
    if sw:
        t = [r[0] / 1e6 for r in sw]
        b, sd = scatter(t, [r[1] for r in sw])
        win = per_window(sw, 0, 1, 2)
        _, sdw = scatter([r[0] / 1e6 for r in win], [r[1] for r in win])
        ex.append(("software, both boards", len(sw), sd, sdw, b))
    if hw:
        t = [r[0] / 1e6 for r in hw]
        b, sd = scatter(t, [r[3] / 1000 for r in hw])
        win = per_window(hw, 0, 3, 4)
        _, sdw = scatter([r[0] / 1e6 for r in win], [r[3] / 1000 for r in win])
        ex.append(("node hardware, ESP-B software", len(hw), sd, sdw, b))

    L = []
    w = L.append
    w("# Time synchronisation over 10BASE-T1S: software stamps, LAN8651 hardware stamps, a PI clock servo")
    w("")
    w("*Generated by `make_ptp_report.py` from the console logs in `%s`. Bench: ESP32-S3 + LAN8651 HAT (node, PLCA "
      "coordinator, SPI 20 MHz) ═T1S═ media converter ─100BASE-TX─ ESP32-S3 + W5500 (ESP-B). 2026-10-06.*" % src)
    w("")
    w("## 1. Measuring: two-way time transfer")
    w("")
    w("ESP-B asks, the node answers (UDP 5007): t1..t4, offset = ((t2 − t1) + (t3 − t4)) / 2. Precision is the "
      "scatter of the offset around its drift line; with no reference clock on the bench, accuracy is not measured.")
    w("")
    w("| stamps | exchanges | σ, all | σ, min-delay per 2 s | drift |")
    w("|---|---|---|---|---|")
    for name, n, sd, sdw, b in ex:
        w("| %s | %d | %.0f µs | %.0f µs | %+.1f ppm |" % (name, n, sd, sdw, b))
    w("")
    w("The node's hardware stamps come from the LAN8651's 1588 wall clock (TSU, 40 ns per 25 MHz tick). Two settings "
      "had to be found: OA_CONFIG0.FTSE/FTSS take effect only when written with SYNC at init, and the PHY's packet "
      "matcher, which triggers the stamp at the SFD on the wire, is off out of reset (STATUS1.TTSCMA: capture "
      "requested, not triggered). The drift differs between the rows because the hardware clock runs off the HAT's "
      "crystal, the software one off the ESP32's.")
    w("")
    w("## 2. Steering: a PI servo on the LAN8651 clock (`ptp lock`)")
    w("")
    w("The node asks ESP-B 16 times a second (its request and the reply stamped in hardware), keeps the min-delay "
      "exchange per second, steps once (TA register below 1 s, else TSL/TN) and then steers the TSU frequency "
      "(TI + TISUBN, 2⁻²⁴ ns steps). Offset after the first 20 s:")
    w("")
    w("![P1](p1_offset_steps.png)")
    w("")
    w("| run | master side | kp / ki | σ | max | mean | one-way delay p50 | frequency held |")
    w("|---|---|---|---|---|---|---|---|")
    for name, kp, ki, rows in sorted(locks, key=lambda x: (x[0].split("_")[0], -x[1])):
        s = stats(rows)
        w("| `%s` | %s | %g / %g | **%.1f µs** | %.0f µs | %+.1f µs | %.0f µs | %+.1f ± %.1f ppm |"
          % (name, label(name), kp, ki, s["sd"], s["max"], s["mean"], s["delay"], s["freq"], s["freq_sd"]))
    w("")
    w("![P2](p2_gains.png)")
    w("")
    w("**Reading it.** The servo locks within 2 s and holds about −21 ppm, the HAT crystal against the ESP32's. "
      "What limits the result is the master's side, step by step: (1) ESP-B's W5500 was polled every 1 ms, so its "
      "receive time wandered by up to 1 ms -- the Elite wires the W5500's INTn to IO14, and interrupt-driven "
      "receive halves the scatter; (2) ESP-B stamped t2 in the UDP socket task -- a tap in the Ethernet driver's "
      "receive path, before lwIP, takes another quarter off; (3) a t3 taken after the send returned (a software "
      "two-step) scattered more than one taken just before it and was reverted. A request spacing of whole "
      "milliseconds kept every request at the same poll phase, so the spacing is jittered by 0–1 ms. ptp4l's gains "
      "(0.7 / 0.3) turn this bench's measurement noise into ±30–40 ppm frequency swings; 0.2 / 0.02 is the default.")
    w("")
    w("## 3. Limits")
    w("")
    w("- One side only has hardware stamps; the master is software (ESP-B) and the path crosses a store-and-forward "
      "converter whose queueing is not symmetric. Two LAN8651 nodes (hardware at both ends, no converter) are the "
      "next measurement; the servo already uses a master's hardware follow-up when it gets one.")
    w("- No reference: offsets are precision, not accuracy. A PPS on DIOA0 from each node and an oscilloscope "
      "would give accuracy directly (the firmware has `ptp pps`; Rev C ties DIOA to ground).")
    w("- Timestamps on every received frame cost 6 % of receive throughput (8.75 → 8.20 Mbit/s at 1472 B), "
      "so they are a build option (`-DLAN865X_FRAME_TIMESTAMPS`).")
    open(os.path.join(out, "REPORT.md"), "w").write("\n".join(L) + "\n")
    write_pdf(out, "\n".join(L))
    print("wrote", out, len(locks), "servo runs,", len(ex), "exchange runs")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
