# Halloween cats – 3 LED pairs with effects
# Works on CircuitPython 10+ (asyncio) & RP2040

import time
import math
import random
import board
import asyncio
import digitalio
import pwmio

# -----------------------------------------------------------------
# CONFIG: pins setup
# NB! Use PWM-capable pins for the smoothest fades
PINS = {
    "cat1": {"pin": board.GP6, "invert": False},
    "cat2": {"pin": board.GP10, "invert": False},
    "cat3": {"pin": board.GP14, "invert": False},
}

PWM_FREQUENCY = 800   # Hz (slightly lower to reduce switching losses)
# GAMMA correction for perceptually linear brightness
# - Typical range: 0.4–0.5 (inverse gamma) for LEDs, or 1.0 to disable
# - Lower values (0.3–0.4): dimmer low end, more "pop" at high brightness
# - Higher values (0.5–0.7): brighter low end, gentler fade curve
# - Value of 1.0: linear (no correction) - use if BRIGHTNESS_LIMIT doesn't work as expected
# - Note: Applied BEFORE BRIGHTNESS_LIMIT scales down the final output
# - Example: GAMMA=0.45, BRIGHTNESS_LIMIT=0.2, input=1.0 → 1.0^0.45 * 0.2 = 0.2 (20% max)
GAMMA = 1.0 / 2.2     # ~0.45 - good default for smooth LED fades

# Power/quality tuning
BRIGHTNESS_LIMIT = 0.05      # Global cap. Accepts 0..1 or 0..100 (%). Lower = dimmer.
DEBUG_BRIGHTNESS = False     # Set to True to print brightness values to console
# Normalize brightness limit so users can set either fraction (0..1) or percent (0..100)
_BRIGHTNESS_LIMIT = BRIGHTNESS_LIMIT
try:
    if _BRIGHTNESS_LIMIT > 1.0:
        # Treat values up to 100 as percent
        if _BRIGHTNESS_LIMIT <= 100.0:
            _BRIGHTNESS_LIMIT = _BRIGHTNESS_LIMIT / 100.0
        else:
            _BRIGHTNESS_LIMIT = 1.0
    if _BRIGHTNESS_LIMIT < 0.0:
        _BRIGHTNESS_LIMIT = 0.0
    if _BRIGHTNESS_LIMIT > 1.0:
        _BRIGHTNESS_LIMIT = 1.0
except Exception:
    # Fallback to safe value if something unexpected is assigned
    _BRIGHTNESS_LIMIT = 0.9

print(f"Brightness limit set to: {_BRIGHTNESS_LIMIT:.2f} ({int(_BRIGHTNESS_LIMIT * 100)}%)")

PWM_NOOP_DELTA = 256        # min duty change to write; higher => fewer PWM writes (lower MCU/switching power), but coarser steps

# Precompute gamma-corrected PWM duty lookup to avoid runtime pow()
# Brightness quantization steps for gamma LUT.
# Set to 256 for fine steps; 128 halves the number of runtime levels to save updates.
_LUT_SIZE = 256
_GAMMA_LUT = [
    int(((i / (_LUT_SIZE - 1)) ** GAMMA) * 65535 + 0.5) for i in range(_LUT_SIZE)
]

# Sine lookup table for effects (avoids math.sin per frame)
_SIN_N = 256
_SIN_LUT = [0.5 + 0.5 * math.sin(2 * math.pi * i / _SIN_N) for i in range(_SIN_N)]

# -----------------------------------------------------------------


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


