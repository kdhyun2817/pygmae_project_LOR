# page_preprocessing_2.py
# 2단계 전처리: combat_pages_normalized.csv -> combat_pages_structured.csv
import csv
import re
from pathlib import Path

SRC = Path("combat_pages_normalized.csv")
DST = Path("combat_pages_structured.csv")

# -----------------------------
# 공통: 상태이상 / 자원 키워드
# -----------------------------
STATUS_KEYWORDS = [
    ("신속", "HASTE"),
    ("힘", "STRENGTH"),
    ("인내", "ENDURANCE"),
    ("보호", "PROTECT"),
    ("취약", "VULNERABLE"),
    ("마비", "PARALYSIS"),
    ("출혈", "BLEED"),
    ("화상", "BURN"),
    ("속박", "BIND"),
    ("허약", "WEAK"),
    ("연기", "SMOKE"),
    ("충전", "CHARGE"),
]

# HP / 빛은 상태이상이 아니라 자원 효과지만,
# 전처리 단계에서는 편의상 가짜 status 코드로 넣어두고
# 나중에 게임 코드에서 특별취급해도 됨.
RESOURCE_PATTERNS = [
    # 체력 3 회복, 체력 2를 회복, 등
    (re.compile(r"체력\s*(\d+)\s*회복"), "HP_HEAL"),
    # 빛 2 회복, 빛 1을 얻음 등
    (re.compile(r"빛\s*(\d+)\s*(?:을|를)?\s*(회복|얻)"), "LIGHT"),
]


# -----------------------------
# 유틸 함수
# -----------------------------
def extract_status_and_amount(text: str):
    """
    텍스트에서 상태이상/자원 + 수치를 찾아서 (status_code, amount)를 반환.
    못 찾으면 ("", 0).
    """
    text = (text or "").strip()
    if not text:
        return "", 0

    # 1) 상태이상들
    for korean, code in STATUS_KEYWORDS:
        if korean in text:
            m = re.search(rf"{korean}\s*(\d+)", text)
            amount = int(m.group(1)) if m else 1
            return code, amount

    # 2) 자원 (체력 / 빛)
    for pattern, code in RESOURCE_PATTERNS:
        m = pattern.search(text)
        if m:
            amount = int(m.group(1))
            return code, amount

    return "", 0


def infer_duration(text: str, status_code: str, is_use_effect: bool):
    """
    지속 턴 수 추정.
    - "다음 막" / "다음막" 존재 시: 2
    - "이번 막" / "이번막" 존재 시: 1
    - 그 외:
        - 버프/디버프: 1
        - 자원(HP_HEAL / LIGHT): 0
    """
    text = (text or "").replace(" ", "")

    if "다음막" in text or "다음턴" in text:
        return 2
    if "이번막" in text or "이번턴" in text:
        return 1

    if status_code in ("HP_HEAL", "LIGHT"):
        return 0

    # 사용효과면 기본 1, 주사위 효과도 기본 1
    return 1


def infer_use_timing(use_type: str):
    """
    use_type 문자열(예: '사용시', '전투 시작')을
    전처리용 타이밍 코드로 변환.
    """
    use_type = (use_type or "").strip()
    if not use_type:
        return ""

    if "사용" in use_type:
        return "ON_USE"
    if "전투" in use_type and "시작" in use_type:
        return "ON_BATTLE_START"
    # 필요하면 장착시, 소모시 등도 추가 가능
    return ""


def infer_dice_trigger(trigger: str, effect_text: str):
    """
    주사위 트리거 문자열 + 효과 텍스트로부터
    전처리용 트리거 코드 반환.
    """
    base = (trigger or "") + " " + (effect_text or "")
    base = base.replace(" ", "")

    if "합승리" in base:
        return "ON_CLASH_WIN"
    if "합패배" in base:
        return "ON_CLASH_LOSS"
    if "피격" in base:
        return "ON_BE_HIT"
    if "방어시" in base or ("방어" in base and "시" in base):
        return "ON_DEFEND"
    if "적중" in base:
        return "ON_HIT"

    return ""


def infer_target(text: str, default: str):
    """
    효과 대상 추정.
    default는 USE_EFFECT에서는 보통 "SELF",
    DICE_EFFECT에서는 보통 "ENEMY"로 넘겨주면 됨.
    """
    text = (text or "").replace(" ", "")
    if not text:
        return default

    if "모든아군" in text or "아군전체" in text:
        return "ALLY_ALL"
    if "모든적" in text or "적전체" in text:
        return "ENEMY_ALL"
    if "무작위아군" in text or "랜덤아군" in text:
        # 엄밀히는 ALLY_RANDOM이지만, 일단 ALLY_ALL로 두고
        # 나중에 게임 코드에서 처리해도 됨.
        return "ALLY_ALL"
    if "무작위적" in text or "랜덤적" in text:
        return "ENEMY_ALL"
    if "자신" in text or "자기자신" in text:
        return "SELF"
    if "아군" in text:
        return "ALLY_ALL"
    if "적" in text:
        return "ENEMY"

    return default


