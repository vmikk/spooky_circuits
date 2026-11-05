# Spooky circuits

A collection of DIY Halloween decoration projects (powered mostly by Raspberry Pi Pico).

| Project | Board | What it does |
|---|---|---|
| [👻 Ghost (2026)](#-ghost-2026) | Waveshare RP2040-Zero | NeoPixel ghost with a PIR-triggered jump-scare |
| [🐈‍⬛ Halloween cats (2025)](#-halloween-cats-2025) | Raspberry Pi Pico | Three cat silhouettes with glowing LED eyes |
| [🎃 Pumpkin Jack (2024)](#-pumpkin-jack-2024) | YD-RP2040 | Pumpkin with LED-matrix eyes and inner NeoPixel glow |

## Common setup

All projects run on [CircuitPython](https://circuitpython.org/) 10.x on an RP2040 board.

1. Flash the CircuitPython UF2 for your board (hold BOOTSEL while plugging in, drop the `.uf2` file on the `RPI-RP2` drive).
2. Copy the project's main script to the `CIRCUITPY` drive as **`code.py`**.
3. Copy the required libraries (from the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries), matching your CircuitPython version) to `CIRCUITPY/lib/`.

**Power:** the projects can run from any 5 V USB source (power bank, phone charger).
NeoPixel rings and MAX7219 matrices take 5 V from the board's `5V`/`VBUS` pin. Connect all grounds together.
The brightness settings in each script also limit how much current the LEDs draw.

---

## 👻 Ghost (2026)