class LightChannel:
    """Abstraction for one LED channel (PWM if available, else digital)."""
    def __init__(self, pin, invert=False, freq=PWM_FREQUENCY, gamma=GAMMA):
        self.invert = invert
        self.gamma = gamma
        self.brightness_limit = _BRIGHTNESS_LIMIT  # Store as instance variable
        self._last = 0.0
        self._last_duty = -1  # track last written PWM duty to skip tiny updates
        # Use global LUT when gamma matches; otherwise, build a per-instance LUT (init-time only)
        if abs(self.gamma - GAMMA) < 1e-6:
            self._lut = _GAMMA_LUT
        else:
            self._lut = [
                int(((i / (_LUT_SIZE - 1)) ** self.gamma) * 65535 + 0.5)
                for i in range(_LUT_SIZE)
            ]

        try:
            self.pwm = pwmio.PWMOut(pin, frequency=freq, duty_cycle=0)
            self.digital = None
            self.has_pwm = True
        except Exception:
            # Fallback to digital on/off if PWM not available
            self.pwm = None
            self.has_pwm = False
            self.digital = digitalio.DigitalInOut(pin)
            self.digital.direction = digitalio.Direction.OUTPUT
            self.digital.value = (not invert)

    def set(self, brightness: float) -> None:
        """Set brightness 0..1."""
        # Apply brightness cap (stored in instance)
        b = _clamp01(brightness) * self.brightness_limit
        b = _clamp01(b)
        if DEBUG_BRIGHTNESS:
            print(f"Set: in={brightness:.3f} * limit={self.brightness_limit:.3f} = {b:.3f}")
        if self.has_pwm:
            # Map brightness to LUT index and fetch precomputed gamma-corrected duty
            idx = int(b * (_LUT_SIZE - 1) + 0.5)
            if idx < 0:
                idx = 0
            elif idx >= _LUT_SIZE:
                idx = _LUT_SIZE - 1
            duty = self._lut[idx]
            if DEBUG_BRIGHTNESS:
                print(f"  idx={idx}, duty_raw={duty}, invert={self.invert}")
            # For inverted LEDs, invert the duty cycle AFTER gamma correction
            if self.invert:
                duty = 65535 - duty
                if DEBUG_BRIGHTNESS:
                    print(f"  duty_inverted={duty} ({duty/655.35:.1f}%)")
            # Skip very small duty changes to reduce flicker/CPU writes
            if self._last_duty >= 0 and abs(duty - self._last_duty) < PWM_NOOP_DELTA:
                self._last = b
                return
            self.pwm.duty_cycle = duty
            self._last_duty = duty
            self._last = b
        else:
            v = b >= 0.5
            if self.invert:
                v = not v
            self.digital.value = v
            self._last = b

    def off(self):
        self.set(0.0)

    def deinit(self):
        if self.pwm:
            self.pwm.deinit()
        if self.digital:
            self.digital.deinit()


class LEDUnit:
    """Single LED unit with override support (one toy = one pin)."""
    def __init__(self, channel: LightChannel):
        self.ch = channel
        self._override_until = 0.0  # epoch time until which overrides are active

    @property
    def overridden(self) -> bool:
        return time.monotonic() < self._override_until

    def safe_set(self, b: float) -> None:
        """Respect overrides: only write if not currently overridden."""
        if not self.overridden:
            self.ch.set(b)

    async def flash(self, sequence):
        """
        Override sequence: list of (brightness, duration_sec).
        Blocks other writers until finished.
        """
        for b, dur in sequence:
            self._override_until = time.monotonic() + dur + 0.02
            self.ch.set(b)
            await asyncio.sleep(dur)
        self._override_until = 0.0


# ------------ Effects (async tasks) ------------

async def eerie_breathe(unit: LEDUnit, base=0.03, peak=0.9, period=4.5, phase_offset=None, period_variation=0.08, jitter_interval=0.25):
    """Slow sinusoidal breathing with subtle jitter.

    Parameters
    - pair: LEDPair to animate.
    - base (0..1): minimum brightness. Lower = darker lows; higher = brighter idle.
    - peak (0..1): maximum brightness (>= base). Higher = brighter tops.
    - period (seconds): full breath cycle length. Larger = slower breathing.
    - phase_offset (seconds or None): initial phase shift; None randomizes per pair.
    - period_variation (0..0.3): per-instance ±fractional period tweak for desync.
    """
    t0 = time.monotonic()
    if phase_offset is None:
        phase_offset = random.uniform(0.0, period)
    # Fixed per-instance period scale to avoid perfect sync across pairs
    pv = max(0.0, min(0.3, period_variation))
    period_scale = 1.0 + random.uniform(-pv, pv)
    prev_b = base
    alpha = 0.25  # smoothing factor for brightness changes (0..1)
    # Phase accumulator for sine LUT
    phase = 0
    # Precompute step per tick based on target period; updated each loop from dt
    # Jitter update timer
    next_jitter_update = 0.0
    jitter = 1.0
    while True:
        if unit.overridden:
            await asyncio.sleep(0.01)
            continue
        t = time.monotonic() - t0
        # Update jitter occasionally to reduce RNG cost and provide stability
        if t >= next_jitter_update:
            # Reduce jitter at low brightness to avoid visible flicker
            # Jitter is sampled at a lower rate to save power
            jitter = 0.985 + 0.03 * random.random()
            next_jitter_update = t + max(0.1, jitter_interval)

        # Sinus from base to peak via LUT
        # Map time to phase index
        period_eff = period * period_scale
        frac = ((t + phase_offset) / period_eff) % 1.0
        idx = int(frac * _SIN_N) & (_SIN_N - 1)
        s = _SIN_LUT[idx]
        target = base + (peak - base) * s
        if target >= 0.08:
            target *= jitter
        # Exponential smoothing to avoid abrupt changes
        b = prev_b + alpha * (target - prev_b)
        prev_b = b
        unit.safe_set(_clamp01(b))
        # Slightly lower update rate to save power without visible stepping
        await asyncio.sleep(0.05)


