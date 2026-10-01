# What the bench says the next T1S HAT (Rev C) must do

Every item here comes from a measurement or a failure on the bench (2026-09-30 … 10-01),
with the evidence next to it. The board this feeds is `elite-t1s-hat` (LAN8651 on an ESP32-S3
T-ETH-Elite); the reference that was measured is TSN Lab's LAN8651 HAT on the same ESP32
running the same firmware (`t1s_node`), through TSN Lab's 10Base-T1S Converter.

## 1. Keep the MAC-PHY. Do not build PHY + external MAC.

| evidence | |
|---|---|
| LAN8651 (MAC + PHY + PLCA in one chip) node | **0 % loss in every PLCA phase**, including both ends flooding ([REPORT](REPORT.md), PLCA vs CSMA) |
| converter = LAN8670 PHY behind a LAN9355 switch MAC | its own stream **93 % lost** while the other node floods; 1.7 vs 7.7 Mbit/s split |
| vendor manual, issue 4.3 | "bidirectional traffic through the converter … LAN8670 issue, not fixable in software" |

**Rule:** the T1S node keeps a PLCA-aware MAC on the same chip as the PHY (LAN8650/8651 class).
No "RMII PHY + generic MAC / switch" variant, even if it saves a part.

## 2. Design the SPI link for 25 MHz, because it *is* the throughput

| HAT SPI clock | PC → node, no loss | node → PC | RTT 64 B |
|---|---|---|---|
| 12 MHz | 6.0 Mbit/s | 6.3 | 1.01 ms |
| 20 MHz | 8.0 | 8.4 | 0.92 ms |
| **25 MHz** | **9.0** | **9.5** | **0.85 ms** (p99 0.99) |

Every frame crosses the OPEN Alliance TC6 SPI link, so below 25 MHz the bus is never full.
The TSN Lab HAT ran clean at 25 MHz **through a 2×20 stacking riser** — so the riser path is
not the limit, but the board must not be either.

**Rules:**
- SCLK/MOSI/MISO/CS short, on one layer over unbroken ground (Rev B already does this — keep it).
- Keep the firmware's boot check (raw DEVID read, auto MOSI/MISO swap) and make **25 MHz the
  default** once a Rev C board passes the full test at it.
- Acceptance: the full test at 25 MHz must reach **≥ 9 Mbit/s each way, < 1 % loss**.

## 3. Node ID and node count settable without a console

TSN Lab: a 4-bit DIP on an FXL6408 I²C expander sets the PLCA node ID (count fixed at 8 in their
driver); their converter uses two rotary switches (ID, count) and a DIP for PLCA/CSMA.
Ours: console + NVS only. On the bench that was fine; in a vehicle harness nobody has a console.

**Rule:** a 4-bit ID selector (DIP or straps) readable by the ESP32, plus a "PLCA on/off"
position; firmware reads it at boot, console/NVS can override. Count: default 8 (TSN Lab's
choice — 8 free slots cost ~26 µs per idle cycle, nothing at load).

## 4. Termination switchable, not populate-time

| evidence | |
|---|---|
| one end's termination OFF | the follower **lost the beacons** and reset itself every few seconds |
| both OFF (≈1 m bench cable) | still passed — short cable, not something to rely on |
| converter | termination on DIP 2/3 (N/P separately) |

Rev B ships R1/R2 unpopulated (END/DROP variants at order time).
**Rule:** a 2-pole switch or jumper for 100 Ω termination, so a node moved from the end of the
bus to the middle is a flick, not a rework. Keep the BIN layout (CMC → AC coupling → term → ESD → MDI).

## 5. Show PLCA state on the board

The converter's OLED/LEDs (mode, PLCA active, ERR codes 2…6) made diagnosis fast; our HAT's
DIOA LEDs are not mapped yet (firmware TODO), and the only way to know "beacons seen" was a
register read over the console.

**Rule (firmware):** map DIOA0 = PLCA status (PLCA_STS.PST), DIOA1 = TX/RX activity via PADCTRL.
**Rule (status):** `status` prints PLCA_STS, collision/late counters and dropped frames.

## 6. Firmware: nothing may block the console

Found the hard way: with zenoh-pico in the main loop, a node with **no transmit opportunity**
(PLCA ID ≥ node count) blocked in a send and the console froze. Zenoh now runs in its own task.
Same class of problem: `blast` occupies the console for its duration, so `sink` cannot be read
during it (the PLCA demo resets before and reads after).

**Rule:** every network activity in its own task; the console task only parses and queues.

## 7. Keep the Pi-HAT pin compatibility

The TSN Lab HAT (SPI0 CE0 = pin 24, IRQ = GPIO23 pin 16, its I²C expander IRQ on GPIO24 pin 18)
ran unmodified on our firmware's pin map. That compatibility is what let us measure at all
before Rev B boards exist. **Rule:** Rev C keeps SPI0/CE0/IRQ on the same header pins.

## 8. A sniffer mode

The converter's sniffer mode (ID ≥ 1, count 0: receive-only, forwards everything to the RJ45)
is the right tool for charting PLCA on the wire. Our HAT already has a W5500 ↔ T1S bridge mode;
**add a receive-only promiscuous variant** so any HAT can be the bus analyser.

## 9. Carried over from the Rev B reviews

- CCOMP: land for a metal-film part, or a dual MLCC/film footprint (Rev B: X7R, documented deviation).
- Real 1 mm test pads for CS_N, SCLK, MOSI, MISO, IRQ_N with GND beside them.
- Move the VDDA dogleg (U1 pin 29) out of the choke outline.
- Measure the stack height with the riser actually used (the TSN Lab HAT stack cleared the
  Elite's RJ45; confirm with Rev B's own socket).

## Acceptance tests for Rev C (the console already runs them)

| test | pass |
|---|---|
| full test, SPI 25 MHz | RTT 64 B avg ≤ 1.0 ms, p99 ≤ 1.5 ms; PC → node ≥ 9 Mbit/s < 1 % loss; node → PC ≥ 9 Mbit/s; 60 s 0 loss |
| PLCA demo | node-side loss 0 % in every phase; longest stall ≤ 100 ms with both flooding |
| Zenoh | session up over T1S; node-measured RTT reported; 20 Hz signal steady |
