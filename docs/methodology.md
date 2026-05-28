# Methodology

## Overview

This repository contains the measurement automation code developed for the electrical characterisation of PET-stainless steel (PET-SS) composite e-textile, investigating its memristive and neuromorphic behaviour. The experimental work was carried out at the Department of LF - HF Impedance and DC Metrology, CSIR – National Physical Laboratory, New Delhi.

---

## Device Under Test (DUT)

The DUT is a knitted electronic textile fabricated from PET-SS composite yarn, formed by blending polyethylene terephthalate (PET) staple fibres and 316L stainless-steel (SS) microfibre sliver in an 80:20 mass ratio through standard ring-spinning. The finished yarn has a linear density of 19.68 Tex (Ne 30) with a twist of 590 turns per metre. For the knitted fabric, two single-yarn ends are used together at a doubled count of Ne 30/2.

The resistive switching mechanism in this material is thermally driven: localised Joule heating at SS-PET fibre junctions raises the surrounding PET above its glass transition temperature (~70–80 °C), triggering a partial amorphous-to-semi-crystalline phase transformation that permanently lowers resistance. This gives rise to non-volatile, write-once (WORM/ReWORM) memristive behaviour with multilevel conductance states.

---

## Instrumentation

| Component | Details |
|-----------|---------|
| Source-measure instrument | Keysight B2985B Electrometer / High Resistance Meter |
| Communication interface | GPIB (IEEE 488.1 / 488.2), primary address 23 |
| Controlling PC | Python-based automation via PyVISA |
| Physical connection | Two-probe configuration using single-core electrical wire contacts on the fabric surface |

The HI terminal of the B2985B sources the voltage stimulus; the LO terminal returns current. The triaxial cable guard is enabled to suppress leakage. All measurements are taken in the **course direction** of the knitted fabric unless stated otherwise.

---

## Software Environment

All instrument control and data acquisition is implemented in Python using the **PyVISA** library (v1.13+), which wraps the NI-VISA backend and communicates over GPIB. The stack used is:

- `pyvisa` — instrument communication (SCPI over GPIB)
- `numpy` — numerical array operations
- `pandas` — structured data logging and `.xlsx` export
- `matplotlib` — in-script plotting

Install dependencies with:

```bash
pip install pyvisa numpy pandas matplotlib openpyxl
```

> **Note:** NI-VISA drivers must be installed on the host machine, or PyVISA-Py can be used as a driver-free alternative. NI-VISA drivers are recommended.

---

## SCPI Command Reference

All scripts use standard SCPI commands over the PyVISA `write()` / `query()` interface. Key commands used across the codebase are listed below.

| Command | Function |
|---------|----------|
| `*RST` | Reset instrument to factory defaults |
| `*CLS` | Clear status registers and error queue |
| `*IDN?` | Query instrument identification string |
| `:SOUR:VOLT <value>` | Set output voltage level |
| `:SOUR:VOLT:MODE LIST` | Switch source to list (waveform) mode |
| `:SOUR:LIST:VOLT <csv>` | Load comma-separated voltage waveform into instrument memory |
| `:SENS:CURR:RANG:AUTO ON` | Enable auto-range on current measurement |
| `:SENS:CURR:NPLC <value>` | Set integration time in power-line cycles |
| `:TRIG:SOUR TIM` | Use internal timer as trigger source |
| `:TRIG:TIM <value>` | Set trigger interval (seconds) |
| `:TRIG:COUN <n>` | Set number of trigger events |
| `:TRAC:POIN <n>` | Configure trace buffer size |
| `:TRAC:FEED:CONT NEXT` | Arm trace buffer for next acquisition |
| `:TRAC:DATA?` | Retrieve all buffered data |
| `:MEAS:CURR?` | Trigger and return a single current reading |
| `:OUTP ON / OFF` | Enable or disable voltage output |
| `:SYST:ERR?` | Query the instrument error queue |

Every session begins with `*RST` and `*CLS`. After each `write()` call, `:SYST:ERR?` is queried to detect faults before the sequence continues.

---

## Experiments

### 1. Parametric Pulse Study

**Purpose:** Characterise how individual pulse parameters — ON time, OFF time, and amplitude — govern conductance evolution under sub-threshold stimulation (LTP-like behaviour).

**Pulse structure per train:**
```
[Baseline read at V_read] → [N × (V_pulse for t_ON, V_read for t_OFF)] → [Post-train read]
```

**Deterministic timing:** Rather than relying on PC-side sleep calls (which introduce tens-of-milliseconds jitter), the complete voltage waveform is pre-loaded into the B2985B's internal **List Trigger** buffer. The instrument executes the sequence autonomously at a fixed 20 ms tick, bypassing the GPIB bus and the host OS for the duration of the pulse train. Timing jitter is limited only by the instrument's internal crystal oscillator.

**Parameters studied:**

| Parameter | Values tested | Fixed values |
|-----------|---------------|--------------|
| Pulse ON time | 20 ms, 40 ms, 60 ms | V = 2.5 V, t_OFF = 100 ms |
| Pulse amplitude | 2.0 V, 2.5 V, 3.0 V | t_ON = 40 ms, t_OFF = 100 ms |
| Pulse OFF time | 40 ms, 100 ms, 400 ms, 600 ms, 1 s | V = 2.5 V, t_ON = 40 ms |


**Output:** `.xlsx` files with three sheets per run — `Raw_Trace`, `Summary`, and `Pulse_Timings` — plus in-script conductance vs. pulse number plots.

---

### 2. Retention Study

**Purpose:** Confirm that conductance states acquired through sub-threshold pulse trains are non-volatile (analogous to biological long-term potentiation) by monitoring the device under read-only bias after stimulation ceases.

**Protocol:**
- Apply 120 excitatory pulses (V = 3.0 V, t_ON = 40 ms, t_OFF = 100 ms)
- At pulse 120, cease stimulation and switch to read-only monitoring at 0.5 V
- Continuously log conductance over the post-stimulation window (~60 s)
- Compute the **Retention Ratio**: `RR = G_end / G_0`, where G_0 is conductance immediately after the last pulse

---

## Data Format

Each experimental run produces an `.xlsx` file with a timestamp-based filename, e.g.:

```
Neuromorphic_Keysight_HWTimed_2024-06-15_14-32-01_2.5V_0.04s.xlsx
```

| Sheet | Contents |
|-------|----------|
| `Raw_Trace` | Time (s), Voltage (V), Current (A), Resistance (Ω) for every hardware tick |
| `Summary` | Per-train Δt, R_initial, R_final, and percentage change |
| `Pulse_Timings` | Verified pulse rise/fall times and actual pulse widths from the raw trace |


---

## References

- S. P. Khanna et al., "ReWORM Memory Effect in PET-Metal Fiber-Based Electroconductive Yarn," *IEEE Trans. Electron Devices*, vol. 69, no. 8, 2022.
- S. P. Khanna et al., "Multilevel Non-Volatile Memristive Response in e-Textile," *IEEE Trans. Electron Devices*, vol. 70, no. 2, 2023.
- H. E. Grecco et al., "PyVISA: the Python instrumentation package," *J. Open Source Softw.*, vol. 8, no. 84, 2023.
- Keysight Technologies, B2985B Electrometer Data Sheet, 2022.
