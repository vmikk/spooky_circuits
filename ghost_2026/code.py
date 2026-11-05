# Halloween ghost - spooky eyes + glowing body + PIR "scare" mode
# CircuitPython 10.x, Waveshare RP2040-Zero
#
# Hardware:
#   GP15 -> two chained 8-LED rings (eyes): pixels 0-7 = eye A, 8-15 = eye B
#   GP6  -> one 12-LED ring (body)
#   GP0  <- PIR motion sensor output (HIGH = motion)
#
# Behaviour:
#   - Warm-up (PIR settling): the ghost slowly fades in from darkness
#   - Idle: pale cold-blue body breathes, a wisp drifts around it,
#     icy-white eyes look around and blink now and then
#   - Motion: jump-scare (eyes go black, then slam blood-red, body strobes),
#     then "alert" mode: red heartbeat eyes darting around, body flickering
#     sickly green/purple with occasional lightning
#   - No motion for a while: the ghost calms down smoothly to idle
#
# Libraries needed in /lib: neopixel.mpy, adafruit_ticks.mpy, asyncio/

import math
import random
import board
import asyncio
import digitalio
import neopixel
from adafruit_ticks import ticks_ms, ticks_diff

# -----------------------------------------------------------------
# CONFIG
EYES_PIN = board.GP15
EYES_PER_RING = 8           # two rings chained -> 16 pixels
BODY_PIN = board.GP6
BODY_COUNT = 12
PIR_PIN = board.GP0

PIXEL_ORDER = neopixel.GRB  # most WS2812 rings; use neopixel.RGB if colors look swapped
EYES_BRIGHTNESS = 0.5       # 0..1 global cap (also limits current draw)
BODY_BRIGHTNESS = 0.5

# Eye ring orientation (to make both eyes "look" the same direction).
# Offsets rotate the ring; mirror eye B if it is mounted flipped/clockwise-reversed
EYE_A_OFFSET = 0
EYE_B_OFFSET = 0
EYE_B_MIRRORED = False

PIR_WARMUP_S = 30.0         # PIR sensors give false triggers while settling
FEAR_RISE_S = 0.5           # how fast the ghost gets angry on motion
ALERT_HOLD_S = 8.0          # stay angry this long after the last motion
CALM_DOWN_S = 6.0           # then fade back to idle over this time
SCARE_REARM_FEAR = 0.3      # new jump-scare only if the ghost had calmed below this
SCARE_MS = 1800             # jump-scare burst duration

FPS_DELAY = 0.02            # ~50 fps animation loops

# Palette "Classic spectral" (r, g, b) 0..255
BODY_IDLE = (90, 200, 255)      # pale cold blue/cyan
BODY_GREEN = (70, 255, 20)      # sickly green
BODY_PURPLE = (140, 0, 255)     # ghastly purple
EYE_IDLE = (150, 190, 255)      # icy white
EYE_ALERT = (255, 0, 0)         # blood red
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

GAMMA = 2.2
# -----------------------------------------------------------------

# Gamma lookup table, built once (no per-frame ** operations)
GAMMA_T = bytes([int(((i / 255) ** GAMMA) * 255 + 0.5) for i in range(256)])
TWO_PI = 2 * math.pi


