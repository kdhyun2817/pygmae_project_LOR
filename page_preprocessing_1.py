# step1_raw_to_normalized_fixed.py
import csv
from pathlib import Path

SRC = Path("라이브러리 오브 루이나_전투책장.csv")
DST = Path("combat_pages_normalized.csv")

GRADES = {"보급", "고급", "예술", "한정"}
DICE_BASE_NAMES = {"참격", "관통", "타격", "방어", "회피"}

DICE_TYPE_MAP = {
    "참격": ("ATTACK", "SLASH"),
    "관통": ("ATTACK", "PIERCE"),
    "타격": ("ATTACK", "BLUNT"),
    "방어": ("DEFENSE", ""),
    "회피": ("EVADE", ""),
}

def normalize_name(s):
    return (s or "").replace("'", "").strip()

def main():
    with open(SRC, encoding="cp949", newline="") as f_in, \
         open(DST, "w", encoding="utf-8", newline="") as f_out:

        reader = csv.reader(f_in)
        writer = csv.writer(f_out)

        header = next(reader)  # 그냥 버림

        writer.writerow([
            "card_id", "grade", "cost", "name",
            "dice_index", "dice_kind", "damage_type", "min", "max",
            "use_type", "use_text", "trigger", "effect_text"
        ])

        card_id = 0
        cur_grade = ""
        cur_cost = 0
        cur_name = ""
        cur_use_type = ""
        cur_use_text = ""
        dice_index = 0

        for row in reader:
            # row 길이 안 맞으면 보정
            while len(row) < 7:
                row.append("")

            grade = row[0].strip()
            cost = row[1].strip()
            name_or_dice = row[2].strip()
            val_min = row[3].strip()
            val_max = row[4].strip()
            special = row[5].strip()
            special_text = row[6].strip()

            # 1) 섹션 헤더 (I 뜬소문 등) → 스킵
            if grade and not cost and not name_or_dice:
                continue

            # 2) 카드 헤더 줄
            if grade in GRADES and name_or_dice:
                card_id += 1
                cur_grade = grade
                cur_cost = int(cost) if cost else 0
                cur_name = name_or_dice
                cur_use_type = special
                cur_use_text = special_text
                dice_index = 0
                continue

            # 3) 주사위 줄
            if not grade and not cost and name_or_dice:
                base = normalize_name(name_or_dice)
                if base not in DICE_BASE_NAMES:
                    continue

                dice_kind, damage_type = DICE_TYPE_MAP[base]
                try:
                    min_v = int(val_min) if val_min else 0
                    max_v = int(val_max) if val_max else 0
                except:
                    continue

                dice_index += 1
                trigger = special
                effect_text = special_text

                writer.writerow([
                    card_id, cur_grade, cur_cost, cur_name,
                    dice_index, dice_kind, damage_type, min_v, max_v,
                    cur_use_type, cur_use_text, trigger, effect_text
                ])

    print("완료:", DST)


if __name__ == "__main__":
    main()
