"""
MetaTFT 실제 승률 데이터 기반 추천 엔진.
모든 결정에 EV(기대값)와 승률 수치를 함께 표시.
"""
from .game_state import GameState
from .meta.loader import rank_comps
from .meta.scraper import get_augment_stats, get_best_items, get_champion_stats


class Decision:
    def __init__(self, priority: str, action: str, detail: str = "", ev: float | None = None):
        self.priority = priority
        self.action = action
        self.detail = detail
        self.ev = ev

    def __repr__(self):
        ev_str = f" EV{self.ev:+.2f}" if self.ev is not None else ""
        return f"[{self.priority}]{ev_str} {self.action}"


class Advisor:
    def __init__(self, live_data: dict):
        self.live_data = live_data
        self.ranked = []

    def refresh_live_data(self, live_data: dict):
        self.live_data = live_data

    def advise(self, state: GameState) -> list[Decision]:
        if state.is_carousel:
            return [Decision("INFO", "캐러셀", "BF Sword / Recurve Bow / NLR 우선")]

        if state.is_augment_phase:
            return self._advise_augment(state)

        owned = [c.name for c in state.board + state.bench]
        all_items = [i for c in state.board + state.bench for i in c.items] + state.items_on_bench

        self.ranked = rank_comps(owned, all_items, self.live_data)

        decisions: list[Decision] = []
        decisions += self._advise_economy(state)
        decisions += self._advise_shop(state)
        decisions += self._advise_items(state)
        decisions += self._advise_sell(state)
        decisions += self._advise_level(state)
        decisions += self._comp_summary()
        return decisions

    # ── 경제 ─────────────────────────────────────────────────────────────────

    def _advise_economy(self, state: GameState) -> list[Decision]:
        decisions = []
        gold, hp = state.gold, state.health

        if hp <= 25:
            decisions.append(Decision(
                "URGENT",
                f"체력 위험 {hp}HP — 즉시 롤다운!",
                "골드 절약 포기. 지금 바로 레벨업 + 롤."
            ))
            return decisions

        interest_bp = next((bp for bp in [10, 20, 30, 40, 50] if bp > gold), None)
        gap = (interest_bp - gold) if interest_bp else 0

        if gold >= 50:
            decisions.append(Decision(
                "ECONOMY", f"골드 {gold}G — 이자 5G/턴 유지",
                "50G 이자 구간. 자연 롤 또는 레벨업만."
            ))
        elif gap <= 2 and interest_bp:
            decisions.append(Decision(
                "ECONOMY", f"이자 구간 {interest_bp}G까지 {gap}G 부족",
                f"{interest_bp}G 유지하면 {interest_bp//10}G/턴 이자 확보."
            ))
        return decisions

    # ── 상점 ─────────────────────────────────────────────────────────────────

    def _advise_shop(self, state: GameState) -> list[Decision]:
        decisions = []
        if not self.ranked:
            return decisions

        best = self.ranked[0]
        target_units = set(u.lower() for u in best.get("units", []))

        # 2순위 덱 유닛도 구매 후보에 포함
        if len(self.ranked) > 1:
            for u in self.ranked[1].get("units", []):
                target_units.add(u.lower())

        owned_counts: dict[str, int] = {}
        for c in state.board + state.bench:
            owned_counts[c.name.lower()] = owned_counts.get(c.name.lower(), 0) + 1

        for slot in state.shop:
            if not slot.champion or not slot.affordable:
                continue
            name_l = slot.champion.name.lower()
            cost = slot.champion.cost
            count = owned_counts.get(name_l, 0)
            in_target = name_l in target_units

            if not in_target:
                continue

            champ_stats = get_champion_stats(slot.champion.name, self.live_data)
            champ_avg = champ_stats.get("avg_placement", 4.5)

            if count >= 6:
                action = f"구매: {slot.champion.name} ★★★ 진행"
                detail = f"현재 {count}장 → 3성까지 {9-count}장 | 챔피언 평균 {champ_avg:.2f}위"
                ev = self._buy_ev(cost, 0.20, best["top4_rate"])
            elif count >= 2:
                action = f"구매: {slot.champion.name} 2성 진행"
                detail = f"현재 {count}장 → 2성까지 {3-count}장 | 챔피언 평균 {champ_avg:.2f}위"
                ev = self._buy_ev(cost, 0.13, best["top4_rate"])
            else:
                action = f"구매: {slot.champion.name}"
                detail = f"덱 핵심 | {cost}G | 챔피언 평균 {champ_avg:.2f}위"
                ev = self._buy_ev(cost, 0.07, best["top4_rate"])

            decisions.append(Decision("BUY", action, detail, ev=ev))

        roll_dec = self._should_roll(state)
        if roll_dec:
            decisions.append(roll_dec)

        return decisions

    def _buy_ev(self, cost: int, boost: float, top4: float) -> float:
        return round(boost * (top4 / 100) * 10 - cost * 0.04, 2)

    def _should_roll(self, state: GameState) -> Decision | None:
        if not self.ranked:
            return None
        best = self.ranked[0]
        completion = best.get("completion", 0)
        top4 = best.get("top4_rate", 40)
        avg = best.get("avg_placement", 4.5)

        if state.health <= 30 and state.gold >= 10:
            return Decision("URGENT", f"체력 {state.health}HP — 지금 롤!",
                            f"완성도 {completion*100:.0f}% | 예상 등수 {avg:.2f}위")

        if completion < 0.65 and state.gold > 30 and state.level >= 6:
            ev = round((1 - completion) * (top4 / 100) * 8, 2)
            return Decision(
                "ECONOMY",
                f"롤 고려 — 완성도 {completion*100:.0f}% (목표 65%)",
                f"골드 {state.gold}G | 예상 Top4율 {top4:.1f}% | 평균 {avg:.2f}위",
                ev=ev
            )
        return None

    # ── 아이템 ───────────────────────────────────────────────────────────────

    def _advise_items(self, state: GameState) -> list[Decision]:
        decisions = []
        bench = state.items_on_bench
        if not bench or not self.ranked:
            return decisions

        best = self.ranked[0]
        carry = best.get("carry", "")
        bis = get_best_items(carry, self.live_data)

        # 조합 가능한 BIS 아이템 (간단히 이름 포함 여부로 체크)
        if bis and carry:
            carry_obj = next((c for c in state.board if c.name.lower() == carry.lower()), None)
            slots_used = len(carry_obj.items) if carry_obj else 0
            for item in bis[:3]:
                if slots_used >= 3:
                    break
                if item in bench:
                    decisions.append(Decision(
                        "ITEM",
                        f"{carry}에게 {item} 장착",
                        f"BIS 아이템 {slots_used+1}/3 | carry 평균 등수 향상 기대"
                    ))
                    slots_used += 1

        # 아이템 미리보기 (가진 컴포넌트로 만들 수 있는 BIS)
        if bench and carry and bis:
            for target_item in bis[:3]:
                if target_item not in bench:
                    decisions.append(Decision(
                        "INFO",
                        f"필요 아이템: {target_item} (for {carry})",
                        f"캐러셀/몬스터 라운드에서 컴포넌트 확보 우선"
                    ))
                    break

        return decisions

    # ── 매각 ─────────────────────────────────────────────────────────────────

    def _advise_sell(self, state: GameState) -> list[Decision]:
        decisions = []
        if len(state.bench) < 8:
            return decisions

        target_set = set()
        for r in self.ranked[:2]:
            for u in r.get("units", []):
                target_set.add(u.lower())

        for champ in state.bench:
            if champ.name.lower() not in target_set and champ.stars == 1 and not champ.items:
                champ_stats = get_champion_stats(champ.name, self.live_data)
                avg = champ_stats.get("avg_placement", 4.5)
                decisions.append(Decision(
                    "SELL",
                    f"매각: {champ.name} (덱 무관 / 평균 {avg:.2f}위)",
                    f"벤치 자리 확보. {champ.cost}G 회수."
                ))
                break  # 한 번에 하나씩만 제안

        return decisions

    # ── 레벨업 ───────────────────────────────────────────────────────────────

    def _advise_level(self, state: GameState) -> list[Decision]:
        xp_stages = {"3-2", "4-1", "4-5"}
        if state.stage in xp_stages and state.gold >= 4:
            return [Decision(
                "ECONOMY",
                f"경험치 구매 ({state.stage})",
                f"4G → 레벨 {state.level}→{state.level+1} 가속"
            )]
        if state.level <= 6 and state.gold >= 40:
            return [Decision(
                "ECONOMY",
                f"레벨업 고려 (현재 {state.level})",
                "골드 여유 있음. 4G 투자해도 이자 영향 없음."
            )]
        return []

    # ── 증강 ─────────────────────────────────────────────────────────────────

    def _advise_augment(self, state: GameState) -> list[Decision]:
        decisions = []
        best_comp_units = set()
        if self.ranked:
            for u in self.ranked[0].get("units", []):
                best_comp_units.add(u.lower())

        scored = []
        for aug in state.augment_choices:
            stats = get_augment_stats(aug.name, self.live_data)
            avg = stats.get("avg_placement", 4.5)
            top4 = stats.get("top4_rate", 40.0)
            win_rate = stats.get("win_rate", 10.0)

            score = (8.0 - avg) / 7.0 * 100

            # 경제 증강 보너스
            econ_kw = ["gold", "loot", "ticket", "silver", "rich", "fortune", "interest"]
            if any(kw in aug.name.lower() for kw in econ_kw) and state.gold < 25:
                score += 8

            scored.append({
                "aug": aug, "score": score,
                "avg": avg, "top4": top4, "win": win_rate,
            })

        scored.sort(key=lambda x: -x["score"])

        for i, s in enumerate(scored):
            prefix = ["선택:", "2순위:", "3순위:"][i] if i < 3 else f"{i+1}순위:"
            data_str = f"평균 {s['avg']:.2f}위 | Top4 {s['top4']:.1f}% | 1등 {s['win']:.1f}%"
            if s["avg"] == 4.5:
                data_str = "데이터 부족 — 직접 판단 필요"

            decisions.append(Decision(
                "AUGMENT" if i == 0 else "INFO",
                f"{prefix} {s['aug'].name}",
                data_str,
                ev=round(s["score"], 1) if i == 0 else None
            ))

        return decisions

    # ── 덱 요약 ──────────────────────────────────────────────────────────────

    def _comp_summary(self) -> list[Decision]:
        if not self.ranked:
            return []

        decisions = []
        best = self.ranked[0]

        missing_str = ", ".join(best.get("missing", [])[:5]) or "없음"
        decisions.append(Decision(
            "INFO",
            f"목표 덱  완성도 {best['completion']*100:.0f}%  ({best['have']}/{best['total']})",
            (
                f"평균 {best['avg_placement']:.2f}위 | Top4 {best['top4_rate']:.1f}% | "
                f"게임수 {best['count']:,}\n"
                f"부족: {missing_str}"
            )
        ))

        if len(self.ranked) > 1:
            s = self.ranked[1]
            decisions.append(Decision(
                "INFO",
                f"대안 덱  완성도 {s['completion']*100:.0f}%",
                f"평균 {s['avg_placement']:.2f}위 | Top4 {s['top4_rate']:.1f}% | {s['label']}"
            ))

        return decisions
