# T1S evaluation — reports and design input

Measured results from the 10BASE-T1S bench and what they mean for the next HAT.

```
PC enp4s0 ─RJ45─ TSN Lab 10Base-T1S Converter ═10BASE-T1S═ TSN Lab LAN8651 HAT ─SPI─ ESP32-S3 (t1s_node)
```

**2026-10-02: the PC is gone from the data path.** A second ESP32-S3 (W5500) took its place:

```
ESP32-S3 + LAN8651 HAT ═10BASE-T1S═ T1S/100BASE-TX converter ─RJ45─ ESP32-S3 + W5500
```

→ **[two-esp/REPORT.pdf](two-esp/REPORT.pdf)** ([markdown](two-esp/REPORT.md)): RTT by payload
both ways, a 1–10 Mbit/s sweep, payload-size sweep against the 10BASE-T1S frame model,
two-way contention, latency under load and a 60 s soak. 9.5 Mbit/s onto T1S and 9.1 off it
with no datagram lost, 64 B RTT 2.97 ms, 0 lost in 2 × 60 s at 8 Mbit/s. Raw data in
`two-esp/data/`, regenerate with `tools/make_duo_report.py two-esp/data/duo_suite_*.json two-esp`.

| file | what |
|---|---|
| **[two-esp/](two-esp/REPORT.md)** | the two-ESP run above: 7 figures, PDF |
| **[REPORT.md](REPORT.md)** | the combined report with figures (throughput by SPI clock, load sweep, latency, PLCA vs CSMA, gap histograms) |
| **[DESIGN_LESSONS.md](DESIGN_LESSONS.md)** | requirements for the next HAT (Rev C), each with its evidence, plus acceptance tests |
| [PLCA_vs_CSMA_20261001.md](PLCA_vs_CSMA_20261001.md) | the comparison table |
| `t1s_hat_*.md` | full tests: 1503 = SPI 12 MHz, 1508 = 20 MHz, 1511 = 25 MHz |
| `t1s_plca_*.md` | PLCA demos: **1538 = CSMA/CD run**, 1527 = PLCA run; 1525 superseded (its PC → HAT counter was read during the node's own blast and is invalid) |
| `data/` | raw results (`fulltests.json`, `demos.json`) |
| `tools/make_report.py` | regenerates `REPORT.md` and `figs/` from `data/` (and from the console's cache when present) |

Tools that produced the data live in the bench repo (`pc/t1s_console/hat_server.py`, the :8813
console: full test, PLCA demo, Zenoh view). Node firmware: `elite-t1s-hat/firmware/t1s_node`.
Converter analysis (log decode, SWD attempt, vendor manual findings): `t1s-converter-analysis`.
