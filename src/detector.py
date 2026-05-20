"""
CV 기반 게임 상태 감지.
LLM 없이 템플릿 매칭 + OCR로 화면에서 직접 읽음.
"""
import re
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from .regions import (
    SHOP_SLOTS, BENCH_SLOTS, BOARD_HEXES,
    GOLD_REGION, HEALTH_REGION, LEVEL_REGION,
    ROUND_REGION, AUGMENT_NAME_REGIONS,
)
from .game_state import GameState, Champion, ShopSlot, AugmentChoice

ASSETS_DIR = Path("assets")
CHAMP_DIR = ASSETS_DIR / "champions"
ITEM_DIR = ASSETS_DIR / "items"

MATCH_THRESHOLD = 0.62   # 템플릿 매칭 최소 신뢰도
SLOT_SIZE = (72, 72)     # 매칭 전 리사이즈 크기

# 챔피언 비용별 테두리 색상 (BGR) - 상점 슬롯 상단 줄 색상
COST_COLORS_BGR = {
    1: (180, 180, 180),  # 회색
    2: (100, 200, 100),  # 초록
    3: (100, 100, 200),  # 파랑
    4: (150, 100, 200),  # 보라
    5: (200, 160, 60),   # 황금
}
COST_COLOR_TOLERANCE = 60


