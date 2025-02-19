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
import hashlib
import gc
import sensor
import lcd
import board
from .qr import QRPartParser
from .wdt import wdt

OV2640_ID = 0x2642  # Lenses, vertical flip - Bit
OV5642_ID = 0x5642  # Lenses, horizontal flip - Bit
OV7740_ID = 0x7742  # No lenses, no Flip - M5sitckV, Amigo
GC0328_ID = 0x9D  # Dock


class Camera:
    """Camera is a singleton interface for interacting with the device's camera"""

    def __init__(self):
        self.cam_id = None
        self.antiglare_enabled = False
        self.initialize_sensor()

    def initialize_sensor(self, grayscale=False):
        """Initializes the camera"""
        sensor.reset(dual_buff=True)
        self.cam_id = sensor.get_id()
        if grayscale:
            sensor.set_pixformat(sensor.GRAYSCALE)
        else:
            sensor.set_pixformat(sensor.RGB565)
        if self.cam_id == OV5642_ID:
            # CIF mode will use central pixels and discard darker periphery
            sensor.set_framesize(sensor.CIF)
            sensor.set_hmirror(1)
        if self.cam_id == OV2640_ID:
            sensor.set_framesize(sensor.CIF)
            sensor.set_vflip(1)
        else:
            sensor.set_framesize(sensor.QVGA)
        if self.cam_id == OV7740_ID:
            self.config_ov_7740()
        sensor.skip_frames()

    def config_ov_7740(self):
        """Specialized config for OV7740 sensor"""
        # Allowed luminance thresholds:
        # luminance high threshold, default=0x78
        sensor.__write_reg(0x24, 0x70)  # pylint: disable=W0212
        # luminance low threshold, default=0x68
        sensor.__write_reg(0x25, 0x60)  # pylint: disable=W0212

        # Average-based sensing window definition
        # Ingnore periphery and measure luminance only on central area
        # Regions 1,2,3,4
        sensor.__write_reg(0x56, 0x0)  # pylint: disable=W0212
        # Regions 5,6,7,8
        sensor.__write_reg(0x57, 0b00111100)  # pylint: disable=W0212
        # Regions 9,10,11,12
        sensor.__write_reg(0x58, 0b00111100)  # pylint: disable=W0212
        # Regions 13,14,15,16
        sensor.__write_reg(0x59, 0x0)  # pylint: disable=W0212

    def has_antiglare(self):
        """Returns whether the camera has anti-glare functionality"""
        return self.cam_id == OV7740_ID

    def enable_antiglare(self):
        """Enables anti-glare mode"""
        if self.cam_id == OV7740_ID:
            # luminance high level, default=0x78
            sensor.__write_reg(0x24, 0x38)  # pylint: disable=W0212
            # luminance low level, default=0x68
            sensor.__write_reg(0x25, 0x20)  # pylint: disable=W0212
            # Disable frame integrtation (night mode)
            sensor.__write_reg(0x15, 0x00)  # pylint: disable=W0212
            sensor.skip_frames()
            self.antiglare_enabled = True

    def disable_antiglare(self):
        """Disables anti-glare mode"""
        if self.cam_id == OV7740_ID:
            # luminance high level, default=0x78
            sensor.__write_reg(0x24, 0x70)  # pylint: disable=W0212
            # luminance low level, default=0x68
            sensor.__write_reg(0x25, 0x60)  # pylint: disable=W0212
            sensor.skip_frames()
            self.antiglare_enabled = False

    def snapshot(self):
        """Helper to take a customized snapshot from sensor"""
        img = sensor.snapshot()
        if self.cam_id in (OV2640_ID, OV5642_ID):
            img.lens_corr(strength=1.1, zoom=0.96)
        if self.cam_id == OV2640_ID:
            img.rotation_corr(z_rotation=180)
        return img

    def capture_qr_code_loop(self, callback):
        """Captures either singular or animated QRs and parses their contents until
        all parts of the message have been captured. The part data are then ordered
        and assembled into one message and returned.
        """
        self.initialize_sensor()
        sensor.run(1)

        parser = QRPartParser()

        prev_parsed_count = 0
        new_part = False
        while True:
            wdt.feed()
            command = callback(parser.total_count(), parser.parsed_count(), new_part)
            if command == 1:
                break
            new_part = False

            img = self.snapshot()
            res = img.find_qrcodes()

            # different cases of lcd.display to show a progress bar on different devices!
            if board.config["type"] == "m5stickv":
                img.lens_corr(strength=1.0, zoom=0.56)
                lcd.display(img, oft=(0, 0), roi=(68, 52, 185, 135))
            elif board.config["type"].startswith("amigo"):
                lcd.display(img, oft=(40, 40))
            else:
                lcd.display(img, oft=(0, 0), roi=(0, 0, 304, 240))

            if len(res) > 0:
                data = res[0].payload()

                parser.parse(data)

                if parser.parsed_count() > prev_parsed_count:
                    prev_parsed_count = parser.parsed_count()
                    new_part = True

            if parser.is_complete():
                break
        gc.collect()
        sensor.run(0)

        if parser.is_complete():
            return (parser.result(), parser.format)
        return (None, None)

    def capture_entropy(self, callback):
        """Captures camera's entropy as the hash of image buffer"""
        self.initialize_sensor()
        sensor.run(1)

        command = 0
        while True:
            wdt.feed()

            img = self.snapshot()

            command = callback()
            if command > 0:
                break

            if board.config["type"] == "m5stickv":
                img.lens_corr(strength=1.0, zoom=0.56)
            lcd.display(img)

        gc.collect()
        sensor.run(0)

        # User cancelled
        if command == 2:
            return None

        img_bytes = img.to_bytes()
        del img
        hasher = hashlib.sha256()
        image_len = len(img_bytes)
        hasher_index = 0
        while hasher_index < image_len:
            hasher.update(img_bytes[hasher_index : hasher_index + 128])
            hasher_index += 128
        return hasher.digest()
