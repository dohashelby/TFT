from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Champion:
    name: str
    cost: int = 0
    stars: int = 1
    items: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)


@dataclass
class ShopSlot:
    champion: Optional[Champion]
    locked: bool = False
    affordable: bool = False


@dataclass
class AugmentChoice:
    name: str
    tier: str = ""
    description: str = ""


@dataclass
class GameState:
    stage: str = ""
    round: int = 0
    gold: int = 0
    health: int = 100
    level: int = 1
    xp: int = 0
    xp_needed: int = 4
    streak: int = 0
    board: list[Champion] = field(default_factory=list)
    bench: list[Champion] = field(default_factory=list)
    shop: list[ShopSlot] = field(default_factory=list)
    items_on_bench: list[str] = field(default_factory=list)
    augment_choices: list[AugmentChoice] = field(default_factory=list)
    active_traits: dict[str, int] = field(default_factory=dict)
    is_augment_phase: bool = False
    is_carousel: bool = False
