# The MIT License (MIT)

# Copyright (c) 2021-2022 Krux contributors

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
import sys
import os
from unittest import mock
import pygame as pg
import cv2
from kruxsim import events
from kruxsim.mocks.board import BOARD_CONFIG

COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)

WIDTH = BOARD_CONFIG["lcd"]["width"]
HEIGHT = BOARD_CONFIG["lcd"]["height"]

screen = None
portrait = True
landscape = False


def rgb565torgb888(color):
    """convert from gggbbbbbrrrrrggg to tuple"""
    MASK5 = 0b11111
    MASK3 = 0b111

    red = ((color >> 3) & MASK5)
    red *= 255
    red //= 31
    green = color >> 13
    green += (color & MASK3) << 3
    green *= 255
    green //= 63
    blue = ((color >> 8) & MASK5)
    blue *=255
    blue //= 31
    return (red, green, blue)

def clear(color):
    def run():
        if screen:
            screen.fill(color)
    color = rgb565torgb888(color)
    pg.event.post(pg.event.Event(events.LCD_CLEAR_EVENT, {"f": run}))


def init(*args, **kwargs):
    pass


def register(addr, val):
    pass


def display(img, oft=None, roi=None):
    def run():
        frame = img.get_frame()
        frame = cv2.resize(
            frame,
            (screen.get_width(), screen.get_height()),
            interpolation=cv2.INTER_AREA,
        )
        frame = frame.swapaxes(0, 1)
        pg.surfarray.blit_array(screen, frame)

    pg.event.post(pg.event.Event(events.LCD_DISPLAY_EVENT, {"f": run}))


def rotation(r):
    global screen
    global portrait
    global landscape

    def run():
        global screen
        global portrait
        global landscape
        if not screen:
            portrait = True
            screen = pg.Surface((HEIGHT, WIDTH)).convert()
        if r == 2:
            landscape = True
        else:
            landscape = False

    pg.event.post(pg.event.Event(events.LCD_ROTATION_EVENT, {"f": run}))


def width():
    return HEIGHT if portrait else WIDTH


def height():
    return WIDTH if portrait else HEIGHT


def draw_string(x, y, s, color, bgcolor=COLOR_BLACK):
    def run():
        from kruxsim import devices
        text, _ = devices.load_font(BOARD_CONFIG["type"]).render(s, color, bgcolor)
        if landscape:
            text = pg.transform.rotate(text, 90)
            screen.blit(
                text,
                (
                    height() - text.get_width() - y
                    if BOARD_CONFIG["krux"]["display"]["inverted_coordinates"]
                    else y,
                    x,
                ),
            )
        else:
            screen.blit(
                text,
                (
                    width() - text.get_width() - x
                    if BOARD_CONFIG["krux"]["display"]["inverted_coordinates"]
                    else x,
                    y,
                ),
            )
    color = rgb565torgb888(color)
    bgcolor = rgb565torgb888(bgcolor)
    pg.event.post(pg.event.Event(events.LCD_DRAW_STRING_EVENT, {"f": run}))


def draw_qr_code(offset_y, code_str, max_width, dark_color, light_color, background):
    def run():
        starting_size = 0
        while code_str[starting_size] != "\n":
            starting_size += 1
        scale = max_width // starting_size
        qr_width = starting_size * scale
        offset = (max_width - qr_width) // 2
        for og_y in range(starting_size):
            for i in range(scale):
                y = og_y * scale + i
                for og_x in range(starting_size):
                    for j in range(scale):
                        x = og_x * scale + j
                        og_yx_index = og_y * (starting_size + 1) + og_x
                        screen.set_at(
                            (offset + x, offset + offset_y + y),
                            dark_color
                            if code_str[og_yx_index] == "1"
                            else light_color,
                        )
    dark_color = rgb565torgb888(dark_color)
    light_color = rgb565torgb888(light_color)
    pg.event.post(pg.event.Event(events.LCD_DRAW_QR_CODE_EVENT, {"f": run}))


def fill_rectangle(x, y, w, h, color):
    def run():
        pg.draw.rect(
            screen,
            color,
            (
                width() - w - x
                if BOARD_CONFIG["krux"]["display"]["inverted_coordinates"]
                else x,
                y,
                w,
                h,
            ),
        )
    color = rgb565torgb888(color)
    pg.event.post(pg.event.Event(events.LCD_FILL_RECTANGLE_EVENT, {"f": run}))


if "lcd" not in sys.modules:
    sys.modules["lcd"] = mock.MagicMock(
        init=init,
        register=register,
        display=display,
        clear=clear,
        rotation=rotation,
        width=width,
        height=height,
        draw_string=draw_string,
        draw_qr_code=draw_qr_code,
        fill_rectangle=fill_rectangle,
        BLACK=COLOR_BLACK,
        WHITE=COLOR_WHITE,
    )