async def random_blink(unit: LEDUnit, every=(2.5, 8.0)):
    """Occasional quick blink (both eyes).

    Parameters
    - pair: LEDPair to animate.
    - every (seconds range tuple): random interval between blinks.
      Smaller values = more frequent blinks; larger = rarer blinks.
    """
    while True:
        await asyncio.sleep(random.uniform(*every))
        # quick shut, quick open w/ slight overshoot
        seq = [
            (0.0, 0.5),    # old duration = 0.08
            (1.0, 0.1),    # old duration = 0.04
            (0.0, 0.4),    # old duration = 0.05
        ]
        await unit.flash(seq)


async def lightning(all_units, cooldown=(15.0, 45.0)):
    """Rare lightning flash that overrides all pairs briefly.

    Parameters
    - all_pairs: iterable of LEDPair to flash together.
    - cooldown (seconds range tuple): random time between lightning events.
      Smaller values = more frequent flashes; larger = rarer flashes.
    """
    while True:
        await asyncio.sleep(random.uniform(*cooldown))
        seq = [
            (1.0,  0.1),   # old duration = 0.05
            (0.35, 0.1),   # old duration = 0.08
            (1.0,  0.1),   # old duration = 0.04
            (0.0,  0.1),   # old duration = 0.12
            (0.4,  0.1),   # added
            (0.0,  0.1),   # added
        ]
        await asyncio.gather(*[u.flash(seq) for u in all_units])


# ------------- Setup + main -------------

def make_unit(pin, invert=True):
    """Create a single LED unit for a toy (one pin).

    Parameters
    - pin: board pin object (PWM-capable preferred).
    - invert (bool): set True if hardware wiring requires inverted logic.
    """
    return LEDUnit(LightChannel(pin, invert=invert))


async def main():
    # Build the three single-channel units
    unit1 = make_unit(PINS["cat1"]["pin"], PINS["cat1"]["invert"])
    unit2 = make_unit(PINS["cat2"]["pin"], PINS["cat2"]["invert"])
    unit3 = make_unit(PINS["cat3"]["pin"], PINS["cat3"]["invert"])

    # Start tasks
    tasks = [
        # cat 1
        asyncio.create_task(
            eerie_breathe(
                unit1,
                base=0.03,
                peak=0.95,
                period=4.7,             # slightly faster
                phase_offset=0.0,
                period_variation=0.05,  # mild
            )
        ),
        asyncio.create_task(random_blink(unit1, every=(5.0, 10.0))),

        # cat 2
        asyncio.create_task(
            eerie_breathe(
                unit2,
                base=0.03,
                peak=0.95,
                period=4.9,            # slightly slower
                phase_offset=1.2,      # offset ~ quarter cycle
                period_variation=0.05,
            )
        ),
        asyncio.create_task(random_blink(unit2, every=(7.0, 20.0))),

        # cat 3
        asyncio.create_task(
            eerie_breathe(
                unit3,
                base=0.03,
                peak=0.95,
                period=4.8,            # middle
                phase_offset=2.4,      # offset ~ half cycle
                period_variation=0.05,
            )
        ),
        asyncio.create_task(random_blink(unit3, every=(6.0, 15.0))),

        # Global lightning
        asyncio.create_task(lightning([unit1, unit2, unit3], cooldown=(30.0, 90.0))),
    ]

    # Keep running forever
    while True:
        await asyncio.sleep(60)


try:
    asyncio.run(main())
finally:
    # If reloaded, try to tidy up PWM/digital resources
    for k in ("cat1", "cat2", "cat3"):
        for side in ("left", "right"):
            try:
                pin = PINS[k][side]
            except Exception:
                pass

