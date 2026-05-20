import json
import threading
import time
import sys
from pathlib import Path

from src.capture import ScreenCapture
from src.analyzer import GameAnalyzer
from src.advisor import Advisor
from src.overlay import Overlay
from src.meta.scraper import fetch_all

CONFIG_PATH = Path("config.json")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def analysis_loop(capture: ScreenCapture, analyzer: GameAnalyzer,
                  advisor: Advisor, overlay: Overlay, interval: float):
    print("[Main] 분석 루프 시작")
    meta_refresh_interval = 3600
    last_meta_refresh = 0

    while True:
        try:
            now = time.time()
            if now - last_meta_refresh > meta_refresh_interval:
                live_data = fetch_all()
                advisor.refresh_live_data(live_data)
                last_meta_refresh = now

            img = capture.capture_full()

            overlay.update([], status="분석 중...")
            state = analyzer.analyze(img)
            decisions = advisor.advise(state)

            stage_str = f"{state.stage}  {state.gold}G  {state.health}HP  Lv{state.level}"
            overlay.update(decisions, status=stage_str)

            print(f"\n[{stage_str}]")
            for d in decisions:
                print(f"  {d}")

        except Exception as e:
            print(f"[Main] 오류: {e}")
            overlay.update([], status=f"오류: {str(e)[:40]}")

        time.sleep(interval)


def main():
    cfg = load_config()

    # 에셋 확인
    if not Path("assets/champions").exists() or not list(Path("assets/champions").glob("*.png")):
        print("=" * 54)
        print("ERROR: 챔피언 이미지가 없습니다.")
        print("  먼저 실행: python setup_assets.py")
        print("=" * 54)
        sys.exit(1)

    print("[Main] MetaTFT 데이터 수집 중...")
    live_data = fetch_all()
    print(f"[Main] 준비 완료: 덱 {len(live_data.get('comps', []))}개")

    capture = ScreenCapture()
    analyzer = GameAnalyzer()
    advisor = Advisor(live_data)

    ov = cfg.get("overlay", {})
    overlay = Overlay(
        x=ov.get("x", 1480), y=ov.get("y", 20),
        width=ov.get("width", 420), height=ov.get("height", 680),
        alpha=ov.get("alpha", 0.88),
    )

    interval = cfg.get("capture_interval_seconds", 1)

    thread = threading.Thread(
        target=analysis_loop,
        args=(capture, analyzer, advisor, overlay, interval),
        daemon=True
    )
    thread.start()

    print("[Main] 오버레이 실행 중 (화면 우상단)")
    overlay.start()


if __name__ == "__main__":
    main()