# -----------------------------
# 1) 카드 사용 효과 파싱
# -----------------------------
def parse_use_effect(use_type: str, use_text: str):
    """
    카드 헤더의 사용 효과를 구조화.
    결과: (use_timing, use_target, use_status, use_amount, use_duration)
    """
    use_type = (use_type or "").strip()
    text = (use_text or "").strip()

    if not use_type or not text:
        return "", "", "", 0, 0

    timing = infer_use_timing(use_type)
    if not timing:
        return "", "", "", 0, 0

    status_code, amount = extract_status_and_amount(text)
    if not status_code:
        return "", "", "", 0, 0

    target = infer_target(text, default="SELF")
    duration = infer_duration(text, status_code, is_use_effect=True)

    return timing, target, status_code, amount, duration


# -----------------------------
# 2) 주사위 효과 파싱
# -----------------------------
def parse_dice_effect(trigger: str, effect_text: str):
    """
    주사위 줄의 trigger + effect_text를 구조화.
    결과: (dice_trigger, dice_target, dice_status, dice_amount, dice_duration, raw_dice_text)
    """
    trigger = (trigger or "").strip()
    effect_text = (effect_text or "").strip()

    if not trigger and not effect_text:
        return "", "", "", 0, 0, ""

    combined = (trigger + " " + effect_text).strip()
    dice_trigger = infer_dice_trigger(trigger, effect_text)

    # 트리거가 인식되지 않으면, 효과는 구조화하지 않고 raw만 남긴다.
    status_code, amount = extract_status_and_amount(combined)
    if not dice_trigger or not status_code:
        return "", "", "", 0, 0, combined

    target = infer_target(combined, default="ENEMY")
    duration = infer_duration(combined, status_code, is_use_effect=False)

    return dice_trigger, target, status_code, amount, duration, combined


# -----------------------------
# 메인: normalized -> structured
# -----------------------------
def main():
    with SRC.open(encoding="utf-8", newline="") as f_in, \
         DST.open("w", encoding="utf-8", newline="") as f_out:

        reader = csv.DictReader(f_in)
        writer = csv.writer(f_out)

        writer.writerow([
            "card_id", "grade", "cost", "name",
            "dice_index", "dice_kind", "damage_type", "min", "max",
            "use_timing", "use_target", "use_status", "use_amount", "use_duration",
            "dice_trigger", "dice_target", "dice_status", "dice_amount", "dice_duration",
            "raw_use_text", "raw_dice_effect_text",
        ])

        # 카드별 사용 효과 캐시
        # card_id -> (use_timing, use_target, use_status, use_amount, use_duration, raw_use_text)
        use_cache = {}

        for row in reader:
            card_id = int(row["card_id"])

            # ----- 카드 사용 효과 (카드당 1번만 파싱해서 캐시에 저장) -----
            if card_id not in use_cache:
                use_timing, use_target, use_status, use_amount, use_duration = parse_use_effect(
                    row.get("use_type", ""), row.get("use_text", "")
                )
                raw_use_text = (
                    ((row.get("use_type", "") or "") + " " +
                     (row.get("use_text", "") or "")).strip()
                )
                use_cache[card_id] = (
                    use_timing,
                    use_target,
                    use_status,
                    use_amount,
                    use_duration,
                    raw_use_text,
                )

            use_timing, use_target, use_status, use_amount, use_duration, raw_use_text = use_cache[card_id]

            # ----- 주사위 효과 파싱 -----
            dice_trigger, dice_target, dice_status, dice_amount, dice_duration, raw_dice_text = parse_dice_effect(
                row.get("trigger", ""), row.get("effect_text", "")
            )

            writer.writerow([
                card_id,
                row["grade"],
                row["cost"],
                row["name"],
                row["dice_index"],
                row["dice_kind"],
                row["damage_type"],
                row["min"],
                row["max"],
                use_timing,
                use_target,
                use_status,
                use_amount,
                use_duration,
                dice_trigger,
                dice_target,
                dice_status,
                dice_amount,
                dice_duration,
                raw_use_text,
                raw_dice_text,
            ])

    print("완료:", DST)


if __name__ == "__main__":
    main()
