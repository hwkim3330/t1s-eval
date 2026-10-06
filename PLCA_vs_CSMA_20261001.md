# PLCA vs CSMA/CD on one 10BASE-T1S segment — 2026-10-01

> **Corrections (2026-10-06):** read this through [ERRATA.md](ERRATA.md) — the "25 MHz" SPI clock is 26.67 MHz actual, and board-measured rates read ≈0.5 % high.

Same bench, same test, only the access method changed:

```
PC enp4s0 ─RJ45─ TSN Lab 10Base-T1S Converter (USB 1-12) ═T1S═ TSN Lab LAN8651 HAT ─SPI 25 MHz─ ESP32-S3 (t1s_node)
```

PLCA run: converter dial ID 0 / count 2, DIP 1 ON; HAT `plca 1 2` (TO 32 bit times = 3.2 µs, burst 0).
CSMA run: converter DIP 1 OFF; HAT `csma`. Traffic is 1000 B UDP; HAT → PC frames captured on the PC
with kernel timestamps (SO_TIMESTAMPNS) and sequence numbers.

| phase | metric | **PLCA** | CSMA/CD |
|---|---|---|---|
| idle | ping avg / p99 | 0.98 / 1.37 ms | 0.97 / 1.46 ms |
| PC floods 9 Mbit/s, pings behind it | ping loss | **0.4 %** | 83 % |
| HAT floods, PC sends 1 Mbit/s | HAT → PC loss | **0 %** | 11 % |
| | HAT frame gap max | **2.4 ms** | 4.7 ms |
| | PC → HAT delivered | 0.06 of 1.0 Mbit/s | 0.12 of 1.0 Mbit/s |
| both flood | HAT → PC loss | **0 %** | 27 % |
| | longest HAT stall | 94 ms | **3,690 ms** |
| | split PC / HAT | 1.66 / 7.68 Mbit/s | 6.6 / 3.2 Mbit/s |
| HAT alone | loss · gap p99 | **0 % · 1.35 ms** | 0.44 % · 2.11 ms |

**Reading.** PLCA removes collisions: the PLCA-capable node (LAN8651, MAC and PHY in one chip) lost
nothing in any phase, where CSMA lost up to 27 % and stalled one node for 3.7 s under contention.
What PLCA does not fix here is the converter's own path: its stream is starved in both modes —
the vendor's manual lists exactly this (issue 4.3, bidirectional traffic through the converter, a
LAN8670 limitation not fixable in software).

PLCA cycle computed from the HAT's registers: idle cycle ≈ 8.4 µs (beacon + 2 × 3.2 µs), worst
wait behind one 1518 B frame ≈ 1.24 ms. Per-run reports: `t1s_plca_*.md` in this folder.
