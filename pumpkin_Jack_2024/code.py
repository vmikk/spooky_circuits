import board
import busio
import digitalio
import neopixel
import time
import random
from adafruit_max7219 import matrices
from rainbowio import colorwheel
import asyncio

class EyeAnimator:
    def __init__(self):
        self.blink_countdown = 100
        self.gaze_countdown = 75
        self.gaze_frames = 50
        self.eye_x, self.eye_y = 3, 3
        self.new_x, self.new_y = 3, 3
        self.dx, self.dy = 0, 0
        self.blink_counter = 0
        self.is_evil = EYE_MODE == "evil"

    async def animate(self):
        while True:
            display_left.fill(0)
            display_right.fill(0)
            
            image_index = BLINK_INDEX[self.blink_countdown] if self.blink_countdown < len(BLINK_INDEX) else 0
            
            if self.is_evil:
                draw_eye(display_left, EVIL_EYE_LEFT_IMG[image_index])
                draw_eye(display_right, EVIL_EYE_RIGHT_IMG[image_index])
            else:
                draw_eye(display_left, NICE_EYE_IMG[image_index])
                draw_eye(display_right, NICE_EYE_IMG[image_index])
            
            self.blink_countdown -= 1
            if self.blink_countdown == 0:
                self.blink_countdown = random.randint(5, 180)
                self.blink_counter += 1
                if EYE_MODE == "round,evil" and self.blink_counter >= 5:
                    self.is_evil = not self.is_evil
                    self.blink_counter = 0
                    if self.is_evil:
                        self.eye_x = self.eye_y = self.new_x = self.new_y = 4
                        self.dx = self.dy = 0
            
            if self.gaze_countdown <= self.gaze_frames:
                pupil_x = self.new_x - (self.dx * self.gaze_countdown // self.gaze_frames)
                pupil_y = self.new_y - (self.dy * self.gaze_countdown // self.gaze_frames)
                if self.is_evil:
                    draw_pupil(display_left, pupil_x + 1, pupil_y)
                    draw_pupil(display_right, pupil_x - 1, pupil_y)
                else:
                    draw_pupil(display_left, pupil_x, pupil_y)
                    draw_pupil(display_right, pupil_x, pupil_y)
                
                if self.gaze_countdown == 0:
                    self.eye_x, self.eye_y = self.new_x, self.new_y
                    if self.is_evil:
                        self.new_y = 4
                        self.new_x = random.randint(3, 5)
                    else:
                        while True:
                            self.new_x = random.randint(0, 6)
                            self.new_y = random.randint(0, 6)
                            self.dx, self.dy = self.new_x - 3, self.new_y - 3
                            if (self.dx * self.dx + self.dy * self.dy) < 10:
                                break
                    self.dx, self.dy = self.new_x - self.eye_x, self.new_y - self.eye_y
                    self.gaze_frames = random.randint(3, 15)
                    self.gaze_countdown = random.randint(self.gaze_frames, 120)
            else:
                if self.is_evil:
                    draw_pupil(display_left, self.eye_x + 1, self.eye_y)
                    draw_pupil(display_right, self.eye_x - 1, self.eye_y)
                else:
                    draw_pupil(display_left, self.eye_x, self.eye_y)
                    draw_pupil(display_right, self.eye_x, self.eye_y)
            
            self.gaze_countdown -= 1
            
            display_left.show()
            display_right.show()
            
            await asyncio.sleep(0.02)  # ~50 FPS

# Initialize SPI bus and MAX7219 devices
spi = busio.SPI(clock=board.GP2, MOSI=board.GP3)
cs_left = digitalio.DigitalInOut(board.GP5)
cs_right = digitalio.DigitalInOut(board.GP6)
display_left = matrices.Matrix8x8(spi, cs_left)
display_right = matrices.Matrix8x8(spi, cs_right)

# Set up NeoPixel rings
pixel_pin_1 = board.GP28
pixel_pin_2 = board.GP29
num_pixels = 12
brightness = 0.7

# Create the NeoPixel objects
pixels_1 = neopixel.NeoPixel(pixel_pin_1, num_pixels, brightness=brightness, auto_write=False)
pixels_2 = neopixel.NeoPixel(pixel_pin_2, num_pixels, brightness=brightness, auto_write=False)

# Constants for eye display
EYE_MODE = "round"  # Options: "round", "evil", or "round,evil"
LED_ON = 1
LED_OFF = 0

# Disable built-in NeoPixel (YD-RP2040)
builtin_neopixel = neopixel.NeoPixel(board.GP23, 1, brightness=0.01, auto_write=False)
builtin_neopixel[0] = (0, 0, 0)
builtin_neopixel.show()

# Eye images and blink index
NICE_EYE_IMG = (
    (0x3C, 0x7E, 0xFF, 0xFF, 0xFF, 0xFF, 0x7E, 0x3C),
    (0x00, 0x7E, 0xFF, 0xFF, 0xFF, 0xFF, 0x7E, 0x3C),
    (0x00, 0x00, 0x3C, 0xFF, 0xFF, 0xFF, 0x3C, 0x00),
    (0x00, 0x00, 0x00, 0x3C, 0xFF, 0x7E, 0x18, 0x00),
    (0x00, 0x00, 0x00, 0x00, 0x81, 0x7E, 0x00, 0x00),
)

EVIL_EYE_LEFT_IMG = (
    (0x70, 0xF8, 0xFC, 0xFE, 0xFF, 0xFF, 0xFF, 0x7E),
    (0x00, 0xF8, 0xFC, 0xFE, 0xFF, 0xFF, 0xFF, 0x00),
    (0x00, 0x00, 0xFC, 0xFE, 0xFF, 0xFF, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0xFE, 0xFF, 0x00, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0x00, 0xFE, 0x00, 0x00, 0x00),
)

EVIL_EYE_RIGHT_IMG = (
    (0x7E, 0xFF, 0xFF, 0xFF, 0xFE, 0xFC, 0xF8, 0x70),
    (0x00, 0xFF, 0xFF, 0xFF, 0xFE, 0xFC, 0xF8, 0x00),
    (0x00, 0x00, 0xFF, 0xFF, 0xFE, 0xFC, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0xFF, 0xFE, 0x00, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0xFE, 0x00, 0x00, 0x00, 0x00),
)

BLINK_INDEX = (1, 2, 3, 4, 3, 2, 1)

def draw_eye(display, image):
    for y, row in enumerate(image):
        for x in range(8):
            if row & (1 << (7 - x)):
                display.pixel(x, y, LED_ON)

def draw_pupil(display, x, y):
    for i in range(2):
        for j in range(2):
            display.pixel(x + i, y + j, LED_OFF)

# Async functions for NeoPixel animations
async def rainbow_cycle(wait):
    while True:
        for j in range(255):
            color = colorwheel(j)
            for i in range(num_pixels):
                pixels_1[i] = color
            pixels_1.show()
            await asyncio.sleep(wait)

async def breathing_green(wait):
    min_brightness = 0.2
    max_brightness = 1.0
    step = 0.02
    green_color = (0, 255, 0)

    while True:
        for b in range(int(min_brightness * 100), int(max_brightness * 100), int(step * 100)):
            brightness = b / 100
            color = tuple(int(c * brightness) for c in green_color)
            for i in range(num_pixels):
                pixels_2[i] = color
            pixels_2.show()
            await asyncio.sleep(wait)

        for b in range(int(max_brightness * 100), int(min_brightness * 100), -int(step * 100)):
            brightness = b / 100
            color = tuple(int(c * brightness) for c in green_color)
            for i in range(num_pixels):
                pixels_2[i] = color
            pixels_2.show()
            await asyncio.sleep(wait)

async def main():
    eye_animator = EyeAnimator()
    rainbow_task = asyncio.create_task(rainbow_cycle(0.9))
    breathing_task = asyncio.create_task(breathing_green(0.02))
    eyes_task = asyncio.create_task(eye_animator.animate())
    
    await asyncio.gather(rainbow_task, breathing_task, eyes_task)

# Run the main async function
asyncio.run(main())
