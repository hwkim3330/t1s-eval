"""PLCA vs CSMA/CD, repeated, from the console's access runs (campaign.access, access_*.json).

    python3 make_access_report.py OUT_DIR access_A.json [access_B.json ...]

Each run holds rounds of the same five phases (the 2026-10-01 PC comparison, with ESP-B in the
PC's place): idle round trip, the peer flooding 9 Mbit/s onto T1S while the node probes, the node
flooding while the peer sends 1 Mbit/s, both flooding, the node alone. Rounds of either method are
pooled across files; every number is a per-round value, reported as mean +- 95 % CI over rounds.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_campaign_report import C_OFF, C_ONTO, ci, ok, pct, plt, save  # noqa: E402
from make_duo_report import write_pdf  # noqa: E402

MODES = ("plca", "csma")
LABEL = {"plca": "PLCA", "csma": "CSMA/CD"}
COL = {"plca": C_ONTO, "csma": C_OFF}


def loss_pct(sk):
    e = (sk or {}).get("expected") or 0
    return 100.0 * (sk.get("seq_lost") or 0) / e if e else (100.0 if sk is not None else float("nan"))


def metrics(ph):
    """One round of one method -> flat dict of per-round values."""
    m = {}
    idle = ok(ph["idle_rtt"]["us"])
    m["idle_p50"] = pct(idle, 50) / 1000 if idle else float("nan")
    m["idle_loss"] = 100.0 * (len(ph["idle_rtt"]["us"]) - len(idle)) / max(1, len(ph["idle_rtt"]["us"]))
    pr = ph["peer_flood_probe"]
    m["probe_loss"] = 100.0 * (pr["summary"] or {}).get("lost", 0) / max(1, (pr["summary"] or {}).get("n", 1))
    prok = ok(pr["us"])
    m["probe_p50"] = pct(prok, 50) / 1000 if prok else float("nan")
    m["probe_p99"] = pct(prok, 99) / 1000 if prok else float("nan")
    m["flood_rate"] = ph["peer_flood_sink"].get("delivered", 0.0)
    m["flood_loss"] = loss_pct(ph["peer_flood_sink"])
    nf = ph["node_flood_peer1"]
    m["nf_node_rate"], m["nf_node_loss"] = nf["sink"].get("delivered", 0.0), loss_pct(nf["sink"])
    m["nf_peer_rate"], m["nf_peer_loss"] = nf["reverse"]["sink"].get("delivered", 0.0), loss_pct(nf["reverse"]["sink"])
    bf = ph["both_flood"]
    m["bf_node_rate"], m["bf_node_loss"] = bf["sink"].get("delivered", 0.0), loss_pct(bf["sink"])
    m["bf_node_gap"] = (bf["sink"].get("gap_max") or 0) / 1000
    m["bf_peer_rate"], m["bf_peer_loss"] = bf["reverse"]["sink"].get("delivered", 0.0), loss_pct(bf["reverse"]["sink"])
    al = ph["node_alone"]["sink"]
    m["alone_rate"], m["alone_loss"] = al.get("delivered", 0.0), loss_pct(al)
    m["alone_gap_p99"] = (al.get("gap_p99") or 0) / 1000
    return m


ROWS = [  # (key, phase, metric, unit, digits)
    ("idle_p50", "idle", "64 B round trip, median (from ESP-B)", "ms", 2),
    ("idle_loss", "idle", "probes lost", "%", 1),
    ("probe_loss", "peer floods 9 Mbit/s", "node's probes lost", "%", 1),
    ("probe_p50", "peer floods 9 Mbit/s", "node's probe round trip, median", "ms", 2),
    ("probe_p99", "peer floods 9 Mbit/s", "node's probe round trip, p99", "ms", 2),
    ("flood_rate", "peer floods 9 Mbit/s", "flood delivered to the node", "Mbit/s", 2),
    ("flood_loss", "peer floods 9 Mbit/s", "flood lost", "%", 1),
    ("nf_node_rate", "node floods, peer 1 Mbit/s", "node -> peer delivered", "Mbit/s", 2),
    ("nf_node_loss", "node floods, peer 1 Mbit/s", "node -> peer lost", "%", 2),
    ("nf_peer_rate", "node floods, peer 1 Mbit/s", "peer -> node delivered (of 1.0)", "Mbit/s", 2),
    ("nf_peer_loss", "node floods, peer 1 Mbit/s", "peer -> node lost", "%", 1),
    ("bf_node_rate", "both flood", "node -> peer delivered", "Mbit/s", 2),
    ("bf_node_loss", "both flood", "node -> peer lost", "%", 2),
    ("bf_node_gap", "both flood", "node's longest gap", "ms", 0),
    ("bf_peer_rate", "both flood", "peer -> node delivered", "Mbit/s", 2),
    ("bf_peer_loss", "both flood", "peer -> node lost", "%", 1),
    ("alone_rate", "node alone", "node -> peer delivered", "Mbit/s", 2),
    ("alone_loss", "node alone", "node -> peer lost", "%", 2),
    ("alone_gap_p99", "node alone", "arrival gap p99", "ms", 2),
]


def main(out, paths):
    os.makedirs(out, exist_ok=True)
    runs = [json.load(open(p)) for p in paths]
    per = {m: [] for m in MODES}          # mode -> list of per-round metric dicts
    src = {m: [] for m in MODES}
    spi = set()
    for p, R in zip(paths, runs):
        spi.add((R.get("setup") or {}).get("node", {}).get("spi_actual"))
        for rnd in R.get("rounds", []):
            for m in MODES:
                if m in rnd:
                    per[m].append(metrics(rnd[m]))
                    src[m].append("%s r%d" % (os.path.basename(p), rnd["i"]))
    have = [m for m in MODES if per[m]]
    stat = {m: {k: ci([r[k] for r in per[m]]) for k, *_ in ROWS} for m in have}

    # Fig 1: losses, the quantities PLCA is meant to change
    keys = [("probe_loss", "probes behind\na 9 Mbit/s flood"), ("nf_peer_loss", "peer's 1 Mbit/s\nwhile node floods"),
            ("bf_peer_loss", "peer, both\nflooding"), ("bf_node_loss", "node, both\nflooding"), ("alone_loss", "node\nalone")]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    w = 0.8 / max(1, len(have))
    for j, m in enumerate(have):
        xs = [i + (j - (len(have) - 1) / 2) * w for i in range(len(keys))]
        ms = [stat[m][k][0] for k, _ in keys]
        es = [0 if stat[m][k][1] != stat[m][k][1] else stat[m][k][1] for k, _ in keys]
        ax.bar(xs, ms, w * 0.92, yerr=es, capsize=2.5, color=COL[m], label="%s (n = %d rounds)" % (LABEL[m], len(per[m])))
        for x, r in zip(xs, [[rr[k] for rr in per[m]] for k, _ in keys]):
            ax.scatter([x] * len(r), r, s=6, color="black", zorder=3, linewidths=0)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([l for _, l in keys])
    ax.set_ylabel("lost (%)")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right", frameon=False)
    save(fig, out, "a1_loss")

    # Fig 2: who gets the wire when both flood
    fig, ax = plt.subplots(figsize=(6.4, 2.4))
    for j, m in enumerate(have):
        y = 1 - j
        nr, pr_ = stat[m]["bf_node_rate"][0], stat[m]["bf_peer_rate"][0]
        ax.barh(y, nr, 0.5, color=COL[m], label=None)
        ax.barh(y, pr_, 0.5, left=nr, color=COL[m], alpha=0.35)
        ax.text(nr / 2, y, "node %.2f" % nr, ha="center", va="center", color="white", fontsize=8)
        ax.text(nr + pr_ / 2, y, "peer %.2f" % pr_, ha="center", va="center", fontsize=8)
    ax.set_yticks([1 - j for j in range(len(have))])
    ax.set_yticklabels([LABEL[m] for m in have])
    ax.axvline(9.8, color="#777", lw=0.8, ls="--")
    ax.text(9.75, 1.45 if len(have) > 1 else 1.3, "10BASE-T1S ceiling ≈ 9.8", ha="right", fontsize=7, color="#777")
    ax.set_xlabel("delivered (Mbit/s), both ends flooding, mean over rounds")
    ax.set_xlim(0, 10.5)
    save(fig, out, "a2_share")

    L = []
    w_ = L.append
    w_("# PLCA vs CSMA/CD on one 10BASE-T1S segment, repeated")
    w_("")
    w_("*Generated by `make_access_report.py` from %s.*" % ", ".join("`%s`" % os.path.basename(p) for p in paths))
    w_("")
    w_("**Bench.** ESP-A: ESP32-S3 + LAN8651 MAC-PHY, PLCA coordinator (id 0 of 2), SPI %s MHz. Converter: LAN8670 + "
       "LAN9355, dial id 1. ESP-B: ESP32-S3 + W5500 on the converter's 100BASE-TX port, in the PC's place. 1000 B UDP. "
       "The same five phases as the 2026-10-01 PC comparison; every number below is per round, mean ± 95 %% CI "
       "(Student t) over rounds." % ", ".join(sorted("%.2f" % s for s in spi if s)) )
    w_("")
    if "csma" not in have:
        w_("> **CSMA/CD rounds pending.** The converter's PLCA is a DIP switch. With it on and only the node switched to "
           "`csma`, the converter does not fall back to CSMA/CD: it stops transmitting (every probe and every flood "
           "datagram from ESP-B lost, `access_20261006_113637`). The CSMA/CD rounds need DIP 1 off by hand; this report "
           "fills its second column when they exist.")
        w_("")
    w_("![Fig. A1](a1_loss.png)")
    w_("")
    w_("*Fig. A1 — Loss in each phase, per method; bars are means, whiskers 95 % CI, dots single rounds.*")
    w_("")
    w_("![Fig. A2](a2_share.png)")
    w_("")
    w_("*Fig. A2 — How the bus is shared when both ends flood: the node's delivered rate (solid) and the peer's (light).*")
    w_("")
    w_("| phase | metric | " + " | ".join("%s (n = %d)" % (LABEL[m], len(per[m])) for m in have) + " |")
    w_("|---|---|" + "---|" * len(have))
    for k, phase, name, unit, d in ROWS:
        cells = []
        for m in have:
            mean, h, n = stat[m][k]
            rng = [r[k] for r in per[m]]
            cells.append(("%.*f" % (d, mean)) + ("" if h != h else " ± %.*f" % (d, h)) + " " + unit +
                         " <small>(%s–%s)</small>" % ("%.*f" % (d, min(rng)), "%.*f" % (d, max(rng))))
        w_("| %s | %s | %s |" % (phase, name, " | ".join(cells)))
    w_("")
    if "plca" in have:
        s = stat["plca"]
        w_("**Reading it (PLCA).** The node never lost a datagram it sent: %.2f %% while it flooded alone, %.2f %% with "
           "the peer sending, %.2f %% with both flooding. Its small probes got onto a bus the peer was flooding at "
           "9 Mbit/s with %.1f %% loss (median %.2f ms), but their tail is in seconds (p99 %.2f s): the peer offers 9 Mbit/s and "
           "the converter carries %.2f onto T1S, so a queue builds on that path and the replies wait behind it — "
           "the median hides it. What PLCA does not protect is the converter's own stream: "
           "while the node floods, %.0f %% of the peer's 1 Mbit/s is lost, and with both flooding %.0f %% — the "
           "converter's two-way limitation the vendor lists (issue 4.3), seen in every round. When both flood, the "
           "node keeps %.2f Mbit/s but stalls for up to %.0f ms (mean of per-round maxima): it waits for transmit "
           "opportunities rather than losing frames." %
           (s["alone_loss"][0], s["nf_node_loss"][0], s["bf_node_loss"][0], s["probe_loss"][0], s["probe_p50"][0],
            s["probe_p99"][0] / 1000, s["flood_rate"][0],
            s["nf_peer_loss"][0], s["bf_peer_loss"][0], s["bf_node_rate"][0], s["bf_node_gap"][0]))
        w_("")
    if "csma" in have and "plca" in have:
        a, b = stat["plca"], stat["csma"]
        w_("**PLCA against CSMA/CD.** Probes behind the flood: %.1f %% vs %.1f %% lost. Node loss with both flooding: "
           "%.2f %% vs %.2f %%. Peer loss with both flooding: %.0f %% vs %.0f %%. Rates when both flood: node %.2f / %.2f, "
           "peer %.2f / %.2f Mbit/s (PLCA / CSMA)." %
           (a["probe_loss"][0], b["probe_loss"][0], a["bf_node_loss"][0], b["bf_node_loss"][0], a["bf_peer_loss"][0],
            b["bf_peer_loss"][0], a["bf_node_rate"][0], b["bf_node_rate"][0], a["bf_peer_rate"][0], b["bf_peer_rate"][0]))
        w_("")
    w_("**Limits.** Two nodes on the bus, one of them a converter whose transmit path is the known weak point; "
       "rounds of one method run back to back (the DIP is set by hand), so slow drift between the two blocks is not "
       "randomised out; one bus length (~1 m).")
    open(os.path.join(out, "REPORT.md"), "w").write("\n".join(L) + "\n")
    write_pdf(out, "\n".join(L))
    print("wrote", out, "methods:", ", ".join("%s %d rounds" % (m, len(per[m])) for m in have))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
