from PIL import Image
from .detector import Detector
from .game_state import GameState

_detector: Detector | None = None


def get_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Detector()
    return _detector


class GameAnalyzer:
    def __init__(self):
        self.detector = get_detector()

    def analyze(self, pil_image: Image.Image) -> GameState:
        return self.detector.extract(pil_image)
