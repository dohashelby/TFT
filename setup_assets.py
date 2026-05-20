"""
Riot Data Dragon에서 현재 Set 챔피언/아이템 이미지를 다운로드.
assets/champions/, assets/items/ 에 저장.
"""
import json
import re
import time
from pathlib import Path

import requests

ASSETS_DIR = Path("assets")
CHAMP_DIR = ASSETS_DIR / "champions"
ITEM_DIR = ASSETS_DIR / "items"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_latest_version() -> str:
    versions = requests.get(
        "https://ddragon.leagueoflegends.com/api/versions.json",
        headers=HEADERS, timeout=10
    ).json()
    return versions[0]


def download_champions(version: str) -> int:
    CHAMP_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/tft-champion.json"
    data = requests.get(url, headers=HEADERS, timeout=10).json()["data"]

    # info["id"] 기준으로 가장 최신 세트 번호 선택
    champ_ids = [v.get("id", "") for v in data.values()]
    set_nums = [int(re.search(r"TFT(\d+)_", cid).group(1)) for cid in champ_ids if re.search(r"TFT(\d+)_", cid)]
    current_set = str(max(set_nums))
    current_prefix = f"TFT{current_set}_"
    filtered = [(v.get("id", ""), v) for v in data.values() if v.get("id", "").startswith(current_prefix)]
    print(f"현재 세트: TFTSet{current_set} (챔피언 {len(filtered)}명)")

    count = 0
    for champ_id, info in filtered:
        out_path = CHAMP_DIR / f"{champ_id}.png"
        if out_path.exists():
            continue

        img_name = info["image"]["full"]
        img_filename = img_name.replace("\\", "/").split("/")[-1]
        img_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/img/tft-champion/{img_filename}"
        try:
            r = requests.get(img_url, headers=HEADERS, timeout=8)
            if r.status_code == 200 and len(r.content) > 500:
                out_path.write_bytes(r.content)
                count += 1
                print(f"  OK {champ_id}")
            else:
                print(f"  SKIP {champ_id} (HTTP {r.status_code}, {len(r.content)}b)")
            time.sleep(0.05)
        except Exception as e:
            print(f"  FAIL {champ_id}: {e}")

    return count


def download_items(version: str) -> int:
    ITEM_DIR.mkdir(parents=True, exist_ok=True)
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/tft-item.json"
    data = requests.get(url, headers=HEADERS, timeout=10).json()["data"]

    count = 0
    for item_id, info in data.items():
        out_path = ITEM_DIR / f"{item_id}.png"
        if out_path.exists():
            continue

        img_name = info["image"]["full"]
        img_filename = img_name.replace("\\", "/").split("/")[-1]
        img_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/img/tft-item/{img_filename}"
        try:
            r = requests.get(img_url, headers=HEADERS, timeout=8)
            if r.status_code == 200 and len(r.content) > 500:
                out_path.write_bytes(r.content)
                count += 1
            time.sleep(0.05)
        except Exception as e:
            print(f"  FAIL {item_id}: {e}")

    return count


if __name__ == "__main__":
    print("Data Dragon 버전 확인 중...")
    version = get_latest_version()
    print(f"버전: {version}\n")

    print("챔피언 이미지 다운로드 중...")
    n_champ = download_champions(version)
    print(f"챔피언 {n_champ}개 다운로드\n")

    print("아이템 이미지 다운로드 중...")
    n_item = download_items(version)
    print(f"아이템 {n_item}개 다운로드\n")

    print("완료!")
    champ_total = len(list(CHAMP_DIR.glob("*.png")))
    item_total = len(list(ITEM_DIR.glob("*.png")))
    print(f"  챔피언 이미지: {champ_total}개")
    print(f"  아이템 이미지: {item_total}개")
