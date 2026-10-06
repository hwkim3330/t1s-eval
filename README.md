# T1S evaluation — reports and design input

Measured results from the 10BASE-T1S bench and what they mean for the next HAT.

```
PC enp4s0 ─RJ45─ TSN Lab 10Base-T1S Converter ═10BASE-T1S═ TSN Lab LAN8651 HAT ─SPI─ ESP32-S3 (t1s_node)
```

**2026-10-06: in-spec rerun → [two-esp-20mhz/REPORT.pdf](two-esp-20mhz/REPORT.pdf)** ([markdown](two-esp-20mhz/REPORT.md)).
The runs below drove the LAN8651 at 26.67 MHz, above its 25 MHz SCLK limit (see [ERRATA.md](ERRATA.md));
the same suite at 20.00 MHz, the fastest in-spec clock on the ESP32-S3:

| | 20.00 MHz (in spec) | 26.67 MHz (10-02) |
|---|---|---|
| onto T1S, no loss | **9.00 Mbit/s** | 9.51 |
| off T1S, no loss | **8.04 Mbit/s** | 8.96 |
| UDP RTT 64 B, from ESP-B / from the node | **3.09 / 3.40 ms** | 2.97 / 2.66 |
| Zenoh pub/sub RTT | **4.9–5.2 ms** | 5.2–5.3 |
| 60 s soak at 8 Mbit/s, lost (each way) | **0 / 0** | 3 / 0 |

Quote these for anything built to the datasheet.

**2026-10-02: the PC is gone from the data path.** A second ESP32-S3 (W5500) took its place:

```
ESP32-S3 + LAN8651 HAT ═10BASE-T1S═ T1S/100BASE-TX converter ─RJ45─ ESP32-S3 + W5500
```

→ **[two-esp/REPORT.pdf](two-esp/REPORT.pdf)** ([markdown](two-esp/REPORT.md)), 10 pages, 9 figures:
RTT by payload both ways, a 1–10 Mbit/s sweep, payload-size sweep against the 10BASE-T1S frame
model, two-way contention, latency under load, a 60 s soak, and **Zenoh peer to peer over UDP
multicast with no router**. One way at a time 9.5 Mbit/s onto T1S and 9.0 off it with no
datagram lost; 64 B UDP RTT 2.97 ms; Zenoh pub/sub RTT 5.6–6.0 ms; offered above the bus
ceiling, the stream stalls for seconds — in the converter, not the node (§2.2.1). Raw data in `two-esp/data/`; regenerate with
`tools/make_duo_report.py two-esp/data/duo_suite_20261002_160735.json two-esp`.

**2026-10-06: two-board campaign** → **[campaign/REPORT.pdf](campaign/REPORT.pdf)** ([markdown](campaign/REPORT.md)).
Five repeats with both boards rebooted between them (mean ± 95 % CI), an SPI service-time model fitted on
three clocks and checked out of sample (worst error 0.2 %), CAN-like periodic messages idle and under
load, a 15 min / 91 k-probe tail (p99.99 4.85 ms), PLCA burst, coordinator-reboot outage (1.87 s), and a
table of what two boards cannot show. Note: the ESP32-S3 SPI runs 80 MHz / integer, so the "25 MHz" of the
earlier reports is **26.67 MHz**.

| file | what |
|---|---|
| **[ERRATA.md](ERRATA.md)** | corrections to the earlier reports (actual SPI clock, sink-rate bias, what is and is not proven) |
| **[campaign/](campaign/REPORT.md)** | the two-board campaign: repeats, SPI model check, periodic, tail, recovery |
| **[two-esp-20mhz/](two-esp-20mhz/REPORT.md)** | the same suite at the in-spec 20 MHz SPI clock (2026-10-06): 9 figures, PDF |
| **[two-esp/](two-esp/REPORT.md)** | the two-ESP run at 26.67 MHz (out of spec): 9 figures, PDF |
| **[REPORT.md](REPORT.md)** | the combined report with figures (throughput by SPI clock, load sweep, latency, PLCA vs CSMA, gap histograms) |
| **[DESIGN_LESSONS.md](DESIGN_LESSONS.md)** | requirements for the next HAT (Rev C), each with its evidence, plus acceptance tests |
| [PLCA_vs_CSMA_20261001.md](PLCA_vs_CSMA_20261001.md) | the comparison table |
| `t1s_hat_*.md` | full tests: 1503 = SPI 12 MHz asked (11.43 actual), 1508 = 20 MHz, 1511 = 25 MHz asked (26.67 actual) |
| `t1s_plca_*.md` | PLCA demos: **1538 = CSMA/CD run**, 1527 = PLCA run; 1525 superseded (its PC → HAT counter was read during the node's own blast and is invalid) |
| `data/` | raw results (`fulltests.json`, `demos.json`) |
| `tools/make_report.py` | regenerates `REPORT.md` and `figs/` from `data/` (and from the console's cache when present) |

Tools that produced the data live in the bench repo (`pc/t1s_console/hat_server.py`, the :8813
console: full test, PLCA demo, Zenoh view). Node firmware: `elite-t1s-hat/firmware/t1s_node`.
Converter analysis (log decode, SWD attempt, vendor manual findings): `t1s-converter-analysis`.
