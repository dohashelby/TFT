"""
실시간 MetaTFT 데이터를 기반으로 현재 보드에서 갈 수 있는
최적 덱을 점수화하여 반환.
"""
from .scraper import get_best_items


def score_comp(comp: dict, owned_names: list[str], owned_items: list[str],
               live_data: dict) -> dict:
    """
    덱 점수 계산 (가중 합산 0~1).

    base_score  : MetaTFT 평균 등수 기반 (낮을수록 좋음)
    completion  : 핵심 챔피언 보유 비율
    item_align  : 최고 캐리의 BIS 아이템 보유 비율
    """
    owned_set = {n.lower() for n in owned_names}
    comp_units = comp.get("units", [])
    avg = comp.get("avg_placement", 4.5)

    # 1. 기반 승률 점수 (1등=1.0, 8등=0.0)
    base_score = max(0.0, (8.0 - avg) / 7.0)

    # 2. 완성도
    if comp_units:
        have = sum(1 for u in comp_units if u.lower() in owned_set)
        completion = have / len(comp_units)
    else:
        completion = 0.0

    # 3. 아이템 얼라인먼트 (첫 번째 챔피언 = 캐리 가정)
    carry = comp_units[0] if comp_units else ""
    bis = get_best_items(carry, live_data)
    if bis:
        matched = sum(1 for item in bis[:3] if item in owned_items)
        item_align = matched / min(len(bis), 3)
    else:
        item_align = 0.0

    # 4. 샘플 수 신뢰도 보정 (게임 수 많을수록 신뢰도 높음)
    count = comp.get("count", 0)
    confidence = min(1.0, count / 2000)

    final = (
        base_score   * 0.30 +
        completion   * 0.50 +
        item_align   * 0.10 +
        confidence   * 0.10
    )

    missing = [u for u in comp_units if u.lower() not in owned_set]

    return {
        "score":         round(final, 4),
        "base_score":    round(base_score, 4),
        "completion":    round(completion, 4),
        "item_align":    round(item_align, 4),
        "avg_placement": avg,
        "top4_rate":     comp.get("top4_rate", 40.0),
        "win_rate":      comp.get("win_rate", 10.0),
        "count":         count,
        "carry":         carry,
        "missing":       missing,
        "have":          len(comp_units) - len(missing),
        "total":         len(comp_units),
    }


def rank_comps(owned_names: list[str], owned_items: list[str],
               live_data: dict) -> list[dict]:
    """
    live_data의 모든 덱을 점수 순으로 정렬.
    각 항목: comp 원본 + scored 결과 병합.
    """
    results = []
    for comp in live_data.get("comps", []):
        scored = score_comp(comp, owned_names, owned_items, live_data)
        results.append({**comp, **scored})

    results.sort(key=lambda x: -x["score"])
    return results
