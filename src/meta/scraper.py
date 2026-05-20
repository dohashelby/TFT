"""
MetaTFT 실제 API 기반 스크래퍼 (api-hc.metatft.com).
챔피언 평균 등수, 덱 승률, 아이템 빌드, 증강 승률 수집.
"""
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

CACHE_PATH = Path(__file__).parent / "cache.json"
CACHE_EXPIRY_HOURS = 4
MIN_COMP_COUNT = 200       # 덱 최소 게임 수 (노이즈 필터)
MIN_BUILD_COUNT = 100      # 아이템 빌드 최소 게임 수
TOP_COMP_LIMIT = 60        # 상위 덱 수

BASE_API = "https://api-hc.metatft.com/tft-comps-api"
DDragon_BASE = "https://ddragon.leagueoflegends.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.metatft.com",
    "Referer": "https://www.metatft.com/",
}

# Diamond+ 클러스터가 407000~407004 범위 (가장 높은 elo)
PREFERRED_CLUSTERS = ["407000", "407001", "407002"]


def _api(endpoint: str) -> dict:
    r = requests.get(BASE_API + endpoint, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def _fetch_valid_champion_ids() -> set[str]:
    """
    Riot Data Dragon에서 현재 세트 챔피언 ID 목록 가져오기.
    비플레이어블 유닛(적, 소환수 등) 필터링에 사용.
    """
    try:
        versions = requests.get(
            f"{DDragon_BASE}/api/versions.json", timeout=8
        ).json()
        latest = versions[0]
        r = requests.get(
            f"{DDragon_BASE}/cdn/{latest}/data/en_US/tft-champion.json",
            timeout=10
        )
        data = r.json().get("data", {})
        # Set17 챔피언만 추출 (TFT17_ 접두어)
        ids = {k for k in data.keys() if re.match(r"^TFT17_", k)}
        print(f"[Scraper] Data Dragon Set17 챔피언 {len(ids)}명 확인")
        return ids
    except Exception as e:
        print(f"[Scraper] Data Dragon 챔피언 목록 실패: {e}")
        return set()


def _strip_prefix(api_name: str) -> str:
    """TFT17_Illaoi → Illaoi,  TFT_Item_Warmogs → Warmog's Armor"""
    name = re.sub(r"^TFT\d+_", "", api_name)
    name = re.sub(r"^TFT_Item_", "", name)
    name = re.sub(r"^TFT_", "", name)
    # camelCase → 공백 분리
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return name.strip()


def _trait_label(traits_list: str) -> str:
    """TFT17_DarkStar_2&TFT17_ADMIN_2 → 'Dark Star + Admin'"""
    labels = []
    for t in traits_list.split("&"):
        t = re.sub(r"^TFT\d+_", "", t)
        t = re.sub(r"_\d+$", "", t)       # 숫자 제거
        t = re.sub(r"([a-z])([A-Z])", r"\1 \2", t)
        t = t.replace("_", " ").strip()
        if t and t.lower() not in ("unique trait", "flex trait", "choose trait"):
            labels.append(t)
    return " + ".join(labels[:3]) if labels else "Unknown"


def _load_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        saved_at = datetime.fromisoformat(data.get("saved_at", "2000-01-01"))
        if datetime.now() - saved_at < timedelta(hours=CACHE_EXPIRY_HOURS):
            age = int((datetime.now() - saved_at).total_seconds() / 60)
            print(f"[Scraper] 캐시 사용 ({age}분 전 저장 | "
                  f"덱 {len(data.get('comps', []))}개 | "
                  f"챔피언 {len(data.get('champions', {}))}개)")
            return data
        print("[Scraper] 캐시 만료 → 새로 수집")
    except Exception:
        pass
    return None


def _save_cache(data: dict):
    data["saved_at"] = datetime.now().isoformat()
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _fetch_champions(valid_ids: set[str]) -> dict:
    """
    챔피언 평균 등수 + 베스트 아이템.
    valid_ids로 플레이어블 챔피언만 필터링.
    """
    raw = _api("/unit_items_processed")
    units_raw = raw.get("units", {})

    champions = {}
    for api_name, stats in units_raw.items():
        # 플레이어블 챔피언 필터: Data Dragon 목록 or TFT17_ 대문자 패턴
        is_valid = (
            api_name in valid_ids or
            (re.match(r"^TFT17_[A-Z]", api_name) and
             not any(kw in api_name.lower() for kw in
                     ["pve", "enemy", "swarm", "tracker", "follower",
                      "minion", "summon", "ward", "dragon", "raptor"]))
        )
        if not is_valid:
            continue

        name = _strip_prefix(api_name)
        avg = float(stats.get("avg", 4.5))
        count = int(stats.get("count", 0))
        pick = float(stats.get("pick", 0))
        top4_rate = max(0.0, (4.5 - avg) / 3.5 * 100)

        items_raw = stats.get("items", [])
        best_items = [_fix_item_name(_strip_prefix(i.get("itemName", "")))
                      for i in items_raw[:5] if i.get("itemName")]

        champions[name] = {
            "api_name": api_name,
            "avg_placement": avg,
            "top4_rate": round(top4_rate, 1),
            "count": count,
            "pick_rate": round(pick * 100, 2),
            "best_items": best_items,
        }
    return champions


def _fetch_comps() -> list[dict]:
    """덱 단위 평균 등수 + 구성 챔피언 목록"""
    raw = _api("/comp_options")
    options = raw.get("results", {}).get("options", {})

    all_comps: list[dict] = []
    seen_units = set()

    # 상위 클러스터에서 8~10유닛 덱 수집
    for cluster in PREFERRED_CLUSTERS:
        cluster_data = options.get(cluster, {})
        for size_key in ["8", "9", "10"]:
            for entry in cluster_data.get(size_key, []):
                units_str = entry.get("units_list", "")
                count = int(entry.get("count", 0))
                avg = float(entry.get("avg", 4.5))

                if count < MIN_COMP_COUNT:
                    continue
                if units_str in seen_units:
                    continue
                seen_units.add(units_str)

                units = [_strip_prefix(u) for u in units_str.split("&") if u]
                traits_str = entry.get("traits_list", "")
                label = _trait_label(traits_str)
                top4_rate = max(0.0, (4.5 - avg) / 3.5 * 100)
                win_rate = max(0.0, (4.5 - avg) / 3.5 * 15)   # 근사

                all_comps.append({
                    "units": units,
                    "label": label,
                    "avg_placement": round(avg, 4),
                    "top4_rate": round(top4_rate, 1),
                    "win_rate": round(win_rate, 1),
                    "count": count,
                    "cluster": cluster,
                })

    # avg 기준 정렬 (낮을수록 좋음) 후 상위 N개
    all_comps.sort(key=lambda x: x["avg_placement"])
    return all_comps[:TOP_COMP_LIMIT]


ITEM_NAME_FIXES = {
    "Thiefs Gloves": "Thief's Gloves",
    "Warmogs Armor": "Warmog's Armor",
    "Madreds Bloodrazor": "Madred's Bloodrazor",
    "Steraks Gage": "Sterak's Gage",
    "Runaans Hurricane": "Runaan's Hurricane",
    "Guinsoos Rageblade": "Guinsoo's Rageblade",
    "Dragons Claw": "Dragon's Claw",
    "Titans Resolve": "Titan's Resolve",
    "Spear Of Shojin": "Spear of Shojin",
}


def _fix_item_name(name: str) -> str:
    return ITEM_NAME_FIXES.get(name, name)


def _fetch_item_builds() -> dict:
    """챔피언별 베스트 아이템 빌드 (avg 기준)"""
    raw = _api("/comp_builds")
    results = raw.get("results", {})

    builds: dict[str, list] = {}
    seen = set()

    for cluster in PREFERRED_CLUSTERS:
        cluster_data = results.get(cluster, {})
        for entry in cluster_data.get("builds", []):
            unit = _strip_prefix(entry.get("unit", ""))
            items = [_strip_prefix(i) for i in entry.get("buildName", []) if i]
            count = int(entry.get("count", 0))
            avg = float(entry.get("avg", 4.5))

            if count < MIN_BUILD_COUNT or not unit or not items:
                continue

            key = f"{unit}|{'&'.join(items)}"
            if key in seen:
                continue
            seen.add(key)

            if unit not in builds:
                builds[unit] = []
            builds[unit].append({
                "items": [_fix_item_name(i) for i in items],
                "avg_placement": round(avg, 4),
                "count": count,
            })

    # 챔피언별 avg 기준 정렬
    for unit in builds:
        builds[unit].sort(key=lambda x: x["avg_placement"])

    return builds


def _fetch_augments() -> dict:
    """증강별 통계 (data가 있을 경우)"""
    try:
        raw = _api("/comp_augments")
        aug_options = raw.get("results", {}).get("augment_options", {})

        augments = {}
        for aug_name, cluster_data in aug_options.items():
            stats_list = []
            for cluster in PREFERRED_CLUSTERS:
                cdata = cluster_data.get(cluster, {})
                if not cdata:
                    continue
                avg = float(cdata.get("avg", 4.5))
                count = int(cdata.get("count", 0))
                if count > 50:
                    stats_list.append((avg, count))

            if stats_list:
                avg_total = sum(a * c for a, c in stats_list) / sum(c for _, c in stats_list)
                total_count = sum(c for _, c in stats_list)
                top4_rate = max(0.0, (4.5 - avg_total) / 3.5 * 100)
                augments[aug_name] = {
                    "avg_placement": round(avg_total, 4),
                    "top4_rate": round(top4_rate, 1),
                    "win_rate": round(top4_rate / 4, 1),
                    "count": total_count,
                }
    except Exception as e:
        print(f"[Scraper] 증강 데이터 수집 실패: {e}")
        augments = {}

    return augments


def fetch_all() -> dict:
    """
    MetaTFT API에서 모든 데이터 수집 후 반환.
    캐시 유효하면 캐시 반환, 아니면 새로 수집.
    """
    cached = _load_cache()
    if cached:
        return cached

    print("[Scraper] MetaTFT 데이터 수집 시작...")

    # 현재 세트 확인
    try:
        cluster_info = _api("/latest_cluster_id")
        tft_set = cluster_info.get("tft_set", "Unknown")
        cluster_id = cluster_info.get("cluster_id", 0)
        print(f"[Scraper] 현재 세트: {tft_set} (클러스터 {cluster_id})")
    except Exception as e:
        print(f"[Scraper] 클러스터 확인 실패: {e}")
        tft_set = "Unknown"

    champions = {}
    comps = []
    item_builds = {}
    augments = {}

    valid_ids = _fetch_valid_champion_ids()
    time.sleep(0.3)

    try:
        print("[Scraper] 챔피언 통계 수집 중...")
        champions = _fetch_champions(valid_ids)
        print(f"[Scraper] 챔피언 {len(champions)}명 수집 (플레이어블)")
        time.sleep(0.4)
    except Exception as e:
        print(f"[Scraper] 챔피언 수집 실패: {e}")

    try:
        print("[Scraper] 덱 구성 수집 중...")
        comps = _fetch_comps()
        print(f"[Scraper] 덱 {len(comps)}개 수집 (avg 기준 정렬)")
        time.sleep(0.4)
    except Exception as e:
        print(f"[Scraper] 덱 수집 실패: {e}")

    try:
        print("[Scraper] 아이템 빌드 수집 중...")
        item_builds = _fetch_item_builds()
        print(f"[Scraper] 아이템 빌드 {len(item_builds)}명분 수집")
        time.sleep(0.4)
    except Exception as e:
        print(f"[Scraper] 아이템 빌드 수집 실패: {e}")

    try:
        print("[Scraper] 증강 데이터 수집 중...")
        augments = _fetch_augments()
        print(f"[Scraper] 증강 {len(augments)}개 수집")
    except Exception as e:
        print(f"[Scraper] 증강 수집 실패: {e}")

    result = {
        "tft_set": tft_set,
        "champions": champions,
        "comps": comps,
        "item_builds": item_builds,
        "augments": augments,
    }

    _save_cache(result)
    print(f"[Scraper] 수집 완료: 챔피언 {len(champions)}명 | 덱 {len(comps)}개 | 증강 {len(augments)}개")
    return result


# ── 조회 헬퍼 ────────────────────────────────────────────────────────────────

def get_champion_stats(name: str, data: dict) -> dict:
    champs = data.get("champions", {})
    if name in champs:
        return champs[name]
    name_lower = name.lower()
    for k, v in champs.items():
        if k.lower() == name_lower:
            return v
    return {"avg_placement": 4.5, "top4_rate": 40.0, "best_items": []}


def get_augment_stats(name: str, data: dict) -> dict:
    augs = data.get("augments", {})
    if name in augs:
        return augs[name]
    name_lower = name.lower()
    for k, v in augs.items():
        if k.lower() == name_lower or name_lower in k.lower():
            return v
    return {"avg_placement": 4.5, "top4_rate": 40.0}


def get_best_items(champion_name: str, data: dict) -> list[str]:
    builds = data.get("item_builds", {}).get(champion_name, [])
    if builds:
        return builds[0]["items"]
    # fallback: unit_items_processed best_items
    champ = get_champion_stats(champion_name, data)
    return champ.get("best_items", [])
