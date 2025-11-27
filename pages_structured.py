# pages_structured.py
import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

from unit import DamageType, DiceKind, StatusType


class EffectTiming(Enum):
    ON_USE = "ON_USE"
    ON_BATTLE_START = "ON_BATTLE_START"


class EffectTrigger(Enum):
    NONE = "NONE"
    ON_HIT = "ON_HIT"
    ON_CLASH_WIN = "ON_CLASH_WIN"
    ON_CLASH_LOSS = "ON_CLASH_LOSS"
    ON_BE_HIT = "ON_BE_HIT"
    ON_DEFEND = "ON_DEFEND"


class EffectTarget(Enum):
    SELF = "SELF"
    ENEMY = "ENEMY"
    ALLY_ALL = "ALLY_ALL"
    ENEMY_ALL = "ENEMY_ALL"


@dataclass
class EffectSpec:
    timing: EffectTiming
    trigger: EffectTrigger
    target: EffectTarget
    status: Optional[StatusType]
    amount: int
    duration: int


@dataclass
class DiceSpec:
    index: int
    kind: DiceKind
    damage_type: Optional[DamageType]
    min_value: int
    max_value: int
    effect: Optional[EffectSpec] = None


@dataclass
class CombatPage:
    card_id: int
    grade: str
    cost: int
    name: str
    use_effect: Optional[EffectSpec] = None
    dice_list: List[DiceSpec] = field(default_factory=list)


def _parse_status(s: str) -> Optional[StatusType]:
    s = (s or "").strip().upper()
    if not s:
        return None
    if s == "HASTE":
        return StatusType.HASTE
    if s == "STRENGTH":
        return StatusType.STRENGTH
    if s == "ENDURANCE":
        return StatusType.ENDURANCE
    if s == "FRAGILE":
        return StatusType.FRAGILE
    if s == "BLEED":
        return StatusType.BLEED
    if s == "PARALYSIS":
        return StatusType.PARALYSIS
    if s == "PROTECT": return StatusType.PROTECT
    if s == "VULNERABLE": return StatusType.VULNERABLE
    if s == "PARALYSIS": return StatusType.PARALYSIS
    if s == "BLEED": return StatusType.BLEED
    if s == "BURN": return StatusType.BURN
    if s == "BIND": return StatusType.BIND
    if s == "WEAK": return StatusType.WEAK
    if s == "SMOKE": return StatusType.SMOKE
    if s == "CHARGE": return StatusType.CHARGE
    if s == "TARGET": return StatusType.TARGET
    if s == "CORROSION": return StatusType.CORROSION
    if s == "STAGGER_PROTECT": return StatusType.STAGGER_PROTECT
    if s == "NAIL": return StatusType.NAIL
    if s == "FAIRY": return StatusType.FAIRY
    if s == "FLARE": return StatusType.FLARE
    if s == "LAST_STAND": return StatusType.LAST_STAND
    if s == "HP_HEAL": return StatusType.HP_HEAL
    if s == "LIGHT": return StatusType.LIGHT

    # LIGHT 같은 자원 효과는 StatusType 대신 따로 처리할 수도 있음
    return None


def _parse_timing(s: str) -> Optional[EffectTiming]:
    s = (s or "").strip().upper()
    if not s:
        return None
    return EffectTiming[s]


def _parse_trigger(s: str) -> EffectTrigger:
    s = (s or "").strip().upper()
    if not s:
        return EffectTrigger.NONE
    try:
        return EffectTrigger[s]
    except KeyError:
        # 알 수 없는 트리거는 기본값으로 처리
        return EffectTrigger.NONE


def _parse_target(s: str) -> Optional[EffectTarget]:
    s = (s or "").strip().upper()
    if not s:
        return None
    return EffectTarget[s]


def load_combat_pages(path: str) -> Dict[int, CombatPage]:
    pages: Dict[int, CombatPage] = {}

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            card_id = int(row["card_id"])

            if card_id not in pages:
                use_timing = _parse_timing(row["use_timing"])
                use_effect = None
                if use_timing is not None:
                    use_effect = EffectSpec(
                        timing=use_timing,
                        trigger=EffectTrigger.NONE,
                        target=_parse_target(row["use_target"]) or EffectTarget.SELF,
                        status=_parse_status(row["use_status"]),
                        amount=int(row["use_amount"]),
                        duration=int(row["use_duration"]),
                    )

                pages[card_id] = CombatPage(
                    card_id=card_id,
                    grade=row["grade"],
                    cost=int(row["cost"]),
                    name=row["name"],
                    use_effect=use_effect,
                )

            page = pages[card_id]

            dice_effect = None
            trig = _parse_trigger(row["dice_trigger"])
            if trig != EffectTrigger.NONE:
                dice_effect = EffectSpec(
                    timing=EffectTiming.ON_USE,  # 주사위는 일단 고정
                    trigger=trig,
                    target=_parse_target(row["dice_target"]) or EffectTarget.ENEMY,
                    status=_parse_status(row["dice_status"]),
                    amount=int(row["dice_amount"]),
                    duration=int(row["dice_duration"]),
                )

            dice = DiceSpec(
                index=int(row["dice_index"]),
                kind=DiceKind[row["dice_kind"]],
                damage_type=DamageType[row["damage_type"]] if row["damage_type"] else None,
                min_value=int(row["min"]),
                max_value=int(row["max"]),
                effect=dice_effect,
            )
            page.dice_list.append(dice)

    for p in pages.values():
        p.dice_list.sort(key=lambda d: d.index)

    return pages
