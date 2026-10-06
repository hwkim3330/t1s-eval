# Corrections (2026-10-06)

Found by the two-board campaign ([campaign/REPORT.md](campaign/REPORT.md)). Earlier reports are kept as they were
measured; read their numbers through these corrections.

| # | what earlier reports say | what is true | affects |
|---|---|---|---|
| 1 | SPI clock "12 / 20 / 25 MHz" | the ESP32-S3 SPI peripheral runs 80 MHz / integer: **11.43 / 20.00 / 26.67 MHz** (read from the board; 15 and 18 asked → 16, 22 → 20) | every clock-axis figure, table and fit: [REPORT.md](REPORT.md), `t1s_hat_*.md`, [DESIGN_LESSONS.md](DESIGN_LESSONS.md) §2, [two-esp/](two-esp/REPORT.md) |
| 2 | a service-time model fitted against the asked clock | fitted against the actual clock: **t0 = 842 µs per 1472 B datagram, k = 13 711 µs·MHz, c = 1.05** clock periods per transferred TC6 bit; out-of-sample error ≤ 0.2 % (one new clock, 16 MHz) | any model or c value derived from the 12/20/25 MHz points |
| 3 | rates measured by the board's `sink` | read **≈0.5 % high** (n datagrams counted over n−1 intervals, ms timer). Fixed in firmware cf0ba44: (datagrams after the first) / (first-to-last arrival, µs) | PC → HAT (HAT sink) in `t1s_hat_*.md` and [REPORT.md](REPORT.md); both directions in [two-esp/](two-esp/REPORT.md). HAT → PC was measured on the PC and is unaffected |
| 4 | "PC → HAT 8.99 Mbit/s, just under the 9 Mbit/s acceptance line" | with correction 3 the true value is ≈0.5 % *lower*; the line is met on the two-board bench instead: onto T1S at 9.0 offered, **9.005 ± 0.002 Mbit/s** delivered, 0 loss, 5 runs | [DESIGN_LESSONS.md](DESIGN_LESSONS.md) acceptance |
| 5 | "the converter's stream collapses" when both directions are busy | it collapses in **4 of 5** runs, from a total stall to none (0.00 / 1.28 / 1.09 / 3.00 / 1.73 Mbit/s of 3 offered); not deterministic | [two-esp/](two-esp/REPORT.md) §2.4 |
| 6 | round trips "stable" | from ESP-B: 3.083 ± 0.005 ms over 5 reboots. From the HAT: **2.71–3.38 ms between reboots** (phase of ESP-B's 1 ms W5500 poll against the HAT's probe timer) | [two-esp/](two-esp/REPORT.md) RTT tables |
| 7 | the overload stall "is in the converter" | supported, not proven: the LAN8651 shows no RX overflow (sticky STATUS0 = 0), no held RX chunks, and its driver count equals the sink's, so the receive side is ruled out; a control run without the converter (two LAN8651 nodes) has not been done | [two-esp/](two-esp/REPORT.md) §2.2.1 |

Still open (needs a second LAN8651 node or more equipment): more than two PLCA nodes, a run without the converter,
a 100BASE-TX-only baseline, cable length / stubs, TO_TIMER, collision counters, CPU load / power.

**2026-10-06, later:** 26.67 MHz is also **above the LAN8651's 25 MHz SCLK maximum** (DS60001734F,
Table 9-9). The firmware now never exceeds it (20.00 MHz on the ESP32-S3), and the two-board suite
was rerun there: [two-esp-20mhz/](two-esp-20mhz/REPORT.md) — onto T1S 9.00, off T1S 8.04 Mbit/s
lossless, 64 B RTT 3.09 / 3.40 ms, soak 0 / 0 lost. Numbers taken at "25 MHz" before this date are out of spec.

**2026-10-06, evening: the "Zenoh ~1000 msg/s receive cap" was misread.** It is set first by the
publisher: unbatched, every put is its own UDP datagram and the put call takes ~1 ms, so ~950–1150 puts/s.
Toward the HAT the subscriber received every one; toward the W5500 board it also dropped some (e.g.
993 of 1161/s at 32 B on 10-02). With zenoh-pico batching (`zenoh blast … batch`) 64 B puts take
~130–150 µs and reach ~5500–6000 msg/s; 1024 B payloads gain nothing. Reports that call it a receive cap
(two-esp/ §2.7) should read "publisher-side, unbatched".
