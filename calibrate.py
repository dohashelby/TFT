"""
좌표 캘리브레이션 도구.

사용법:
  python calibrate.py                   # 3초 후 화면 캡처
  python calibrate.py screenshot.png    # 저장된 이미지 파일로 확인
  python calibrate.py --mock            # TFT 없이 가상 배경으로 확인
"""
import sys
import time
import cv2
import numpy as np
from PIL import Image
from src.regions import (
    SHOP_SLOTS, BENCH_SLOTS, BOARD_HEXES,
    GOLD_REGION, HEALTH_REGION, LEVEL_REGION,
    ROUND_REGION, AUGMENT_NAME_REGIONS,
    AUGMENT_SLOTS, SHOP_COST_REGIONS,
)

COLORS = {
    "shop":    (0, 255, 0),
    "bench":   (0, 165, 255),
    "board":   (255, 165, 0),
    "numbers": (0, 0, 255),
    "augment": (255, 0, 255),
}


def draw_regions(img: np.ndarray) -> np.ndarray:
    out = img.copy()

    def box(region, color, label=""):
        x, y, w, h = region
        cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        if label:
            cv2.putText(out, label, (x + 2, y - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    for i, r in enumerate(SHOP_SLOTS):
        box(r, COLORS["shop"], f"Shop{i + 1}")

    for i, r in enumerate(BENCH_SLOTS):
        box(r, COLORS["bench"], f"Bench{i + 1}" if i == 0 else "")

    for i, r in enumerate(BOARD_HEXES):
        box(r, COLORS["board"], f"H{i}" if i == 0 else "")

    box(GOLD_REGION,   COLORS["numbers"], "Gold")
    box(HEALTH_REGION, COLORS["numbers"], "HP")
    box(LEVEL_REGION,  COLORS["numbers"], "Lv")
    box(ROUND_REGION,  COLORS["numbers"], "Round")

    for i, r in enumerate(AUGMENT_NAME_REGIONS):
        box(r, COLORS["augment"], f"Aug{i + 1}")

    # 범례
    legend = [
        ("Shop (green)",   COLORS["shop"]),
        ("Bench (orange)", COLORS["bench"]),
        ("Board (blue)",   COLORS["board"]),
        ("Numbers (red)",  COLORS["numbers"]),
        ("Augment (pink)", COLORS["augment"]),
    ]
    for i, (text, color) in enumerate(legend):
        cv2.putText(out, text, (10, 20 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    return out


def make_mock_background() -> np.ndarray:
    """TFT UI를 흉내 낸 가상 배경 이미지 생성 (1920x1080)."""
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    img[:] = (20, 15, 10)  # 어두운 배경

    def fill(region, color, label=""):
        x, y, w, h = region
        cv2.rectangle(img, (x, y), (x + w, y + h), color, -1)
        cv2.rectangle(img, (x, y), (x + w, y + h), (200, 200, 200), 1)
        if label:
            cx, cy = x + w // 2, y + h // 2
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.putText(img, label, (cx - tw // 2, cy + th // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (230, 230, 230), 1, cv2.LINE_AA)

    # 보드 영역 배경
    cv2.rectangle(img, (270, 540), (950, 830), (30, 28, 22), -1)

    # 헥스
    for i, h in enumerate(BOARD_HEXES):
        fill(h, (45, 40, 32), f"H{i}")

    # 벤치
    for i, b in enumerate(BENCH_SLOTS):
        fill(b, (35, 32, 26), f"B{i+1}")

    # 상점 배경 바
    cv2.rectangle(img, (420, 830), (1200, 980), (28, 24, 18), -1)

    # 상점 슬롯
    for i, s in enumerate(SHOP_SLOTS):
        fill(s, (55, 48, 38), f"S{i+1}")
    for r in SHOP_COST_REGIONS:
        fill(r, (80, 64, 20))

    # 증강 팝업
    for i, a in enumerate(AUGMENT_SLOTS):
        fill(a, (38, 30, 50), f"Aug{i+1}")
    for r in AUGMENT_NAME_REGIONS:
        fill(r, (60, 45, 80))

    # 숫자 영역
    for region, label in [
        (GOLD_REGION,   "Gold"),
        (HEALTH_REGION, "HP"),
        (LEVEL_REGION,  "Lv"),
        (ROUND_REGION,  "Round"),
    ]:
        fill(region, (40, 40, 50), label)

    # UI 테두리 힌트
    cv2.putText(img, "MOCK BACKGROUND - src/regions.py 좌표 확인용", (600, 540),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 1, cv2.LINE_AA)

    return img


def load_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"이미지를 열 수 없습니다: {path}")
    # 1920x1080이 아니면 리사이즈
    h, w = img.shape[:2]
    if (w, h) != (1920, 1080):
        print(f"  원본 해상도: {w}x{h} → 1920x1080으로 리사이즈")
        img = cv2.resize(img, (1920, 1080))
    return img


def capture_screen() -> np.ndarray:
    from src.capture import ScreenCapture
    print("3초 후 화면 캡처합니다. TFT 화면으로 이동하세요...")
    time.sleep(3)
    cap = ScreenCapture()
    pil = cap.capture_full()
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--mock":
        print("가상 배경 모드: TFT UI 레이아웃 시뮬레이션")
        img = make_mock_background()
    elif len(sys.argv) > 1:
        img_path = sys.argv[1]
        print(f"이미지 파일 사용: {img_path}")
        img = load_image(img_path)
    else:
        img = capture_screen()

    annotated = draw_regions(img)

    # calibration_result.png 저장
    cv2.imwrite("calibration_result.png", annotated)

    print()
    print("색상 의미:")
    print("  초록  = 상점 슬롯 (Shop 1~5)")
    print("  주황  = 벤치 슬롯")
    print("  파랑  = 보드 헥스")
    print("  빨강  = 숫자 표시 (Gold, HP, Lv, Round)")
    print("  분홍  = 증강 선택 이름 영역")
    print()
    print("calibration_result.png 저장 완료 - 파일을 열어서 확인하세요")
    print("박스가 UI에 맞지 않으면 src/regions.py 수정")

    # Pillow로 이미지 표시 (OpenCV GUI 불필요)
    pil_img = Image.fromarray(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))
    pil_img = pil_img.resize((1280, 720), Image.LANCZOS)
    pil_img.show()


if __name__ == "__main__":
    main()
