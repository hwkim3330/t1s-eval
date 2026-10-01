# T1S evaluation — reports and design input

Measured results from the 10BASE-T1S bench and what they mean for the next HAT.

```
PC enp4s0 ─RJ45─ TSN Lab 10Base-T1S Converter ═10BASE-T1S═ TSN Lab LAN8651 HAT ─SPI─ ESP32-S3 (t1s_node)
```

| file | what |
|---|---|
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
