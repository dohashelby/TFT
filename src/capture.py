import mss
from PIL import Image


class ScreenCapture:
    def __init__(self):
        self.sct = mss.mss()

    def capture_full(self) -> Image.Image:
        monitor = self.sct.monitors[1]
        shot = self.sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def capture_region(self, x: int, y: int, w: int, h: int) -> Image.Image:
        region = {"left": x, "top": y, "width": w, "height": h}
        shot = self.sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