def clamp01(x):
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def smoothstep(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(a, b, t):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def put(pixels, i, c):
    """Write a float color (0..255) to a pixel with gamma correction."""
    r = int(c[0])
    g = int(c[1])
    b = int(c[2])
    pixels[i] = (GAMMA_T[0 if r < 0 else 255 if r > 255 else r],
                 GAMMA_T[0 if g < 0 else 255 if g > 255 else g],
                 GAMMA_T[0 if b < 0 else 255 if b > 255 else b])


def ring_dist(a, b, n):
    """Shortest distance between two positions on a ring of n pixels."""
    d = abs(a - b) % n
    return min(d, n - d)


def ring_step(pos, target, max_step, n):
    """Move pos toward target along the shortest way around the ring."""
    d = (target - pos) % n
    if d > n / 2:
        d -= n
    if abs(d) <= max_step:
        return target % n
    return (pos + (max_step if d > 0 else -max_step)) % n


def bump(x, center, width):
    """Triangle pulse: 1 at center, 0 at +/- width."""
    v = 1.0 - abs(x - center) / width
    return v if v > 0 else 0.0


def heartbeat(phase):
    """Double-thump 'lub-dub' shape for phase 0..1."""
    return max(bump(phase, 0.07, 0.07), 0.7 * bump(phase, 0.27, 0.07))


class Clock:
    """Frame timer: returns dt in seconds, immune to float time precision loss."""
    def __init__(self):
        self.last = ticks_ms()

    def tick(self):
        now = ticks_ms()
        dt = ticks_diff(now, self.last) / 1000
        self.last = now
        return now, (dt if dt < 0.2 else 0.2)


class Ghost:
    """Shared mood state, written by the PIR task, read by the animations."""
    def __init__(self):
        self.wake = 0.0          # 0..1 fade-in during warm-up
        self.fear = 0.0          # 0 = idle, 1 = full alert
        self.motion = False
        self.last_motion = None  # ticks_ms of last motion
        self.scare_start = None  # ticks_ms when jump-scare started

    def scare_ms(self, now):
        """Milliseconds into the jump-scare, or None if not scaring."""
        if self.scare_start is None:
            return None
        ms = ticks_diff(now, self.scare_start)
        return ms if ms < SCARE_MS else None


# ------------ Tasks ------------

async def pir_task(ghost, pir):
    print("Ghost warming up ({:.0f} s)...".format(PIR_WARMUP_S))
    start = ticks_ms()
    while True:
        el = ticks_diff(ticks_ms(), start) / 1000
        ghost.wake = clamp01(el / PIR_WARMUP_S)
        if el >= PIR_WARMUP_S:
            break
        await asyncio.sleep(0.05)
    print("Ghost awake - watching for trick-or-treaters")

    clock = Clock()
    while True:
        now, dt = clock.tick()
        motion = pir.value
        if motion and not ghost.motion:
            print("Motion detected!")
            if ghost.fear < SCARE_REARM_FEAR:
                print("  BOO! (jump-scare)")
                ghost.scare_start = now
                ghost.fear = 1.0
        elif ghost.motion and not motion:
            print("Motion stopped")
        ghost.motion = motion

        if motion:
            ghost.last_motion = now
            ghost.fear = clamp01(ghost.fear + dt / FEAR_RISE_S)
        elif ghost.last_motion is not None:
            if ticks_diff(now, ghost.last_motion) > ALERT_HOLD_S * 1000:
                ghost.fear = clamp01(ghost.fear - dt / CALM_DOWN_S)
                if ghost.fear == 0.0:
                    ghost.last_motion = None
                    print("Ghost calmed down")

        # forget old scare timestamps (keeps ticks_diff from wrapping)
        if ghost.scare_start is not None and ghost.scare_ms(now) is None:
            ghost.scare_start = None

        await asyncio.sleep(0.05)


def eye_pixel(eye, i):
    """Map logical eye position i (0..7) of eye 0/1 to a strip index."""
    n = EYES_PER_RING
    if eye == 0:
        return (i + EYE_A_OFFSET) % n
    if EYE_B_MIRRORED:
        return n + (-i + EYE_B_OFFSET) % n
    return n + (i + EYE_B_OFFSET) % n


async def eyes_task(ghost, pixels):
    n = EYES_PER_RING
    clock = Clock()
    pos = 0.0                      # pupil position on the ring
    target = 0.0
    next_look = 0.0                # seconds until a new look target
    beat = 0.0                     # heartbeat phase 0..1
    breath = 0.0                   # idle breathing phase 0..1
    next_blink = random.uniform(3.0, 8.0)
    blink_t = None                 # seconds into current blink
    blink_eyes = (True, True)      # which eyes blink (winks!)
    jitter = 1.0
    eye_map = [[eye_pixel(e, i) for i in range(n)] for e in (0, 1)]

    while True:
        now, dt = clock.tick()
        fear = smoothstep(ghost.fear)
        scare = ghost.scare_ms(now)

        if scare is not None:
            # Jump-scare: darkness... then glaring red eyes
            if scare < 300:
                pixels.fill(BLACK)
            else:
                c = scale(EYE_ALERT, 1.0 if (scare // 60) % 4 else 0.6)
                for i in range(2 * n):
                    put(pixels, i, c)
            pixels.show()
            await asyncio.sleep(FPS_DELAY)
            continue

        # --- where are the eyes looking? ---
        next_look -= dt
        if next_look <= 0:
            target = random.uniform(0, n)
            next_look = lerp(random.uniform(1.5, 4.5), random.uniform(0.15, 0.6), fear)
        speed = lerp(2.5, 25.0, fear)  # pixels per second
        pos = ring_step(pos, target, speed * dt, n)

        # --- brightness envelope ---
        breath = (breath + dt / 6.0) % 1.0
        beat = (beat + dt * lerp(1.0, 1.9, fear)) % 1.0   # 60 -> 115 bpm
        idle_level = 0.60 + 0.12 * math.sin(TWO_PI * breath)
        alert_level = 0.50 + 0.50 * heartbeat(beat)
        level = lerp(idle_level, alert_level, fear)

        if fear > 0.05 and random.random() < 0.15:
            jitter = random.uniform(1.0 - 0.3 * fear, 1.0)
        else:
            jitter += (1.0 - jitter) * 0.3
        level *= jitter * ghost.wake * ghost.wake

        # --- blinking (only when calm; angry ghosts stare) ---
        lid = (1.0, 1.0)
        if blink_t is None:
            next_blink -= dt
            if next_blink <= 0 and fear < 0.5:
                blink_t = 0.0
                r = random.random()
                blink_eyes = (True, True) if r < 0.8 else ((True, False) if r < 0.9 else (False, True))
        if blink_t is not None:
            blink_t += dt
            if blink_t < 0.08:
                o = 1.0 - blink_t / 0.08
            elif blink_t < 0.16:
                o = 0.0
            elif blink_t < 0.30:
                o = (blink_t - 0.16) / 0.14
            else:
                o = 1.0
                blink_t = None
                next_blink = random.uniform(3.0, 8.0)
            lid = (o if blink_eyes[0] else 1.0, o if blink_eyes[1] else 1.0)

        # --- render ---
        color = lerp_color(EYE_IDLE, EYE_ALERT, fear)
        base = lerp(0.30, 0.60, fear)   # ring glow outside the pupil
        width = lerp(1.6, 2.2, fear)
        for e in (0, 1):
            k_eye = level * lid[e]
            m = eye_map[e]
            for i in range(n):
                glow = 1.0 - ring_dist(i, pos, n) / width
                if glow < 0:
                    glow = 0.0
                k = k_eye * (base + (1.0 - base) * glow)
                put(pixels, m[i], scale(color, k))
        pixels.show()
        await asyncio.sleep(FPS_DELAY)


def lightning_level(t):
    """Lightning flash pattern; t = seconds since flash start. None = done."""
    if t < 0.05:
        return 1.0
    if t < 0.13:
        return 0.15
    if t < 0.17:
        return 1.0
    if t < 0.45:
        return 1.0 - (t - 0.17) / 0.28
    return None


async def body_task(ghost, pixels):
    n = BODY_COUNT
    clock = Clock()
    breath = 0.0          # idle breathing phase 0..1
    wisp = 0.0            # rotating wisp position (pixels)
    swirl = 0.0           # alert color swirl phase 0..1
    shimmer = [1.0] * n
    flicker = [1.0] * n
    flicker_target = [1.0] * n
    flash_t = None

    while True:
        now, dt = clock.tick()
        fear = smoothstep(ghost.fear)
        scare = ghost.scare_ms(now)

        if scare is not None:
            # Jump-scare: dark, white flash, then 3 green/purple strobes
            if scare < 300:
                c = BLACK
            elif scare < 450:
                c = WHITE
            elif scare < 1500:
                s = (scare - 450) // 175  # 0..5
                c = BLACK if s % 2 else (BODY_GREEN if s % 4 == 0 else BODY_PURPLE)
            else:
                c = scale(BODY_GREEN, (scare - 1500) / 300)
            for i in range(n):
                put(pixels, i, c)
            pixels.show()
            flash_t = None
            await asyncio.sleep(FPS_DELAY)
            continue

        breath = (breath + dt * lerp(1 / 5.5, 1 / 1.4, fear)) % 1.0
        wisp = (wisp + dt * lerp(1.5, 6.0, fear)) % n
        swirl = (swirl + dt * 0.6) % 1.0
        b = 0.5 - 0.5 * math.cos(TWO_PI * breath)
        idle_level = 0.22 + 0.6 * b
        alert_level = 0.55 + 0.45 * b

        # lightning while angry
        if flash_t is None:
            if fear > 0.8 and random.random() < dt / 6.0:
                flash_t = 0.0
        else:
            flash_t += dt
        flash = lightning_level(flash_t) if flash_t is not None else None
        if flash is None:
            flash_t = None
            flash = 0.0

        wake = ghost.wake * ghost.wake
        for i in range(n):
            # idle: pale breathing glow + drifting wisp + shimmer
            shimmer[i] += (random.uniform(0.9, 1.1) - shimmer[i]) * 0.1
            w = 0.5 + 0.5 * math.cos(TWO_PI * (i - wisp) / n)
            idle = scale(BODY_IDLE, idle_level * (0.45 + 0.55 * w) * shimmer[i])

            if fear > 0.0:
                # alert: candle-like flicker, green/purple swirl
                if random.random() < 0.2:
                    flicker_target[i] = random.uniform(0.25, 1.0)
                flicker[i] += (flicker_target[i] - flicker[i]) * 0.35
                mix = 0.5 + 0.5 * math.sin(TWO_PI * (swirl + i / n))
                alert = scale(lerp_color(BODY_GREEN, BODY_PURPLE, mix),
                              alert_level * flicker[i])
                c = lerp_color(idle, alert, fear)
            else:
                c = idle

            if flash > 0.0:
                c = lerp_color(c, WHITE, flash)
            put(pixels, i, scale(c, wake))
        pixels.show()
        await asyncio.sleep(FPS_DELAY)


# ------------- Setup + main -------------

eyes = neopixel.NeoPixel(EYES_PIN, 2 * EYES_PER_RING, brightness=EYES_BRIGHTNESS,
                         auto_write=False, pixel_order=PIXEL_ORDER)
body = neopixel.NeoPixel(BODY_PIN, BODY_COUNT, brightness=BODY_BRIGHTNESS,
                         auto_write=False, pixel_order=PIXEL_ORDER)
pir = digitalio.DigitalInOut(PIR_PIN)
pir.direction = digitalio.Direction.INPUT
pir.pull = digitalio.Pull.DOWN


async def main():
    ghost = Ghost()
    await asyncio.gather(
        asyncio.create_task(pir_task(ghost, pir)),
        asyncio.create_task(eyes_task(ghost, eyes)),
        asyncio.create_task(body_task(ghost, body)),
    )


try:
    asyncio.run(main())
finally:
    # On reload / Ctrl-C: lights off, release pins
    for strip in (eyes, body):
        strip.fill(BLACK)
        strip.show()
        strip.deinit()
    pir.deinit()