class Detector:
    def __init__(self):
        self.champ_templates: dict[str, np.ndarray] = {}
        self.item_templates: dict[str, np.ndarray] = {}
        self._ocr_reader = None
        self._load_templates()

    # ── 초기화 ────────────────────────────────────────────────────────────────

    def _load_templates(self):
        if not CHAMP_DIR.exists():
            print("[Detector] 챔피언 이미지 없음 → python setup_assets.py 실행 필요")
            return

        for img_path in CHAMP_DIR.glob("*.png"):
            champ_id = img_path.stem   # e.g. "TFT17_Leona"
            img = cv2.imread(str(img_path))
            if img is not None:
                img = cv2.resize(img, SLOT_SIZE)
                self.champ_templates[champ_id] = img

        for img_path in ITEM_DIR.glob("*.png"):
            item_id = img_path.stem
            img = cv2.imread(str(img_path))
            if img is not None:
                img = cv2.resize(img, (32, 32))
                self.item_templates[item_id] = img

        print(f"[Detector] 템플릿 로드: 챔피언 {len(self.champ_templates)}개, 아이템 {len(self.item_templates)}개")

    def _get_ocr(self):
        if self._ocr_reader is None:
            try:
                import easyocr
                self._ocr_reader = easyocr.Reader(["en"], verbose=False)
            except ImportError:
                self._ocr_reader = False
        return self._ocr_reader if self._ocr_reader else None

    # ── 핵심 인식 함수 ────────────────────────────────────────────────────────

    def match_champion(self, region_img: np.ndarray) -> tuple[str, float]:
        """템플릿 매칭으로 챔피언 ID와 신뢰도 반환."""
        if not self.champ_templates:
            return "", 0.0

        region_resized = cv2.resize(region_img, SLOT_SIZE)
        region_gray = cv2.cvtColor(region_resized, cv2.COLOR_BGR2GRAY)

        best_id = ""
        best_score = 0.0

        for champ_id, tmpl in self.champ_templates.items():
            tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(region_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
            score = float(result.max())
            if score > best_score:
                best_score = score
                best_id = champ_id

        return best_id, best_score

    def match_item(self, region_img: np.ndarray) -> tuple[str, float]:
        """템플릿 매칭으로 아이템 ID와 신뢰도 반환."""
        if not self.item_templates:
            return "", 0.0

        region_resized = cv2.resize(region_img, (32, 32))
        region_gray = cv2.cvtColor(region_resized, cv2.COLOR_BGR2GRAY)

        best_id, best_score = "", 0.0
        for item_id, tmpl in self.item_templates.items():
            tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(region_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
            score = float(result.max())
            if score > best_score:
                best_score = score
                best_id = item_id

        return best_id, best_score

    def read_number(self, screen: np.ndarray, region: tuple) -> int:
        """지정 영역에서 숫자 읽기."""
        x, y, w, h = region
        crop = screen[y:y+h, x:x+w]

        # 전처리: 흰색/노란색 텍스트 강조
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)

        # 간단한 digit 템플릿 매칭 시도
        reader = self._get_ocr()
        if reader:
            try:
                results = reader.readtext(thresh, detail=0, allowlist="0123456789/-")
                text = "".join(results).strip()
                nums = re.findall(r"\d+", text)
                if nums:
                    return int(nums[0])
            except Exception:
                pass
        return -1

    def read_text(self, screen: np.ndarray, region: tuple) -> str:
        """지정 영역에서 텍스트 읽기."""
        x, y, w, h = region
        crop = screen[y:y+h, x:x+w]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)

        reader = self._get_ocr()
        if reader:
            try:
                results = reader.readtext(thresh, detail=0)
                return " ".join(results).strip()
            except Exception:
                pass
        return ""

    def detect_cost_from_slot(self, screen: np.ndarray, slot_region: tuple) -> int:
        """
        상점 슬롯 테두리 색상으로 챔피언 비용 추정.
        슬롯 상단 2px 줄의 평균 색상 사용.
        """
        x, y, w, h = slot_region
        # 슬롯 상단 테두리 영역
        border = screen[y-3:y, x:x+w]
        if border.size == 0:
            return 0
        avg_color = border.mean(axis=(0, 1))  # (B, G, R)

        best_cost, best_dist = 0, 999
        for cost, ref_bgr in COST_COLORS_BGR.items():
            dist = sum(abs(float(avg_color[i]) - ref_bgr[i]) for i in range(3))
            if dist < best_dist:
                best_dist = dist
                best_cost = cost

        return best_cost if best_dist < COST_COLOR_TOLERANCE else 0

    def is_slot_affordable(self, screen: np.ndarray, slot_region: tuple) -> bool:
        """슬롯이 살 수 있는 상태인지 (어둡게 처리되면 불가)."""
        x, y, w, h = slot_region
        crop = screen[y:y+h, x:x+w]
        mean_brightness = float(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).mean())
        return mean_brightness > 60  # 어두우면 구매 불가

    def is_augment_phase(self, screen: np.ndarray) -> bool:
        """증강 선택 화면 감지 - 화면 상단 중앙에 특정 밝기 패턴."""
        # 증강 팝업은 화면 중앙에 큰 패널을 띄움
        center_region = screen[250:700, 300:1600]
        gray = cv2.cvtColor(center_region, cv2.COLOR_BGR2GRAY)
        # 증강 패널의 특징: 중앙에 밝은 패널 + 주변 어두운 배경
        bright_ratio = (gray > 200).mean()
        dark_ratio = (gray < 30).mean()
        return bright_ratio > 0.08 and dark_ratio > 0.05

    # ── 전체 게임 상태 추출 ───────────────────────────────────────────────────

    def extract(self, pil_image: Image.Image) -> GameState:
        """PIL 이미지에서 전체 게임 상태 추출."""
        screen = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        state = GameState()

        # 기본 수치
        state.gold   = max(0, self.read_number(screen, GOLD_REGION))
        state.health = max(0, self.read_number(screen, HEALTH_REGION))
        state.level  = max(1, self.read_number(screen, LEVEL_REGION))

        round_text = self.read_text(screen, ROUND_REGION)
        m = re.search(r"(\d+)[^0-9](\d+)", round_text)
        if m:
            state.stage = f"{m.group(1)}-{m.group(2)}"
            state.round = int(m.group(2))

        # 증강 선택 감지
        state.is_augment_phase = self.is_augment_phase(screen)
        if state.is_augment_phase:
            state.augment_choices = self._extract_augments(screen)
            return state

        # 상점
        state.shop = self._extract_shop(screen)

        # 벤치
        state.bench = self._extract_slots(screen, BENCH_SLOTS)

        # 보드
        state.board = self._extract_slots(screen, BOARD_HEXES)

        return state

    def _extract_shop(self, screen: np.ndarray) -> list[ShopSlot]:
        slots = []
        for region in SHOP_SLOTS:
            x, y, w, h = region
            crop = screen[y:y+h, x:x+w]

            champ_id, score = self.match_champion(crop)
            if score < MATCH_THRESHOLD or not champ_id:
                slots.append(ShopSlot(champion=None))
                continue

            name = _api_to_display(champ_id)
            cost = self.detect_cost_from_slot(screen, region)
            affordable = self.is_slot_affordable(screen, region)

            slots.append(ShopSlot(
                champion=Champion(name=name, cost=cost),
                affordable=affordable,
            ))
        return slots

    def _extract_slots(self, screen: np.ndarray, regions: list) -> list[Champion]:
        champs = []
        for region in regions:
            x, y, w, h = region
            crop = screen[y:y+h, x:x+w]
            champ_id, score = self.match_champion(crop)
            if score >= MATCH_THRESHOLD and champ_id:
                name = _api_to_display(champ_id)
                champs.append(Champion(name=name))
        return champs

    def _extract_augments(self, screen: np.ndarray) -> list[AugmentChoice]:
        augments = []
        for region in AUGMENT_NAME_REGIONS:
            text = self.read_text(screen, region)
            if text:
                augments.append(AugmentChoice(name=text))
        return augments


def _api_to_display(api_name: str) -> str:
    """TFT17_MasterYi → Master Yi"""
    name = re.sub(r"^TFT\d+_", "", api_name)
    # camelCase → 공백
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return name.strip()
