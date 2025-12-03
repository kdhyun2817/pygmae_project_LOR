# battle.py
import pygame
import random
import os

from unit import (
    Unit, SpeedTokenSprite, ResistLevel, DAMAGE_NAME_KO,
    WHITE, PANEL_BG, DiceKind, DamageType, StatusType, Unit, SpeedTokenSprite, MouseCursorSprite
)

from stages import STAGES

from pages_structured import load_combat_pages, CombatPage, EffectTarget, EffectTrigger

COMBAT_PAGES = load_combat_pages("combat_pages_structured.csv")

# --- 공격/수비 주사위 아이콘 텍스처 ---

_DICE_ICON_EVADE = None     # 회피
_DICE_ICON_GUARD = None     # 방어
_DICE_ICON_SLASH = None     # 참격
_DICE_ICON_BLUNT = None     # 타격
_DICE_ICON_PIERCE = None    # 관통


def _load_dice_type_icons():
    """전투 주사위(공격/수비) 아이콘을 한 번만 로드."""
    global _DICE_ICON_EVADE, _DICE_ICON_GUARD
    global _DICE_ICON_SLASH, _DICE_ICON_BLUNT, _DICE_ICON_PIERCE

    if _DICE_ICON_EVADE is not None:
        return  # 이미 로드됨

    base_dir = os.path.dirname(__file__)
    image_dir = os.path.join(base_dir, "dice")

    def _load(name: str):
        path = os.path.join(image_dir, name)
        img = pygame.image.load(path).convert_alpha()
        return img

    # 파일 이름은 네가 넣어둔 이름 그대로 사용
    _DICE_ICON_EVADE  = _load("회피 주사위.png")
    _DICE_ICON_GUARD  = _load("방어 주사위.png")
    _DICE_ICON_SLASH  = _load("참격 주사위.png")
    _DICE_ICON_BLUNT  = _load("타격 주사위.png")
    _DICE_ICON_PIERCE = _load("관통 주사위.png")


# 현재 전투에서 사용 중인 속도 토큰 스프라이트 그룹 (run_battle에서 설정)
CURRENT_SPEED_TOKEN_GROUP = None

# --- 주목(Attention) 시스템용 마지막 주사위 로그 ---
ATTENTION_LAST = None  # {"kind": ..., "unit_a": ..., ...}
RENDER_FOCUS_SCENE = None  # 주사위 연출용 화면 렌더 함수 포인터

def set_attention_last(entry: dict):
    """최근에 처리한 주사위 1개 정보를 전역으로 저장 (주목 UI에서 사용)."""
    global ATTENTION_LAST
    ATTENTION_LAST = entry

def clear_attention_last():
    """주목 단계가 끝났을 때 주사위 표시를 지우기 위한 함수."""
    global ATTENTION_LAST
    ATTENTION_LAST = None

# --- 주목(FOCUS) 정보: 감정 UI 아래에 보여줄 현재 주사위 상태 저장용 ---

CURRENT_FOCUS_INFO = None  # 나중에 run_battle / draw 루틴에서 참조할 예정


def clear_focus_info():
    """주목 정보 초기화."""
    global CURRENT_FOCUS_INFO
    CURRENT_FOCUS_INFO = None


def set_focus_info(
    mode,
    left_unit,
    right_unit,
    left_page,
    right_page,
    left_dice_list,
    right_dice_list,
    current_index,
    left_value=None,
    right_value=None,
):
    """
    감정단계 아래 UI에서 사용할 '이번에 굴린 주사위 + 남은 주사위' 정보 저장.

    - mode: "clash" / "one_sided"
    - left/right_unit: 화면 기준 왼쪽/오른쪽 유닛
    - *_page: 해당 유닛이 사용 중인 CombatPage (없으면 None)
    - *_dice_list: 이번 막에 이 책장이 가진 전체 주사위 리스트
    - current_index: 이번에 굴린 주사위 인덱스
    - left/right_value: 이번에 실제로 나온 주사위 눈 (없으면 None)
    """
    global CURRENT_FOCUS_INFO

    remaining_left = []
    remaining_right = []
    if left_dice_list is not None:
        remaining_left = left_dice_list[current_index + 1 :]
    if right_dice_list is not None:
        remaining_right = right_dice_list[current_index + 1 :]

    CURRENT_FOCUS_INFO = {
        "mode": mode,
        "left_unit": left_unit,
        "right_unit": right_unit,
        "left_page": left_page,
        "right_page": right_page,
        "left_dice_list": left_dice_list,
        "right_dice_list": right_dice_list,
        "index": current_index,
        "left_value": left_value,
        "right_value": right_value,
        "remaining_left": remaining_left,
        "remaining_right": remaining_right,
    }

def clear_all_damage_popups(units):
    """현재 전투에 참여 중인 모든 유닛의 데미지/SP 팝업을 초기화."""
    for u in units:
        if hasattr(u, "damage_popups"):
            u.damage_popups.clear()


# ---- 막(턴) 시스템 헬퍼 ----

def start_scene(scene_index, all_units):
    """
    새 막 시작 시 호출.
    - 각 유닛 빛 +1
    - 흐트러짐 회복
    - 속도 주사위 리셋
    - 감정 단계 보너스(최대 빛 / 속도 주사위 개수) 적용
    """

    # 🔹 이전 막의 주목 주사위 / 포커스 정보 초기화
    clear_attention_last()
    clear_focus_info()

    for u in all_units:
        # 감정 단계 보너스 적용
        emo = None
        try:
            emo = get_emotion_system_for(u)
        except NameError:
            emo = None

        # 🔹 유닛마다 "기본 속도 주사위 개수"를 한 번만 저장해 둔다.
        if not hasattr(u, "base_speed_dice"):
            # Unit 생성 시 설정한 speed_dice_count (기본은 1, 테스트용으로 2 등)
            u.base_speed_dice = getattr(u, "speed_dice_count", 1)
        base_speed_dice = u.base_speed_dice

        # 감정 보너스를 기본값에 더해준다.
        if emo is not None:
            u.speed_dice_count = base_speed_dice + emo.speed_dice_bonus
        else:
            u.speed_dice_count = base_speed_dice

        # (밑에 있던 최대 빛 보너스 부분은 그대로 두면 됨)
        # 최대 빛 보너스는 플레이어 측에만 적용
        if emo is not None and emo.is_player_side:
            base_max_light = 3
            u.max_light = base_max_light + emo.max_light_bonus
            if u.light > u.max_light:
                u.light = u.max_light

        # 빛 1개 획득
        if hasattr(u, "gain_light"):
            u.gain_light(1)

        # 🔹 흐트러짐 상태인 유닛은 '막 카운트'를 깎고, 0이 되면 회복
        if getattr(u, "is_staggered", False):
            # 처음 on_staggered()에서 2로 설정했으니,
            #   - SP 0 된 현재 막: 그냥 흐트러짐
            #   - 다음 막 시작: 2 -> 1 (여전히 흐트러짐, 행동 불가)
            #   - 그 다음 막 시작: 1 -> 0 → 여기서 회복
            if getattr(u, "stagger_recover_scenes", 0) > 0:
                u.stagger_recover_scenes -= 1
                if u.stagger_recover_scenes <= 0 and hasattr(u, "recover_stagger_next_scene"):
                    u.recover_stagger_next_scene()

        # 이번 막 시작 시 속도/책장 사용 횟수 초기화
        if hasattr(u, "pages_used_this_scene"):
            u.pages_used_this_scene = 0
        u.reset_speed_for_new_turn()


def end_scene(all_units):
    """
    막 종료 시 호출.
    - 화상/출혈 등 상태이상 처리 및 지속시간 감소
    - 각 유닛이 책장 1장씩 추가로 뽑음 (+ 감정 단계 보너스)
    - 감정 단계 5 이상인 아군이 직전 막에서 책장을 2장 이상 사용했다면,
      그 유닛은 다음 막 시작 전에 책장을 1장 더 드로우한다.
    """
    for u in all_units:
        if hasattr(u, "on_scene_end"):
            u.on_scene_end()

        # ✅ 덱이 있는 유닛이라면 막 종료 시 카드 1장 + 각종 보너스만큼 추가 드로우
        if hasattr(u, "draw_cards"):
            extra_draw = 0
            emo = None
            try:
                emo = get_emotion_system_for(u)
            except NameError:
                emo = None

            # 기본 감정 보너스 (아군만)
            if emo is not None and emo.is_player_side:
                extra_draw += getattr(emo, "next_scene_draw_bonus", 0)

                # 🔹 감정 5단계 이상 + 이 막에서 책장 2장 이상 사용 시 1장 추가 드로우
                used_pages = getattr(u, "pages_used_this_scene", 0)
                if getattr(emo, "level", 1) >= 5 and used_pages >= 2:
                    extra_draw += 1

            # 기본 1장 + 보너스만큼 추가 드로우
            u.draw_cards(1 + extra_draw)

        # 다음 막을 위해 사용 횟수 리셋
        if hasattr(u, "pages_used_this_scene"):
            u.pages_used_this_scene = 0




def reset_plans(all_units):
    for u in all_units:
        if hasattr(u, "planned_page"):
            u.planned_page = None
        if hasattr(u, "planned_target"):
            u.planned_target = None
        if hasattr(u, "attack_token_index"):
            u.attack_token_index = None
        if hasattr(u, "defense_token_index"):
            u.defense_token_index = None
        if hasattr(u, "token_plans"):
            u.token_plans = {}
        if hasattr(u, "initial_target"):
            u.initial_target = None
        if hasattr(u, "token_prev_targets"):
            u.token_prev_targets = {}


        # 🔹 빛 예약도 같이 초기화
        if hasattr(u, "light_reserved"):
            u.light_reserved = 0
        if hasattr(u, "light_reserved_per_token"):
            u.light_reserved_per_token = {}
        if hasattr(u, "light_blink_timer"):
            u.light_blink_timer = 0






# ----------------------------
# Dice 클래스
# ----------------------------
class Dice:
    def __init__(self, owner, kind, min_value, max_value, damage_type=None, effect=None):
        self.owner = owner
        self.kind = kind
        self.min_value = min_value
        self.max_value = max_value
        self.damage_type = damage_type
        self.value = None
        self.effect = effect  # ← 추가: 이 주사위의 EffectSpec (없으면 None)

    def roll(self):
        self.apply_status_modifiers()
        self.value = random.randint(self.min_value, self.max_value)
        return self.value

    def apply_status_modifiers(self):
        for st in self.owner.status_effects:

            # 공격 강화/약화
            if st.type == StatusType.STRENGTH and self.kind == DiceKind.ATTACK:
                self.max_value += st.stacks

            if st.type == StatusType.WEAK and self.kind == DiceKind.ATTACK:
                self.max_value -= st.stacks

            # 수비 강화/약화
            if st.type == StatusType.ENDURANCE and self.kind != DiceKind.ATTACK:
                self.max_value += st.stacks

            if st.type == StatusType.DISARM and self.kind != DiceKind.ATTACK:
                self.max_value -= st.stacks

            # 마비 (현재 간단 구현: max - 3)
            if st.type == StatusType.PARALYSIS:
                self.max_value -= 3

        # max < min 방지
        if self.max_value < self.min_value:
            self.min_value = self.max_value

def apply_effect(effect, user, target):
    """
    pages_structured.EffectSpec 을 실제 유닛(target)에 적용하는 함수.
    - user: 효과를 발생시킨 유닛(버프/디버프 소유자)
    - target: 효과를 받는 유닛
    """
    if effect is None:
        return

    st = effect.status

    # ---- 일반 상태이상 / 버프 ----
    if st in (
        StatusType.HASTE,
        StatusType.STRENGTH,
        StatusType.ENDURANCE,
        StatusType.PROTECT,
        StatusType.VULNERABLE,   # 취약
        StatusType.WEAK,      # 허약
        StatusType.BIND,      # 속박
        StatusType.PARALYSIS, # 마비
        StatusType.BLEED,     # 출혈
        StatusType.BURN,      # 화상
        StatusType.SMOKE,     # 연기
        StatusType.CHARGE,    # 충전
    ):
        target.add_status(st, effect.amount, effect.duration)

    # ---- 자원 계열 ----
    elif st == StatusType.HP_HEAL:
        target.hp = min(target.max_hp, target.hp + effect.amount)

    elif st == StatusType.LIGHT:
        target.gain_light(effect.amount)

    # 필요하면 여기서 더 특수처리 추가 가능

def apply_dice_trigger(dice: Dice, user, target, trigger_type):
    """
    Dice가 가진 effect 중, 주어진 trigger_type에 해당하면 발동시킨다.
    - user: 효과를 거는 쪽 (주사위 주인)
    - target: 기본 적 대상
    """
    effect = getattr(dice, "effect", None)
    if effect is None:
        return
    if effect.trigger != trigger_type:
        return

    # EffectTarget에 따라 실제 타겟 결정
    if effect.target == EffectTarget.SELF:
        apply_effect(effect, user, user)
    elif effect.target == EffectTarget.ENEMY:
        apply_effect(effect, user, target)
    elif effect.target == EffectTarget.ALLY_ALL:
        group = user.ally_group
        if group is not None:
            for ally in group:
                apply_effect(effect, user, ally)
    elif effect.target == EffectTarget.ENEMY_ALL:
        group = user.enemy_group
        if group is not None:
            for enemy in group:
                apply_effect(effect, user, enemy)
    else:
        # 안전하게 기본은 target에 적용
        apply_effect(effect, user, target)


def build_dice_summary_lines(page: CombatPage):
    """
    CombatPage → ["참격 1~4", "방어 2~6", "회피 1~14"] 같은 리스트로 변환
    """
    lines = []

    for dice in page.dice_list:
        # 주사위 종류
        if dice.kind == DiceKind.ATTACK:
            dtype = DAMAGE_NAME_KO.get(dice.damage_type, "")
            kind_name = dtype
        elif dice.kind == DiceKind.DEFENSE:
            kind_name = "방어"
        elif dice.kind == DiceKind.EVADE:
            kind_name = "회피"
        else:
            kind_name = "주사위"

        # 범위값
        val = f"{dice.min_value}~{dice.max_value}"

        lines.append(f"{kind_name} {val}")

    return lines

# ----------------------------
# 감정고조
# ----------------------------
class BattleEmotionSystem:
    def __init__(self, is_player_side=True):
        self.is_player_side = is_player_side   # True = 아군, False = 적군
        self.level = 1
        self.positive = 0
        self.negative = 0

        self.emotion_requirements = [3, 3, 5, 9, 15]

        # 아군만 받는 보너스
        self.max_light_bonus = 0            # 최대 빛 +1, +2 ...
        self.speed_dice_bonus = 0           # ✅ "추가 속도 코인 개수" (행동 슬롯 수 - 1)
        self.next_scene_draw_bonus = 0      # 다음 막 카드 추가 드로우 개수

        self.ego_count = 0

    def gain_coin(self, pos=0, neg=0):
        self.positive += pos
        self.negative += neg
        self.check_level_up()

    def total_coins(self):
        return self.positive + self.negative

    def check_level_up(self):
        while (
            self.level < 5
            and self.total_coins() >= self.emotion_requirements[self.level - 1]
        ):
            self.level += 1
            self.positive = 0
            self.negative = 0
            self.on_level_up()

    def on_level_up(self):
        """감정 레벨이 증가했을 때 처리"""
        self.ego_count += 1  # 공통 (아군/적 둘 다)

        if not self.is_player_side:
            return  # 적은 여기서 끝 (추가 보너스 없음)

        # 아군만 추가 효과
        self.max_light_bonus += 1

        if self.level == 4:
            # ✅ 속도 굴리기 보너스 X, "속도 코인 1개 추가" 로만 취급
            self.speed_dice_bonus += 1

        if self.level == 5:
            self.next_scene_draw_bonus += 1


def get_emotion_system_for(unit):
    """
    Unit이 아군이면 PLAYER_EMOTION, 적이면 ENEMY_EMOTION을 반환.
    """
    global PLAYER_EMOTION, ENEMY_EMOTION
    if unit.is_ally:
        return PLAYER_EMOTION
    else:
        return ENEMY_EMOTION

def award_emotion_for_hit(attacker, defender, damage_amount, is_kill=False):
    """
    공격자가 피해를 줄 때 감정 코인을 지급하는 함수.
    - 기본 규칙:
      (라오루 기준 간단화 버전)

      • 피해를 준 공격자 → 긍정 코인 +1
      • 피해를 받은 대상 → 부정 코인 +1

    - 추격치/감정 단계 시스템은 EmotionSystem.gain_coin()에서 자동 처리됨.

    - is_kill=True 이면:
      • 공격자 → 추가 긍정 코인 +2
      • 피격자 → 추가 부정 코인 +2
    """

    if damage_amount <= 0:
        return

    # unit → 감정 시스템 연결
    atk_emotion = get_emotion_system_for(attacker)
    def_emotion = get_emotion_system_for(defender)

    # 기본 코인 획득
    if atk_emotion is not None:
        atk_emotion.gain_coin(pos=1, neg=0)  # 공격자는 긍정 코인
    if def_emotion is not None:
        def_emotion.gain_coin(pos=0, neg=1)  # 피격자는 부정 코인

    # 킬 보너스
    if is_kill:
        if atk_emotion is not None:
            atk_emotion.gain_coin(pos=2, neg=0)
        if def_emotion is not None:
            def_emotion.gain_coin(pos=0, neg=2)



def create_ally_units(width, height):
    """아군 유닛 3명 생성 (오른쪽 '<' 모양)"""
    ally_group = pygame.sprite.Group()
    ally_positions = [
        (width - 260, int(height * 0.60)),
        (width - 200, int(height * 0.40)),
        (width - 200, int(height * 0.80)),
    ]

    for idx, (x, y) in enumerate(ally_positions):
        hp_res = {
            DamageType.SLASH: ResistLevel.NORMAL,
            DamageType.PIERCE: ResistLevel.NORMAL,
            DamageType.BLUNT: ResistLevel.NORMAL,
        }
        sp_res = {
            DamageType.SLASH: ResistLevel.NORMAL,
            DamageType.PIERCE: ResistLevel.NORMAL,
            DamageType.BLUNT: ResistLevel.NORMAL,
        }
        u = Unit(x, y, 2, 5, True, None, 1000, 1, hp_res, sp_res)

        u.speed_dice_count = 1

        ally_group.add(u)

    return ally_group



# battle.py 중 일부

def create_enemies_from_stage(stage_code):
    """stages.py의 STAGES에서 enemy 데이터 읽어서 생성"""
    data = STAGES[stage_code]
    enemy_group = pygame.sprite.Group()

    for spec in data["enemy_units"]:
        x, y = spec["pos"]
        u = Unit(
            x, y,
            spec["speed_min"], spec["speed_max"],
            False,                # is_ally=False
            None,                 # image_path
            spec["max_hp"],
            spec["max_sp"],
            spec["hp_res"],
            spec["sp_res"],
        )

        # 🔹 적도 기본 속도 코인 2개 사용
        u.speed_dice_count = 1

        enemy_group.add(u)

    return enemy_group



def plan_enemy_actions(enemy_group, ally_group):
    """
    이번 막에서 적들이 어떤 책장으로 누구를 공격할지 미리 정해둔다.
    - hand 에서 코스트가 현재 빛(self.light) 이하인 책장만 후보
    - 속도 토큰 개수(speed_dice_count)만큼 토큰별 계획을 세움
    - 단, "각 토큰에 배정된 책장 코스트의 총합"이 현재 빛을 넘지 않도록 제한
    - 토큰별 계획은 e.token_plans[token_idx] = {"page": CombatPage, "target": Unit}
    - 대표 planned_page/planned_target 은 첫 번째 토큰 계획으로 맞춰둔다
      (기존 해석/합공/일반 일방공 로직이 깨지지 않도록 호환용)
    """

    # 현재 살아있는 아군 목록
    alive_allies = [a for a in ally_group if not a.is_dead and not a.is_escaped]

    for e in enemy_group:
        # 기본값 초기화
        if hasattr(e, "planned_page"):
            e.planned_page = None
        if hasattr(e, "planned_target"):
            e.planned_target = None
        if hasattr(e, "attack_token_index"):
            e.attack_token_index = None
        if hasattr(e, "token_plans"):
            e.token_plans = {}
        else:
            e.token_plans = {}

        # 빛 예약/깜빡임도 초기화
        if hasattr(e, "light_reserved"):
            e.light_reserved = 0
        if hasattr(e, "light_reserved_per_token"):
            e.light_reserved_per_token = {}
        if hasattr(e, "light_blink_timer"):
            e.light_blink_timer = 0

        # 죽었거나 도망간 적은 스킵
        if getattr(e, "is_dead", False) or getattr(e, "is_escaped", False):
            continue
        if not alive_allies:
            continue

        hand = list(getattr(e, "hand", []))
        if not hand:
            continue

        # 현재 사용 가능한 빛
        current_light = int(getattr(e, "light", 0))
        if current_light <= 0:
            continue

        # 이 적이 가진 속도 토큰 개수
        speed_dice_count = int(getattr(e, "speed_dice_count", 1))
        if speed_dice_count <= 0:
            speed_dice_count = 1

        remaining_light = current_light
        token_plans = {}

        # 토큰마다 책장/타겟을 하나씩 배정 (코스트 합 제한)
        for token_idx in range(speed_dice_count):
            # 현재 남은 빛으로 쓸 수 있는 책장만 후보
            candidates = [p for p in hand if getattr(p, "cost", 0) <= remaining_light]
            if not candidates:
                break

            page = random.choice(candidates)
            target = random.choice(alive_allies)

            # 🔹 이 공격이 "타겟의 몇 번 토큰"을 치는지 결정
            def_idx = 0
            if hasattr(target, "get_speed_token_centers"):
                centers_t = target.get_speed_token_centers()
                if centers_t:
                    # 기본은 방어 토큰 인덱스(defense_token_index)를 쓰되,
                    # 범위 밖이면 0번으로 보정
                    d_idx = getattr(target, "defense_token_index", 0) or 0
                    if 0 <= d_idx < len(centers_t):
                        def_idx = d_idx
                    else:
                        def_idx = 0
                else:
                    def_idx = 0
            else:
                def_idx = 0

            token_plans[token_idx] = {
                "page": page,
                "target": target,
                "def_token_index": def_idx,  # ✅ 토큰별로 맞는 방어 토큰 인덱스 저장
            }

            # 코스트 누적
            cost = getattr(page, "cost", 0)
            remaining_light -= cost
            if remaining_light <= 0:
                break

        # 이 적이 이번 막에 아무것도 안 쓰는 경우
        if not token_plans:
            continue

        # 실제 계획 저장
        e.token_plans = token_plans

        # 기존 유닛 단위 planned_page/planned_target 을
        # "첫 번째 토큰 계획"으로 맞춰서 기존 처리와 호환
        first_idx = sorted(token_plans.keys())[0]
        first_plan = token_plans[first_idx]
        e.planned_page = first_plan["page"]
        e.planned_target = first_plan["target"]
        e.attack_token_index = first_idx

        # 🔹 빛 예약: 적도 이번 막에 쓸 책장들의 코스트 합만큼 깜빡이게
        if not hasattr(e, "light_reserved_per_token"):
            e.light_reserved_per_token = {}

        e.light_reserved_per_token = {}
        total_reserved = 0
        for idx, plan in token_plans.items():
            page = plan.get("page")
            if page is None:
                continue
            cost = getattr(page, "cost", 0)
            if cost <= 0:
                continue
            e.light_reserved_per_token[idx] = cost
            total_reserved += cost

        # 실제 예약 빛 = 토큰별 코스트 합 (현재 빛보다 더 크지는 않도록 안전 처리)
        e.light_reserved = min(total_reserved, current_light)

        # 깜빡임 길이는 코스트 합에 비례(그냥 감성용)
        if hasattr(e, "light_blink_timer"):
            e.light_blink_timer = max(getattr(e, "light_blink_timer", 0), total_reserved * 10)




def update_counter_target_on_attack(attacker, defender, atk_speed=None, def_speed=None):
    """
    공격자(attacker)의 특정 속도 토큰이 defender를 타겟팅했을 때,
    defender가 누구를 노릴지(반타겟)를 갱신하는 함수.

    🔹 규칙 (토큰 속도 반영 버전):

      - 비교에 쓰는 속도:
        * 공격자: 이번에 사용한 '공격 토큰 속도' (atk_speed 인자로 넘어옴)
        * 수비자:
            - def_speed 인자가 들어오면 그 값 사용 (클릭한 방어 코인 속도)
            - 없으면 defender.defense_speed (가장 느린 속도)

      - [우선 규칙] 처음에 노리던 애가 나를 때리면 (initial_target == attacker)
        → 속도와 무관하게 그 공격자로 다시 타겟을 되돌린다.

      - [규칙 1] 공격자가 나보다 느리거나 같으면 (atk_speed <= def_speed)
        → 타겟 변경 없이 기존 planned_target 유지 (합 뺏기 실패)

      - [규칙 2] 공격자가 나보다 빠르면 (atk_speed > def_speed)
        → defender.planned_target 을 공격자로 변경 (합 뺏기 성공)
    """
    if attacker is None or defender is None:
        return
    if attacker.is_dead or attacker.is_escaped:
        return
    if defender.is_dead or defender.is_escaped:
        return

    # 같은 팀이면 반타겟팅 안 함
    if attacker.is_ally == defender.is_ally:
        return

    # defender.initial_target 이 아직 안 잡혀 있으면,
    # 현재 planned_target을 "원래 노리던 애"로 기록해 둔다.
    if not hasattr(defender, "initial_target") or defender.initial_target is None:
        defender.initial_target = getattr(defender, "planned_target", None)

    # 공격 속도: 호출 쪽에서 넘겨준 토큰 속도가 우선
    if atk_speed is not None:
        atk_spd = atk_speed
    else:
        atk_spd = getattr(attacker, "current_speed", None)

    # 방어 속도: 인자로 넘긴 def_speed(= 클릭한 방어 코인 속도)가 우선
    if def_speed is not None:
        def_spd = def_speed
    else:
        def_spd = getattr(defender, "defense_speed", None)

    # [우선 규칙] 처음에 노리던 애가 나를 때리면 → 속도 상관없이 되돌리기
    initial = getattr(defender, "initial_target", None)
    if initial is attacker:
        defender.planned_target = attacker
        return

    # 속도 정보 없으면 안전하게 무시
    if atk_spd is None or def_spd is None:
        return

    # [규칙 1] 공격자가 나보다 느리거나 같으면 타겟 유지 (합 뺏기 실패)
    if atk_spd <= def_spd:
        return

    # [규칙 2] 공격자가 더 빠르면 그 공격자를 새 타겟으로 (합 뺏기 성공)
    defender.planned_target = attacker

    # 🔽 여기부터 추가: 방금 합을 '뺏어온' 방어 토큰의 계획도 같이 바꿔서
    #     예전 대상에게 가던 빨간 화살표를 없애준다.
    token_plans = getattr(defender, "token_plans", None)
    if isinstance(token_plans, dict) and token_plans:
        speed_values = getattr(defender, "speed_values", [])
        def_index = None

        # 1) def_speed(이번에 클릭한 방어 코인 속도)와 speed_values를 비교해서
        #    해당 속도를 가진 토큰 인덱스를 찾아본다.
        if def_spd is not None and speed_values:
            for idx, sp in enumerate(speed_values):
                if sp == def_spd:
                    def_index = idx
                    break

        # 2) 못 찾으면 기존 attack_token_index나 0번 토큰으로 fallback
        if def_index is None:
            def_index = getattr(defender, "attack_token_index", None)
        if def_index is None:
            def_index = 0

        # 이 토큰이 이제 공격에 쓰이는 토큰이다.
        defender.attack_token_index = def_index

        # 3) 해당 토큰의 token_plan 을 "attacker 쪽으로" 돌려준다.
        #    이때, 나중에 공격을 취소했을 때를 위해
        #    '원래 누구를 노리던 토큰이었는지'를 따로 저장해 둔다.
        if not hasattr(defender, "token_prev_targets"):
            defender.token_prev_targets = {}

        if def_index in token_plans:
            # 아직 이전 타겟을 기록해 두지 않았다면 한 번만 저장
            prev_target = token_plans[def_index].get("target")
            if (prev_target is not None
                    and prev_target is not attacker
                    and def_index not in defender.token_prev_targets):
                defender.token_prev_targets[def_index] = prev_target

            # 이제 이 토큰은 공격자를 노리도록 변경
            token_plans[def_index]["target"] = attacker
        else:
            # 혹시 그 토큰 인덱스로 된 계획이 없으면 하나 만들어 준다.
            page = getattr(defender, "planned_page", None)
            token_plans[def_index] = {
                "page": page,
                "target": attacker,
            }


def retarget_defender_after_cancel(defender, all_units):
    """
    어떤 유닛이 defender를 향한 공격을 취소했을 때,
    defender의 planned_target을 다시 잡아주는 함수.

    규칙:
      1) defender를 현재 '토큰 단위로' 타겟팅 중인 유닛들 중
         (살아 있고, 반대 진영이며, 속도가 정해진 유닛)
         가장 속도가 빠른 유닛이 있다면 그 유닛으로 타겟 변경
         → 합공 상태 형성 (서로를 노리게 됨)

      2) 그런 유닛이 하나도 없다면 defender.initial_target 으로 복귀
         (initial_target이 살아 있을 때만, 아니면 타겟 해제)
    """
    if defender is None:
        return
    if defender.is_dead or defender.is_escaped:
        return

    best_attacker = None
    best_speed = -1

    # 1) 아직 defender를 때리는 토큰이 남아 있는 유닛이 있는지 토큰 계획으로 확인
    for u in all_units:
        if u is defender:
            continue
        if u.is_dead or u.is_escaped:
            continue
        if u.is_ally == defender.is_ally:
            continue

        token_plans = getattr(u, "token_plans", {})
        is_attacking_defender = False

        # 이 유닛의 어떤 토큰이라도 defender를 노리고 있으면 "공격 중"으로 간주
        for plan in token_plans.values():
            if plan.get("target") is defender:
                is_attacking_defender = True
                break

        if not is_attacking_defender:
            continue

        spd = getattr(u, "current_speed", None)
        if spd is None:
            continue

        if spd > best_speed:
            best_speed = spd
            best_attacker = u

    # 2) 아직 나를 때리는 유닛이 남아 있으면 → 그 중 가장 빠른 애로 타겟 유지/변경
    if best_attacker is not None:
        defender.planned_target = best_attacker
        return

    # 3) 아무도 나를 안 때리면 → 원래 타겟(initial_target)과 토큰별 원래 타겟으로 복귀
    #    (합을 뺏었다가 공격을 전부 취소한 경우 등)
    #    update_counter_target_on_attack 에서 defender.token_prev_targets 에
    #    저장해 둔 값이 있으면 먼저 해당 토큰 계획들을 원복해 준다.
    prev_dict = getattr(defender, "token_prev_targets", None)
    if isinstance(prev_dict, dict) and prev_dict:
        token_plans = getattr(defender, "token_plans", {})
        for idx, prev_tgt in list(prev_dict.items()):
            if idx in token_plans:
                token_plans[idx]["target"] = prev_tgt
        # 한 번 되돌렸으면 초기화
        defender.token_prev_targets = {}

    # 그리고 유닛 단위 planned_target 은 initial_target 기준으로 되돌린다.
    initial = getattr(defender, "initial_target", None)
    if initial is not None and not initial.is_dead and not initial.is_escaped:
        defender.planned_target = initial
    else:
        # 원래 타겟도 없거나 죽었으면 그냥 타겟 해제
        defender.planned_target = None


def draw_unit_info_panel(surface, font, hovered_unit):
    """지금까지 쓰던 내성 패널 그대로 가져옴"""
    if hovered_unit is None:
        return

    panel_x = 620
    panel_y = 80
    panel_w = 260

    lines = []

    side = "아군" if hovered_unit.is_ally else "적"
    lines.append(f"[선택된 캐릭터] ({side})")
    lines.append(f"HP: {int(max(hovered_unit.hp, 0))}/{int(hovered_unit.max_hp)}")
    lines.append(f"SP: {int(max(hovered_unit.sp, 0))}/{int(hovered_unit.max_sp)}")

    if hovered_unit.is_dead:
        lines.append("상태: 사망")
    elif hovered_unit.is_escaped:
        lines.append("상태: 도주")
    elif hovered_unit.is_staggered:
        lines.append("상태: 흐트러짐")
    else:
        lines.append("상태: 정상")

    lines.append("")
    lines.append("[내성 정보] (HP / SP)")

    for dmg_type in DamageType:
        name = DAMAGE_NAME_KO[dmg_type]
        hp_lv = hovered_unit.hp_resist_cur.get(dmg_type, ResistLevel.NORMAL).value
        sp_lv = hovered_unit.sp_resist_cur.get(dmg_type, ResistLevel.NORMAL).value
        lines.append(f"{name}: HP {hp_lv} / SP {sp_lv}")

    line_height = 22
    padding = 16
    panel_h = len(lines) * line_height + padding * 2

    pygame.draw.rect(surface, PANEL_BG, (panel_x, panel_y, panel_w, panel_h))
    pygame.draw.rect(surface, WHITE, (panel_x, panel_y, panel_w, panel_h), 2)

    offset_y = panel_y + padding
    for text in lines:
        surf = font.render(text, True, WHITE)
        surface.blit(surf, (panel_x + 10, offset_y))
        offset_y += line_height


def get_unit_at_token(all_units, pos):
    """
    마우스 좌표 pos가 어느 유닛의 '속도 코인(토큰)' 위에 있는지 찾아서 돌려준다.
    여러 개의 속도 주사위를 가진 유닛은 토큰도 여러 개지만,
    현재는 어떤 토큰을 클릭했는지 구분하지 않고 동일한 유닛으로 취급한다.
    없으면 None.
    """
    mx, my = pos
    radius = 28
    for u in all_units:
        # Unit 쪽 헬퍼를 통해 토큰 중심 좌표들을 가져온다.
        if hasattr(u, "get_speed_token_centers"):
            centers = u.get_speed_token_centers()
        else:
            # 구버전 호환
            centers = [(u.rect.centerx, u.rect.top - 40)]

        for (cx, cy) in centers:
            dx = mx - cx
            dy = my - cy
            if dx * dx + dy * dy <= radius * radius:
                return u
    return None

def rebuild_speed_token_sprites(all_units, token_group):
    """현재 all_units의 speed_dice_count 값을 기준으로
    속도 토큰 스프라이트들을 다시 생성한다.
    - token_group은 pygame.sprite.Group 인스턴스
    - 각 유닛의 토큰 인덱스(0 ~ speed_dice_count-1)에 대해 SpeedTokenSprite를 만든다.
    """
    token_group.empty()
    for u in all_units:
        # Unit 쪽에서 speed_dice_count가 정의되어 있지 않으면 기본 1개로 취급
        n = max(1, int(getattr(u, "speed_dice_count", 1)))
        for idx in range(n):
            token_sprite = SpeedTokenSprite(u, idx)
            token_group.add(token_sprite)


def get_token_at_pos(all_units, pos):
    """
    마우스 좌표 pos가 어느 유닛의 '몇 번 속도 토큰' 위에 있는지 찾아서
    (unit, token_index)를 돌려준다.
    - all_units: 검색 범위로 삼을 유닛 그룹(ally_group, enemy_group, all_units 등)
    - pos      : (x, y) 마우스 좌표
    없으면 (None, None).
    """
    mx, my = pos

    global CURRENT_SPEED_TOKEN_GROUP
    group = CURRENT_SPEED_TOKEN_GROUP

    # 1) 현재 전투에서 토큰 스프라이트 그룹이 설정되어 있다면,
    #    그 안에서 owner가 all_units에 포함되는 스프라이트만 대상으로 충돌 판정한다.
    if group is not None:
        clicked_sprite = None
        best_dist2 = None

        for spr in group:
            owner = getattr(spr, "owner", None)
            if owner not in all_units:
                continue

            # rect 기준으로 충돌 영역 확인
            if not spr.rect.collidepoint(mx, my):
                continue

            cx, cy = spr.rect.center
            dx = mx - cx
            dy = my - cy
            d2 = dx * dx + dy * dy

            if clicked_sprite is None or d2 < best_dist2:
                clicked_sprite = spr
                best_dist2 = d2

        if clicked_sprite is not None:
            return clicked_sprite.owner, clicked_sprite.token_index

    # 2) 혹시라도 group이 아직 설정되지 않았거나,
    #    어떤 이유로 스프라이트에서 못 찾은 경우에는
    #    이전 버전과 동일한 원형 거리 기반 판정으로 폴백한다.
    radius = 28
    for u in all_units:
        if hasattr(u, "get_speed_token_centers"):
            centers = u.get_speed_token_centers()
        else:
            centers = [(u.rect.centerx, u.rect.top - 40)]

        for idx, (cx, cy) in enumerate(centers):
            dx = mx - cx
            dy = my - cy
            if dx * dx + dy * dy <= radius * radius:
                return u, idx

    return None, None





def get_hand_owner(selected_unit, selected_token_index,
                   hovered_speed_unit, hovered_speed_token_index):
    """
    중앙 아래에 어떤 '유닛/토큰'의 카드를 보여줄지 결정.
    우선순위:
      1) 선택된 유닛 + 선택된 토큰
      2) (행동 가능하면) 마우스가 올라간 속도 토큰
      3) 그 외에는 (None, None)
    """
    # 1) 명시적으로 선택된 토큰이 있으면 그걸 최우선
    if selected_unit is not None and selected_token_index is not None:
        if can_unit_roll_dice(selected_unit):
            return selected_unit, selected_token_index

    # 2) 선택된 게 없으면 hover 중인 토큰 (행동 가능할 때만)
    if hovered_speed_unit is not None and hovered_speed_token_index is not None:
        if can_unit_roll_dice(hovered_speed_unit):
            return hovered_speed_unit, hovered_speed_token_index

    return None, None




def get_hand_pages_for_owner(owner, token_index):
    """
    hand에 어떤 페이지들을 보여줄지 결정 (토큰 단위).
    - owner가 None이면: []
    - 적:
        - token_plans[token_index] 에 page가 있으면 그 카드 1장만
        - 아니면: []
    - 아군:
        - 해당 토큰에 이미 책장이 배정되어 있으면: 그 책장 1장만
        - 아니면: 현재 손패(hand)를 그대로 보여줌
          (이미 다른 토큰에 쓴 카드들은 hand에서 제거되어 있다고 가정)
    """
    if owner is None:
        return []

    # 🔹 적: 토큰별 token_plans에서 가져오기
    if not owner.is_ally:
        token_plans = getattr(owner, "token_plans", {})
        if token_index is not None and token_index in token_plans:
            page = token_plans[token_index].get("page")
            return [page] if page is not None else []
        # 적 손패 UI는 따로 안보니까 기본은 빈 리스트
        return []

    # 🔹 아군 (기존 로직 그대로)
    if token_index is None:
        return list(getattr(owner, "hand", []))

    token_plans = getattr(owner, "token_plans", {})
    plan = token_plans.get(token_index)
    if plan is not None:
        page = plan.get("page")
        return [page] if page is not None else []

    return list(getattr(owner, "hand", []))





def build_hand_card_rects(pages, screen_width, screen_height):
    """
    주어진 CombatPage 리스트(pages)를 화면 아래 중앙에 카드 형태로 배치.
    각 카드에 대해 (page, rect) 튜플 목록을 반환.
    """
    card_w = 110
    card_h = 150
    spacing = 16

    n = len(pages)
    if n == 0:
        return []

    total_w = n * card_w + (n - 1) * spacing
    start_x = (screen_width - total_w) // 2
    y = screen_height - card_h - 20

    result = []
    for i, page in enumerate(pages):
        x = start_x + i * (card_w + spacing)
        rect = pygame.Rect(x, y, card_w, card_h)
        result.append((page, rect))

    return result


def draw_hand_cards(surface, font, owner, token_index, selected_unit, mouse_pos):
    """
    화면 아래쪽에 카드(책장)를 실제 UI처럼 그린다.
    - owner: 카드를 보여줄 유닛
    - token_index: 어느 속도 토큰 기준인지 (None 가능)
    - selected_unit: 현재 선택된 유닛(카드 인터랙션 가능 대상)
    - mouse_pos: 마우스 위치 (hover 시 카드 확대)
    """
    if owner is None:
        return []

    small_font = pygame.font.SysFont("malgungothic", 18)

    width, height = surface.get_size()
    pages = get_hand_pages_for_owner(owner, token_index)
    card_infos = build_hand_card_rects(pages, width, height)

    if not card_infos:
        return card_infos  # 빈 리스트면 바로 반환

    for page, rect in card_infos:
        # 카드 배경
        draw_rect = rect.inflate(-4, -4)
        base_color = (230, 230, 230)
        border_color = (80, 80, 80)

        # 코스트가 "사용 가능한 빛"보다 크면 회색 처리
        light = getattr(owner, "light", 0)
        reserved = getattr(owner, "light_reserved", 0)
        available_light = max(0, light - reserved)

        afford = (page is not None and page.cost <= available_light)

        if not afford:
            base_color = (180, 180, 180)

        pygame.draw.rect(surface, base_color, draw_rect)
        pygame.draw.rect(surface, border_color, draw_rect, 2)

        if page is None:
            continue

        # 카드 텍스트: 맨 위 이름, 그 아래 코스트
        name_text = small_font.render(page.name, True, (0, 0, 0))
        cost_text = small_font.render(f"코스트: {page.cost}", True, (0, 0, 0))
        surface.blit(name_text, (draw_rect.x + 6, draw_rect.y + 6))
        surface.blit(cost_text, (draw_rect.x + 6, draw_rect.y + 6 + 22))

        # 🔹 여기서부터: 카드 안에 주사위 요약 텍스트 다시 표시
        #    예) "참격 3~7", "방어 2~5" 같은 형식
        dice_lines = build_dice_summary_lines(page)
        dice_y_start = draw_rect.y + 6 + 22 + 22  # 이름 + 코스트 아래부터 시작

        # 카드 높이가 150이라 너무 꽉 차지 않게 3~4줄 정도만 표시
        max_lines = 4
        for i, line in enumerate(dice_lines[:max_lines]):
            dice_text = small_font.render(line, True, (0, 0, 0))
            surface.blit(dice_text, (draw_rect.x + 6, dice_y_start + i * 20))

        # hover 시 약간 강조
        if rect.collidepoint(mouse_pos):
            pygame.draw.rect(surface, (255, 255, 0), draw_rect, 3)

    return card_infos





def draw_planned_arrows(
    surface,
    units,
    color,
    mutual_pairs=None,
    highlight_unit=None,
    highlight_token_index=None,
):
    """
    token_plans에 기록된 토큰별 공격 계획을 기준으로
    토큰 코인 → 타깃 코인 방향으로 화살표를 그린다.

    mutual_pairs: find_mutual_target_pairs_per_token 으로 구해진
      (아군, 아군 토큰 인덱스, 적, 적 토큰 인덱스) 목록.
      - 이 쌍에 해당하는 '토큰'들은
        노란 합공 화살표로 따로 그리기 때문에
        여기서는 파란/빨간 화살표를 그리지 않는다.
    """
    # 🔹 합공에 사용된 (유닛, 토큰 인덱스) 집합
    clash_tokens = set()
    if mutual_pairs is not None:
        for a, atk_idx, e, def_idx in mutual_pairs:
            clash_tokens.add((a, atk_idx))
            clash_tokens.add((e, def_idx))

    # 깜빡임 타이머 (약 0.15초 간격으로 on/off)
    tick = pygame.time.get_ticks()
    blink_on = ((tick // 150) % 2) == 0

    for u in units:
        token_plans = getattr(u, "token_plans", {})
        if not token_plans:
            # 여전히 planned_page만 쓰는 경우를 위해서
            page = getattr(u, "planned_page", None)
            target = getattr(u, "planned_target", None)
            if page is None or target is None:
                continue
            token_idx = getattr(u, "attack_token_index", 0)
            token_plans = {token_idx: {"page": page, "target": target}}

        if hasattr(u, "get_speed_token_centers"):
            centers_u = u.get_speed_token_centers()
        else:
            centers_u = [(u.rect.centerx, u.rect.top - 40)]

        for token_idx, plan in token_plans.items():
            page = plan.get("page")
            target = plan.get("target")
            if page is None or target is None:
                continue

            # 🔹 이 토큰이 합공(노란 화살표)으로 이미 표시되는 토큰이면
            #    파란/빨간 화살표는 그리지 않는다.
            if (u, token_idx) in clash_tokens:
                continue


            # 시작점: 공격 토큰 코인
            if 0 <= token_idx < len(centers_u):
                start = centers_u[token_idx]
            else:
                start = centers_u[0] if centers_u else (u.rect.centerx, u.rect.top - 40)

            # 끝점: 타깃 유닛의 방어 토큰 코인
            if hasattr(target, "get_speed_token_centers"):
                centers_t = target.get_speed_token_centers()

                # ✅ 1순위: 이 공격 계획에 저장된 def_token_index
                def_idx = plan.get("def_token_index", None)

                # ✅ 2순위: 유닛 전체의 defense_token_index (기존 방식)
                if def_idx is None:
                    def_idx = getattr(target, "defense_token_index", None)

                if def_idx is not None and 0 <= def_idx < len(centers_t):
                    end = centers_t[def_idx]
                else:
                    end = centers_t[0] if centers_t else (target.rect.centerx, target.rect.top - 40)
            else:
                end = (target.rect.centerx, target.rect.top - 40)

            # 🔹 하이라이트: "해당 유닛 + 해당 토큰"일 때만 깜빡이게
            arrow_color = color
            if (
                highlight_unit is not None
                and u is highlight_unit
                and highlight_token_index is not None
                and token_idx == highlight_token_index
            ):
                # blink_on 이 False일 땐 아예 화살표를 안 그림 → 깜빡임 효과
                if not blink_on:
                    continue
                # 켜져 있을 때는 색을 더 밝게
                r, g, b = color
                arrow_color = (
                    min(255, (r + 255) // 2),
                    min(255, (g + 255) // 2),
                    min(255, (b + 255) // 2),
                )

            draw_drag_arrow(surface, start, end, arrow_color)



def find_mutual_target_pairs(ally_group, enemy_group):
    """
    아군 A의 planned_target이 적 E이고,
    동시에 적 E의 planned_target이 A인 쌍들을 모두 찾는다.
    """
    pairs = []
    for a in ally_group:
        target = getattr(a, "planned_target", None)
        if target is None or target.is_ally:
            continue
        e = target
        if getattr(e, "planned_target", None) is a:
            pairs.append((a, e))
    return pairs

def find_mutual_target_pairs_per_token(ally_group, enemy_group):
    """
    토큰 단위로 서로를 노리는 합공 쌍들을 모두 찾는다.

    반환값: [(ally_unit, ally_token_idx, enemy_unit, enemy_token_idx), ...]
    """
    pairs = []

    for a in ally_group:
        plans_a = getattr(a, "token_plans", {})
        if not plans_a:
            continue

        for atk_idx, plan_a in plans_a.items():
            target = plan_a.get("target")
            if target is None or target.is_ally:
                continue

            e = target
            plans_e = getattr(e, "token_plans", {})
            if not plans_e:
                continue

            # 이 아군 토큰을 노리는 적 토큰을 찾는다.
            for def_idx, plan_e in plans_e.items():
                if plan_e.get("target") is a:
                    pairs.append((a, atk_idx, e, def_idx))
                    # 한 아군 토큰당 한 적 토큰만 합공 대상으로 잡고 끝낸다.
                    break

    return pairs


def draw_mutual_arrows(surface, pairs, color):
    """
    find_mutual_target_pairs_per_token 으로 구해진
    (아군, 아군 토큰 인덱스, 적, 적 토큰 인덱스) 목록을 받아서,
    각 토큰 코인 ↔ 토큰 코인 방향으로 노란 화살표를 그린다.

    pairs: [(ally_unit, ally_token_idx, enemy_unit, enemy_token_idx), ...]
    color: (R, G, B)
    """
    if not pairs:
        return

    for a, atk_idx, e, def_idx in pairs:
        if not is_unit_alive_and_present(a) or not is_unit_alive_and_present(e):
            continue

        # 아군 쪽 시작점: 해당 토큰 인덱스
        if hasattr(a, "get_speed_token_centers"):
            centers_a = a.get_speed_token_centers()
            if 0 <= atk_idx < len(centers_a):
                start_a = centers_a[atk_idx]
            else:
                start_a = centers_a[0] if centers_a else (a.rect.centerx, a.rect.top - 40)
        else:
            start_a = (a.rect.centerx, a.rect.top - 40)

        # 적 쪽 시작점: 해당 토큰 인덱스
        if hasattr(e, "get_speed_token_centers"):
            centers_e = e.get_speed_token_centers()
            if 0 <= def_idx < len(centers_e):
                start_e = centers_e[def_idx]
            else:
                start_e = centers_e[0] if centers_e else (e.rect.centerx, e.rect.top - 40)
        else:
            start_e = (e.rect.centerx, e.rect.top - 40)

        # 서로에게 가는 양방향 노란 화살표
        draw_drag_arrow(surface, start_a, start_e, color)
        draw_drag_arrow(surface, start_e, start_a, color)


def draw_drag_arrow(surface, start_pos, end_pos, color=(80, 160, 255)):
    """
    시작점 → 끝점으로 포물선 화살표를 그린다.
    (2차 베지어 곡선 사용)
    """
    sx, sy = start_pos
    ex, ey = end_pos

    # 중간 제어점: 가운데를 기준으로 위로 올려 ∩ 모양
    mx = (sx + ex) / 2
    my = (sy + ey) / 2 - 80  # -80은 곡률, 필요하면 조정

    points = []
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        # B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * mx + t ** 2 * ex
        y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * my + t ** 2 * ey
        points.append((x, y))

    # 곡선을 선분으로 그리기
    for i in range(len(points) - 1):
        pygame.draw.line(surface, color, points[i], points[i + 1], 3)

    # 화살촉
    if len(points) >= 2:
        x1, y1 = points[-2]
        x2, y2 = points[-1]
        dx = x2 - x1
        dy = y2 - y1
        length = max((dx * dx + dy * dy) ** 0.5, 1)
        ux, uy = dx / length, dy / length

        base_x = x2 - ux * 12
        base_y = y2 - uy * 12
        perp_x, perp_y = -uy, ux

        left = (base_x + perp_x * 6, base_y + perp_y * 6)
        right = (base_x - perp_x * 6, base_y - perp_y * 6)

        pygame.draw.polygon(surface, color, [(x2, y2), left, right])

def draw_focus_step(
    screen,
    font,
    all_units,
    ally_group,
    enemy_group,
    show_enemy_arrows,
    show_ally_arrows,
    show_mutual_arrows,
    dice_owner_a=None,
    value_a=None,
    dice_owner_b=None,
    value_b=None,
    delay_ms=400,
):
    """
    주사위를 한 번 굴린 직후, 화면을 다시 그려서
    - 유닛/HP/SP/속도 주사위
    - 공격/합공 화살표
    - 주사위 눈(간단히 유닛 위에 표시)
    를 보여주고 잠깐 멈춘다.
    """
    if screen is None or font is None:
        return

    # 배경
    screen.fill((30, 30, 40))

    # 1) 유닛 + HP/SP/속도 토큰
    for u in all_units:
        u.draw(screen, font)

    # 2) 화살표
    mutual_pairs = find_mutual_target_pairs_per_token(ally_group, enemy_group)

    if show_mutual_arrows:
        draw_mutual_arrows(screen, mutual_pairs, (255, 230, 80))

    if show_enemy_arrows:
        draw_planned_arrows(
            screen, enemy_group, (255, 120, 120),
            mutual_pairs=mutual_pairs,
        )

    if show_ally_arrows:
        draw_planned_arrows(
            screen, ally_group, (80, 160, 255),
            mutual_pairs=mutual_pairs,
        )

    # 3) 이번에 굴린 주사위 값 간단 표시 (유닛 머리 위)
    if dice_owner_a is not None and value_a is not None:
        text_surf = font.render(str(value_a), True, (255, 255, 255))
        rect = text_surf.get_rect()
        rect.centerx = dice_owner_a.rect.centerx
        rect.bottom = dice_owner_a.rect.top - 50
        screen.blit(text_surf, rect)

    if dice_owner_b is not None and value_b is not None:
        text_surf = font.render(str(value_b), True, (255, 255, 255))
        rect = text_surf.get_rect()
        rect.centerx = dice_owner_b.rect.centerx
        rect.bottom = dice_owner_b.rect.top - 50
        screen.blit(text_surf, rect)

    # 4) 화면 갱신 + 잠깐 딜레이
    pygame.display.flip()
    pygame.event.pump()      # 윈도우 응답 멈추지 않게
    pygame.time.delay(delay_ms)



# ----------------------------
# 합 시스템
# ----------------------------
def resolve_clash(dice_a, dice_b):
    """
    dice_a: A 유닛의 주사위
    dice_b: B 유닛의 주사위

    합공 주사위 1회 판정 (감정코인 + 상태이상 트리거 포함)

    항상 (winner, va, vb)을 반환한다.
    winner = "a" | "b" | "tie"
    va, vb = 각각 A/B가 굴린 주사위 값
    """
    ua, ub = dice_a.owner, dice_b.owner
    ka, kb = dice_a.kind, dice_b.kind

    # --- 주사위 굴림 ---
    va = dice_a.roll()
    vb = dice_b.roll()

    # --- 공통 트리거: 롤 직후 ---
    apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_ROLL)
    apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_ROLL)

    # ================================================================
    # 1) ATTACK vs ATTACK
    # ================================================================
    if ka == DiceKind.ATTACK and kb == DiceKind.ATTACK:
        if va > vb:
            ub.take_damage(va, dice_a.damage_type)
            is_kill = ub.is_dead
            award_emotion_for_hit(ua, ub, va, is_kill)

            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_HIT)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_BE_HIT)
            return "a", va, vb

        elif vb > va:
            ua.take_damage(vb, dice_b.damage_type)
            is_kill = ua.is_dead
            award_emotion_for_hit(ub, ua, vb, is_kill)

            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_HIT)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_BE_HIT)
            return "b", va, vb

        else:
            return "tie", va, vb

    # ================================================================
    # 2) ATTACK vs DEFENSE
    # ================================================================
    if ka == DiceKind.ATTACK and kb == DiceKind.DEFENSE:
        if va > vb:
            dmg = va - vb
            ub.take_damage(dmg, dice_a.damage_type)
            is_kill = ub.is_dead
            award_emotion_for_hit(ua, ub, dmg, is_kill)

            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_HIT)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_BE_HIT)
            return "a", va, vb

        elif vb > va:
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DEFEND)
            return "b", va, vb

        else:
            return "tie", va, vb

    # ================================================================
    # 3) ATTACK vs EVADE
    #    → 네가 말한 규칙:
    #       - 회피가 공격보다 크거나 같으면 피해 없음
    #       - 회피가 공격보다 클 때, 회피값만큼 SP 회복
    #       - 회피 vs 회피는 SP 회복 없음 (밑의 6번에서 처리)
    # ================================================================
    if ka == DiceKind.ATTACK and kb == DiceKind.EVADE:
        if va > vb:
            ub.take_damage(va, dice_a.damage_type)
            is_kill = ub.is_dead
            award_emotion_for_hit(ua, ub, va, is_kill)

            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_HIT)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_BE_HIT)
            return "a", va, vb
        else:
            # 회피 성공 → SP 회복
            if hasattr(ub, "recover_sp") and vb > va:
                ub.recover_sp(vb)

            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DODGE)
            return "b", va, vb

    # ================================================================
    # 4) DEFENSE vs DEFENSE
    # ================================================================
    if ka == DiceKind.DEFENSE and kb == DiceKind.DEFENSE:
        if va > vb:
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_DEFEND)
            return "a", va, vb
        elif vb > va:
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DEFEND)
            return "b", va, vb
        else:
            return "tie", va, vb

    # ================================================================
    # 5) DEFENSE vs EVADE
    # ================================================================
    if ka == DiceKind.DEFENSE and kb == DiceKind.EVADE:
        if va > vb:
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_DEFEND)
            return "a", va, vb
        elif vb > va:
            # 회피 승리 → SP 회복
            if hasattr(ub, "recover_sp"):
                ub.recover_sp(vb)

            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DODGE)
            return "b", va, vb
        else:
            return "tie", va, vb

    # ================================================================
    # 6) EVADE vs EVADE
    #    → 누가 이겨도 SP 회복 없음 (네가 말한 규칙 그대로)
    # ================================================================
    if ka == DiceKind.EVADE and kb == DiceKind.EVADE:
        if va > vb:
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_DODGE)
            return "a", va, vb
        elif vb > va:
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DODGE)
            return "b", va, vb
        else:
            return "tie", va, vb

    # ================================================================
    # 7) 혹시 위 케이스에 안 걸리는 이상 상황 (안전장치)
    # ================================================================
    return "tie", va, vb





def is_unit_alive_and_present(u):
    """데미지/행동 처리 가능한 '대상'인지 확인 (죽거나 도주했으면 False)."""
    if u is None:
        return False
    return (not u.is_dead) and (not u.is_escaped)


def can_unit_roll_dice(u):
    """
    이 유닛이 지금 '자기 주사위'를 굴릴 수 있는지 확인.
    흐트러짐/행동불가이면 False.
    """
    if not is_unit_alive_and_present(u):
        return False
    if getattr(u, "is_staggered", False):
        return False
    if getattr(u, "can_act", True) is False:
        return False
    return True


def build_dice_list_for_page(page: CombatPage, owner):
    """
    CombatPage의 dice_list를 실제 Dice 객체 리스트로 변환.
    각 Dice는 spec.effect(EffectSpec)를 들고 있게 만든다.
    """
    dice_list = []
    for spec in page.dice_list:
        d = Dice(
            owner=owner,
            kind=spec.kind,
            min_value=spec.min_value,
            max_value=spec.max_value,
            damage_type=spec.damage_type,
            effect=spec.effect,
        )
        dice_list.append(d)
    return dice_list



def resolve_one_sided_attack(dice: Dice, attacker, defender):
    """
    일방 공격 주사위 1개 처리.
    - ATTACK 주사위: val 만큼 피해 + 감정코인 + 트리거
    - DEFENSE / EVADE 주사위: 일단 피해는 없고 트리거만 (필요하면 나중에 확장)
    - 반환값: 굴린 주사위 값 val (int)
    """
    if not can_unit_roll_dice(attacker):
        return 0
    if not is_unit_alive_and_present(defender):
        return 0

    val = dice.roll()

    # 롤 트리거
    apply_dice_trigger(dice, attacker, defender, EffectTrigger.ON_ROLL)

    if dice.kind == DiceKind.ATTACK:
        dmg_type = dice.damage_type or DamageType.SLASH
        defender.take_damage(val, dmg_type)
        award_emotion_for_hit(attacker, defender, val, defender.is_dead)

        apply_dice_trigger(dice, attacker, defender, EffectTrigger.ON_HIT)
        apply_dice_trigger(dice, defender, attacker, EffectTrigger.ON_BE_HIT)

    elif dice.kind == DiceKind.DEFENSE:
        # 필요하면 ON_DEFEND 같은 트리거만; 일단 피해 없음
        apply_dice_trigger(dice, attacker, defender, EffectTrigger.ON_DEFEND)

    elif dice.kind == DiceKind.EVADE:
        # 일방 회피는 특별한 효과 없이 트리거만
        apply_dice_trigger(dice, attacker, defender, EffectTrigger.ON_DODGE)

    return val

def _get_unit_speed_for_clash(u):
    """
    이 유닛이 이번 합공에서 사용하는 '속도' 값.

    - 기본: current_speed
    - 없으면 defense_speed
    - 둘 다 없으면 0
    """
    if u is None:
        return 0
    spd = getattr(u, "current_speed", None)
    if spd is None:
        spd = getattr(u, "defense_speed", 0)
    return spd or 0


def _pick_faster_slower(a, b):
    """
    둘 중 속도가 빠른 쪽(faster), 느린 쪽(slower)을 리턴.
    LoR식 '합공 시 빠른 쪽이 주도권' 규칙을 연출에 쓰기 위한 헬퍼.
    """
    sa = _get_unit_speed_for_clash(a)
    sb = _get_unit_speed_for_clash(b)
    if sa >= sb:
        return a, b
    else:
        return b, a



def resolve_clash_between_units(unit_a, unit_b):
    """
    unit_a ↔ unit_b 가 서로를 노리는 합공 1쌍에 대한 전체 처리.
    - 각자의 planned_page를 사용.
    - 코스트(빛)를 먼저 지불.
    - 주사위를 인덱스 순서대로 1:1로 합 처리.
    - 더 많은 주사위를 가진 쪽의 남은 주사위는 일방공격.
    - 주사위 1개마다:
        - 주사위 '굴리는 연출'(랜덤 숫자 깜빡임)
        - 실제 판정(resolve_clash / resolve_one_sided_attack)
        - ATTENTION_LAST에 결과 기록
    """
    if not is_unit_alive_and_present(unit_a) or not is_unit_alive_and_present(unit_b):
        return

    page_a = getattr(unit_a, "planned_page", None)
    page_b = getattr(unit_b, "planned_page", None)
    if page_a is None or page_b is None:
        return

    # --- 코스트 지불 ---
    if not unit_a.spend_light(page_a.cost):
        print(f"[빛 부족] {unit_a.name} : {page_a.name}")
        return
    else:
        if hasattr(unit_a, "pages_used_this_scene"):
            unit_a.pages_used_this_scene += 1

    if not unit_b.spend_light(page_b.cost):
        print(f"[빛 부족] {unit_b.name} : {page_b.name}")
        return
    else:
        if hasattr(unit_b, "pages_used_this_scene"):
            unit_b.pages_used_this_scene += 1

    # --- 주사위 리스트 생성 ---
    dice_a = build_dice_list_for_page(page_a, unit_a)
    dice_b = build_dice_list_for_page(page_b, unit_b)

    len_a = len(dice_a)
    len_b = len(dice_b)
    max_len = max(len_a, len_b)

    # 연출용 훅
    set_attention_last_fn = globals().get("set_attention_last")
    clear_popups = globals().get("clear_all_damage_popups")
    render_focus = globals().get("RENDER_FOCUS_SCENE")

    for i in range(max_len):
        d_a = dice_a[i] if i < len_a else None
        d_b = dice_b[i] if i < len_b else None

        # 둘 다 이미 죽었으면 종료
        if (not is_unit_alive_and_present(unit_a)) and (not is_unit_alive_and_present(unit_b)):
            break

        can_a = (d_a is not None) and is_unit_alive_and_present(unit_a)
        can_b = (d_b is not None) and is_unit_alive_and_present(unit_b)

        # 🔹 주사위 1개 시작: 기존 데미지 팝업 정리
        if callable(clear_popups):
            try:
                clear_popups([unit_a, unit_b])
            except TypeError:
                for u in (unit_a, unit_b):
                    if hasattr(u, "damage_popups"):
                        u.damage_popups.clear()

        # 🔹 실제 판정 전에 '숫자 막 바뀌는' 굴림 연출
        if callable(render_focus) and callable(set_attention_last_fn):
            TEMP_STEPS = 8       # 몇 번 깜빡일지
            TEMP_DELAY = 80      # 한 번당 지연(ms)

            for _ in range(TEMP_STEPS):
                temp_va = None
                temp_vb = None

                if can_a and d_a is not None:
                    temp_va = random.randint(d_a.min_value, d_a.max_value)
                if can_b and d_b is not None:
                    temp_vb = random.randint(d_b.min_value, d_b.max_value)

                entry = {
                    "kind": "clash",
                    "unit_a": unit_a,
                    "unit_b": unit_b,
                    "page_a": page_a if d_a is not None else None,
                    "page_b": page_b if d_b is not None else None,
                    "dice_index": i,
                    "val_a": temp_va,
                    "val_b": temp_vb,
                    "winner": None,
                }
                set_attention_last_fn(entry)
                render_focus()
                pygame.time.delay(TEMP_DELAY)

        # 1) 합공 주사위
        if can_a and can_b:
            winner, va, vb = resolve_clash(d_a, d_b)

            # 🔹 주목 정보 기록 (최종 값)
            if callable(set_attention_last_fn):
                set_attention_last_fn({
                    "kind": "clash",
                    "unit_a": unit_a,
                    "unit_b": unit_b,
                    "page_a": page_a,
                    "page_b": page_b,
                    "dice_index": i,
                    "val_a": va,
                    "val_b": vb,
                    "winner": winner,
                })

            if callable(render_focus):
                render_focus()
                pygame.time.delay(350)

        # 2) A만 굴릴 수 있음 → A 일방 공격
        elif can_a and (not can_b):
            val = resolve_one_sided_attack(d_a, unit_a, unit_b)

            if callable(set_attention_last_fn):
                set_attention_last_fn({
                    "kind": "one_sided",
                    "unit_a": unit_a,
                    "unit_b": unit_b,
                    "page_a": page_a,
                    "page_b": None,
                    "dice_index": i,
                    "val_a": val,
                })

            if callable(render_focus):
                render_focus()
                pygame.time.delay(350)

        # 3) B만 굴릴 수 있음 → B 일방 공격
        elif can_b and (not can_a):
            val = resolve_one_sided_attack(d_b, unit_b, unit_a)

            if callable(set_attention_last_fn):
                set_attention_last_fn({
                    "kind": "one_sided",
                    "unit_a": unit_b,   # 공격자
                    "unit_b": unit_a,   # 피격자
                    "page_a": page_b,
                    "page_b": None,
                    "dice_index": i,
                    "val_a": val,
                })

            if callable(render_focus):
                render_focus()
                pygame.time.delay(350)

        # 둘 다 못 굴리면 스킵


def resolve_one_sided_sequence(attacker, defender):
    """
    공격자 attacker가 defender를 향해 planned_page로 일방 공격하는 전체 처리.
    - 코스트 지불
    - 주사위 순서대로 굴리며, ATTACK 주사위만 실제 피해를 준다.
    - 각 주사위마다:
        - 굴리는 연출(랜덤 숫자 깜빡임)
        - 실제 판정(resolve_one_sided_attack)
        - ATTENTION_LAST에 결과 기록
    """
    if not is_unit_alive_and_present(attacker):
        return
    if not is_unit_alive_and_present(defender):
        return

    page = getattr(attacker, "planned_page", None)
    if page is None:
        return

    # 코스트 지불
    if not attacker.spend_light(page.cost):
        print(f"[빛 부족] {page.name}")
        return
    else:
        if hasattr(attacker, "pages_used_this_scene"):
            attacker.pages_used_this_scene += 1

    dice_list = build_dice_list_for_page(page, attacker)

    set_attention_last_fn = globals().get("set_attention_last")
    clear_popups = globals().get("clear_all_damage_popups")
    render_focus = globals().get("RENDER_FOCUS_SCENE")

    for idx, d in enumerate(dice_list):
        if not can_unit_roll_dice(attacker):
            break
        if not is_unit_alive_and_present(defender):
            break

        # 이전 데미지 팝업 정리
        if callable(clear_popups):
            try:
                clear_popups([attacker, defender])
            except TypeError:
                for u in (attacker, defender):
                    if hasattr(u, "damage_popups"):
                        u.damage_popups.clear()

        # 🔹 실제 판정 전, 굴리는 연출
        if callable(render_focus) and callable(set_attention_last_fn):
            TEMP_STEPS = 10
            TEMP_DELAY = 1

            for _ in range(TEMP_STEPS):
                temp_val = random.randint(d.min_value, d.max_value)

                entry = {
                    "kind": "one_sided",
                    "unit_a": attacker,
                    "unit_b": defender,
                    "page_a": page,
                    "page_b": None,
                    "dice_index": idx,
                    "val_a": temp_val,
                }
                set_attention_last_fn(entry)
                render_focus()
                pygame.time.delay(TEMP_DELAY)

        # 실제 일방 공격 판정
        val = resolve_one_sided_attack(d, attacker, defender)

        if callable(set_attention_last_fn):
            set_attention_last_fn({
                "kind": "one_sided",
                "unit_a": attacker,
                "unit_b": defender,
                "page_a": page,
                "page_b": None,
                "dice_index": idx,
                "val_a": val,
            })

        if callable(render_focus):
            render_focus()
            pygame.time.delay(200)




def execute_scene_actions(all_units, ally_group, enemy_group):
    """
    (기존처럼) 이번 막에서 모든 planned_page / planned_target을
    속도 순서대로 '즉시' 처리하는 버전.
    → 디버그 / 빠른 테스트용으로 남겨둔다.
    """
    actions = build_scene_actions(all_units, ally_group, enemy_group)

    for kind, _, a, b, atk_idx, def_idx in actions:
        if not is_unit_alive_and_present(a) or not is_unit_alive_and_present(b):
            continue

        # 🔹 이번 action에 해당하는 토큰/페이지 세팅
        apply_action_token_plan(kind, a, b, atk_idx, def_idx)

        if kind == "clash":
            resolve_clash_between_units(a, b)
        elif kind == "one_sided":
            resolve_one_sided_sequence(a, b)


def build_scene_actions(all_units, ally_group, enemy_group):
    """
    이번 막에서 처리해야 할 행동(합공 / 일방 공격)을
    속도 순서대로 정렬한 리스트로 만들어 돌려준다.

    반환값:
      actions = [
        (kind, speed, attacker, defender, atk_token_idx, def_token_idx),
        ...
      ]
        kind: "clash" 또는 "one_sided"
        speed: 정렬용 속도값 (내림차순으로 처리)
        atk_token_idx: 공격자가 사용하는 속도 토큰 인덱스 (없으면 None)
        def_token_idx: 방어자가 사용하는 속도 토큰 인덱스 (없으면 None)
    """
    actions = []

    # 토큰 계획(token_plans)을 쓰는 유닛이 하나라도 있는지 확인
    any_token_plans = False
    for u in all_units:
        tps = getattr(u, "token_plans", None)
        if tps:
            any_token_plans = True
            break

    if any_token_plans:
        # 🔹 새 방식: 토큰 단위로 합공/일방을 만든다.

        # 1) 토큰 단위 합공 쌍
        mutual_pairs = find_mutual_target_pairs_per_token(ally_group, enemy_group)
        used_tokens = set()  # (unit, token_idx) 집합

        # 2) 합공 액션들
        for a, atk_idx, e, def_idx in mutual_pairs:
            if not is_unit_alive_and_present(a) or not is_unit_alive_and_present(e):
                continue

            sv_a = getattr(a, "speed_values", [])
            sv_e = getattr(e, "speed_values", [])

            if sv_a and atk_idx is not None and 0 <= atk_idx < len(sv_a):
                spd_a = sv_a[atk_idx]
            else:
                spd_a = getattr(a, "current_speed", 0) or 0

            if sv_e and def_idx is not None and 0 <= def_idx < len(sv_e):
                spd_e = sv_e[def_idx]
            else:
                spd_e = getattr(e, "current_speed", 0) or 0

            effective_speed = max(spd_a, spd_e)
            actions.append(("clash", effective_speed, a, e, atk_idx, def_idx))

            used_tokens.add((a, atk_idx))
            used_tokens.add((e, def_idx))

        # 3) 합공에 사용되지 않은 토큰들의 일방 공격
        for u in all_units:
            token_plans = getattr(u, "token_plans", None)
            if not token_plans:
                continue

            for token_idx, plan in token_plans.items():
                if (u, token_idx) in used_tokens:
                    continue

                page = plan.get("page")
                target = plan.get("target")
                if page is None or target is None:
                    continue
                if not is_unit_alive_and_present(u):
                    continue
                if not is_unit_alive_and_present(target):
                    continue

                sv_u = getattr(u, "speed_values", [])
                if sv_u and token_idx is not None and 0 <= token_idx < len(sv_u):
                    spd = sv_u[token_idx]
                else:
                    spd = getattr(u, "current_speed", 0) or 0

                def_idx = plan.get("def_token_index", None)
                actions.append(("one_sided", spd, u, target, token_idx, def_idx))

    else:
        # 🔹 옛 방식: 유닛 단위 planned_page/planned_target만 있는 경우 (호환용)
        mutual_pairs = find_mutual_target_pairs(ally_group, enemy_group)
        units_in_pairs = set()
        for a, e in mutual_pairs:
            units_in_pairs.add(a)
            units_in_pairs.add(e)

        # 2) 합공 액션들 (유닛 단위)
        for a, e in mutual_pairs:
            if not is_unit_alive_and_present(a) or not is_unit_alive_and_present(e):
                continue

            sv_a = getattr(a, "speed_values", [])
            idx_a = getattr(a, "attack_token_index", None)
            if sv_a and idx_a is not None and 0 <= idx_a < len(sv_a):
                spd_a = sv_a[idx_a]
            else:
                spd_a = getattr(a, "current_speed", 0) or 0

            sv_e = getattr(e, "speed_values", [])
            idx_e = getattr(e, "attack_token_index", None)
            if sv_e and idx_e is not None and 0 <= idx_e < len(sv_e):
                spd_e = sv_e[idx_e]
            else:
                spd_e = getattr(e, "current_speed", 0) or 0

            effective_speed = max(spd_a, spd_e)
            actions.append(("clash", effective_speed, a, e, idx_a, idx_e))

        # 3) 합공에 포함되지 않은 유닛들의 일방 공격
        for u in all_units:
            if u in units_in_pairs:
                continue

            page = getattr(u, "planned_page", None)
            target = getattr(u, "planned_target", None)
            if page is None or target is None:
                continue
            if not is_unit_alive_and_present(u):
                continue
            if not is_unit_alive_and_present(target):
                continue

            sv_u = getattr(u, "speed_values", [])
            idx_u = getattr(u, "attack_token_index", None)
            if sv_u and idx_u is not None and 0 <= idx_u < len(sv_u):
                spd = sv_u[idx_u]
            else:
                spd = getattr(u, "current_speed", 0) or 0

            actions.append(("one_sided", spd, u, target, idx_u, None))

    # 4) 속도 내림차순 정렬 (빠른 순서대로 처리)
    actions.sort(key=lambda x: x[1], reverse=True)
    return actions




def apply_action_token_plan(kind, attacker, defender, atk_token_idx, def_token_idx):
    """
    actions 항목에서 넘어온 토큰 인덱스를 기준으로
    이번 한 번의 행동에 사용할 planned_page / planned_target /
    attack_token_index / defense_token_index 를 세팅한다.
    """

    # 🔹 공격자 쪽 설정 (토큰 기반으로 page/target 선택)
    if atk_token_idx is not None and hasattr(attacker, "token_plans"):
        plan_a = attacker.token_plans.get(atk_token_idx)
        if plan_a:
            attacker.planned_page = plan_a.get("page")
            attacker.planned_target = plan_a.get("target")
            attacker.attack_token_index = atk_token_idx

    # 🔹 수비자 쪽: 방어 토큰 인덱스는 화살표/속도 비교용으로 세팅
    if def_token_idx is not None and hasattr(defender, "defense_token_index"):
        defender.defense_token_index = def_token_idx
    else:
        # defense_token_index 속성이 항상 있는 건 아니어서 getattr로 체크
        if def_token_idx is not None:
            defender.defense_token_index = def_token_idx

    # 🔹 합공인 경우, defender도 자기 토큰으로 공격을 하므로
    #     수비자 쪽도 해당 토큰 계획을 공격용으로 세팅
    if kind == "clash":
        if def_token_idx is not None and hasattr(defender, "token_plans"):
            plan_d = defender.token_plans.get(def_token_idx)
            if plan_d:
                defender.planned_page = plan_d.get("page")
                defender.planned_target = plan_d.get("target")
                defender.attack_token_index = def_token_idx




def init_decks_for_units(ally_group, enemy_group):
    """
    아군/적군 유닛에게 각각 9장의 책장을 랜덤으로 배정하고,
    시작할 때 손패 3장을 뽑는다.
    (지금은 모든 책장을 COMBAT_PAGES 전체에서 랜덤으로 뽑는 구조)
    """
    all_pages = list(COMBAT_PAGES.values())

    for u in list(ally_group) + list(enemy_group):
        if not hasattr(u, "set_deck"):
            continue

        # 같은 책장을 여러 장 가질 수 있도록 choice 9번
        deck = [random.choice(all_pages) for _ in range(9)]
        u.set_deck(deck)
        u.draw_cards(3)



def run_battle(screen, stage_code):
    """
    전투 씬 메인 루프.
    - screen은 main_play에서 만든 걸 그대로 사용
    - stage_code는 "test1" 같은 문자열
    - 전투 끝나면 "win" / "lose" / "escaped" 같은 문자열 리턴하도록 설계 가능
    """
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("malgungothic", 22)

    pygame.mouse.set_visible(False)

    w, h = screen.get_size()
    ally_group = create_ally_units(w, h)
    enemy_group = create_enemies_from_stage(stage_code)
    all_units = pygame.sprite.Group()
    all_units.add(ally_group)
    all_units.add(enemy_group)

    # 각 유닛에 아군/적군 그룹 참조를 연결하여 on_staggered 등에서 안전하게 활용할 수 있게 한다.
    for u in ally_group:
        u.ally_group = ally_group
        u.enemy_group = enemy_group
    for e in enemy_group:
        e.ally_group = enemy_group
        e.enemy_group = ally_group

    for u in all_units:
        cx, cy = u.rect.center
        u.home_pos = (float(cx), float(cy))
        u.current_pos = [float(cx), float(cy)]  # 그릴 때는 이 값을 rect에 반영할 것

    #  전투 시작 시 각 유닛에게 책장 9장 배정 + 손패 3장
    init_decks_for_units(ally_group, enemy_group)

    # 속도 토큰 스프라이트 그룹 생성 (이번 전투 동안 재사용)
    token_group = pygame.sprite.Group()
    global CURRENT_SPEED_TOKEN_GROUP
    CURRENT_SPEED_TOKEN_GROUP = token_group

    scene_index = 1
    scene_started = False
    speed_rolled = False

    # --- 스프라이트 그룹들 ---
    all_sprites = pygame.sprite.Group()
    speed_token_sprites = pygame.sprite.Group()

    # 마우스 커서 스프라이트
    mouse_cursor = MouseCursorSprite()
    all_sprites.add(mouse_cursor)

    # 각 유닛의 속도 토큰 스프라이트 생성
    for u in all_units:
        n = max(1, int(getattr(u, "speed_dice_count", 1)))
        for idx in range(n):
            token_sprite = SpeedTokenSprite(u, idx)
            speed_token_sprites.add(token_sprite)
            all_sprites.add(token_sprite)


    # 🔹 전투 연출(애니메이션) 상태
    anim_state = {
        "mode": False,
        "actions": [],
        "index": 0,
        "phase": "idle",
        "timer": 0.0,
        "current_kind": None,
        "attacker": None,
        "defender": None,
        "resolved": False,
        "return_timer": 0.0,
        "finished": False,
        "last_index": -1,
    }

    show_enemy_arrows = True  # 1번 키로 토글하는 표시 여부
    show_ally_arrows = True  # ✅ 2번 키: 아군(파란) 화살표 표시 여부
    show_mutual_arrows = True  # ✅ 3번 키: 합공격(노란) 화살표 표시 여부

    # ✅ 유저 입력/선택 상태
    selected_unit = None
    selected_card = None
    is_dragging_card = False
    temp_target_pos = None

    # 🔹 현재 선택된 아군의 몇 번째 속도 토큰을 쓰는지
    selected_token_index = None

    running = True
    result = None  # 전투 결과

    # 감정 시스템 생성
    player_emotion = BattleEmotionSystem(is_player_side=True)
    enemy_emotion = BattleEmotionSystem(is_player_side=False)

    # 전역으로도 참조 가능하게 연결
    global PLAYER_EMOTION, ENEMY_EMOTION
    PLAYER_EMOTION = player_emotion
    ENEMY_EMOTION = enemy_emotion

    # 감정 UI 색상
    EMOTION_BG = (30, 30, 50)
    EMOTION_BORDER = (200, 200, 220)
    EMOTION_TEXT = (240, 240, 255)
    EMOTION_POS_COLOR = (120, 200, 255)  # 긍정 코인 색
    EMOTION_NEG_COLOR = (255, 120, 140)  # 부정 코인 색

    def draw_emotion_ui(surface, font, player_emotion: BattleEmotionSystem, enemy_emotion: BattleEmotionSystem):
        """화면 양쪽 위에 감정단계 + 감정 코인을 표시"""

        width, height = surface.get_size()

        box_w = 180
        box_h = 80
        margin = 10

        # ----- 왼쪽 위: 적 감정 -----
        ex = margin
        ey = margin

        pygame.draw.rect(surface, EMOTION_BG, (ex, ey, box_w, box_h), border_radius=8)
        pygame.draw.rect(surface, EMOTION_BORDER, (ex, ey, box_w, box_h), 2, border_radius=8)

        enemy_title = font.render("적 감정", True, EMOTION_TEXT)
        surface.blit(enemy_title, (ex + 10, ey + 6))

        enemy_lv = font.render(f"Lv. {enemy_emotion.level}", True, EMOTION_TEXT)
        surface.blit(enemy_lv, (ex + 10, ey + 28))

        enemy_coin = font.render(f"코인 +{enemy_emotion.positive} / -{enemy_emotion.negative}", True, EMOTION_TEXT)
        surface.blit(enemy_coin, (ex + 10, ey + 50))

        # ----- 오른쪽 위: 아군 감정 -----
        px = width - box_w - margin
        py = margin

        pygame.draw.rect(surface, EMOTION_BG, (px, py, box_w, box_h), border_radius=8)
        pygame.draw.rect(surface, EMOTION_BORDER, (px, py, box_w, box_h), 2, border_radius=8)

        player_title = font.render("아군 감정", True, EMOTION_TEXT)
        surface.blit(player_title, (px + 10, py + 6))

        player_lv = font.render(f"Lv. {player_emotion.level}", True, EMOTION_TEXT)
        surface.blit(player_lv, (px + 10, py + 28))

        player_coin = font.render(f"코인 +{player_emotion.positive} / -{player_emotion.negative}", True, EMOTION_TEXT)
        surface.blit(player_coin, (px + 10, py + 50))

    def draw_attention_dice_ui(surface, font):
        """
        ATTENTION_LAST에 저장된 마지막 주사위 정보를
        각 유닛 머리 위에 LoR 비슷한 형태로 표시한다.

        - 아군: 왼쪽에 큰 육각형 주사위 + 오른쪽으로 남은 주사위들
        - 적군: 반대로 오른쪽에 큰 육각형 + 왼쪽으로 남은 주사위들
        """
        entry = ATTENTION_LAST
        if not entry:
            return

        small_font = pygame.font.SysFont("malgungothic", 16)
        dice_index = entry.get("dice_index", 0)

        # 간단 육각형 그리는 헬퍼
        # 주사위 종류에 따른 아이콘 이미지
        def get_dice_icon(spec):
            """
            combat dice spec을 받아서 알맞은 주사위 아이콘 Surface를 돌려준다.
            첫 호출 때만 파일에서 로드하고, 이후에는 캐시에 저장해서 재사용.
            """
            from unit import DiceKind, DamageType

            if not hasattr(get_dice_icon, "cache"):
                base_dir = os.path.dirname(__file__)
                image_dir = os.path.join(base_dir, "dice")

                def load(name):
                    path = os.path.join(image_dir, name)
                    return pygame.image.load(path).convert_alpha()

                # 파일 이름은 battle_UI 폴더 기준
                get_dice_icon.cache = {
                    "EVADE": load("회피 주사위.png"),
                    "GUARD": load("방어 주사위.png"),
                    "SLASH": load("참격 주사위.png"),
                    "BLUNT": load("타격 주사위.png"),
                    "PIERCE": load("관통 주사위.png"),
                }

            cache = get_dice_icon.cache

            # kind + damage_type 조합으로 아이콘 선택
            if spec.kind == DiceKind.EVADE:
                return cache["EVADE"]
            elif spec.kind == DiceKind.DEFENSE:
                return cache["GUARD"]
            elif spec.kind == DiceKind.ATTACK:
                dt = getattr(spec, "damage_type", None)
                if dt == DamageType.SLASH:
                    return cache["SLASH"]
                elif dt == DamageType.PIERCE:
                    return cache["PIERCE"]
                else:
                    # 기본은 타격으로
                    return cache["BLUNT"]
            else:
                # 혹시 모르는 경우 기본값
                return cache["SLASH"]

        # 한 유닛 머리 위 UI를 그리는 함수
        def draw_side(unit, page, rolled_value, align_left: bool):
            if unit is None or page is None or rolled_value is None:
                return

            specs = page.dice_list
            if not specs:
                return

            # 현재 / 남은 주사위
            if 0 <= dice_index < len(specs):
                cur_spec = specs[dice_index]
                remaining_specs = specs[dice_index + 1:]
            else:
                cur_spec = specs[-1]
                remaining_specs = []

            # ------------------------------
            # 1) 좌표 설정 (라오루 스타일)
            # ------------------------------
            head_x = unit.rect.centerx
            head_y = unit.rect.top

            # big dice는 캐릭터 머리 바로 위
            big_cx = head_x
            big_cy = head_y - 55

            small_r = 14
            big_r = 22

            # ------------------------------
            # 2) UI 배경 이미지 (원 + 툴팁 박스)
            # ------------------------------
            if not hasattr(draw_side, "ui_bg_loaded"):
                base_dir = os.path.dirname(__file__)
                image_dir = os.path.join(base_dir, "battle_UI")

                def _load(name: str):
                    path = os.path.join(image_dir, name)
                    return pygame.image.load(path).convert_alpha()

                # 캐릭터 머리 위 큰 원
                draw_side.circle_base = _load("UIBlackcircle.png")
                # 이름/남은 주사위용 가로 붓질 배경
                draw_side.tooltip_base = _load("UIBlacktooltipBG.png")
                draw_side.ui_bg_loaded = True

            circle_base = draw_side.circle_base
            tooltip_base = draw_side.tooltip_base

            # big dice용 원 배경 (크기는 big_r 기준으로 스케일)
            circle_d = big_r * 5
            circle_bg = pygame.transform.smoothscale(circle_base, (circle_d, circle_d))
            circle_rect = circle_bg.get_rect(center=(big_cx, big_cy))


            # ------------------------------
            # 툴팁 이미지 스케일링 (라오루 스타일 크기로 강제 조정)
            # ------------------------------
            TIP_W = 260  # 가로 크기
            TIP_H = 90  # 세로 크기
            tooltip = pygame.transform.smoothscale(tooltip_base, (TIP_W, TIP_H))
            tooltip_rect = tooltip.get_rect()

            # 원과 박스 사이 간격 (양수로!)
            offset = big_r - 240  # 필요하면 30~70 사이에서 취향대로 조절

            if align_left:
                # 왼쪽에 있는 유닛: 박스를 캐릭터의 왼쪽(바깥쪽)에 배치
                tooltip_rect.midright = (big_cx - offset, big_cy)
            else:
                # 오른쪽에 있는 유닛: 박스를 캐릭터의 오른쪽(바깥쪽)에 배치
                tooltip_rect.midleft = (big_cx + offset, big_cy)

            surface.blit(tooltip, tooltip_rect)
            surface.blit(circle_bg, circle_rect)

            surface.blit(tooltip, tooltip_rect)
            surface.blit(circle_bg, circle_rect)

            # ------------------------------
            # 3) big dice 그리기 (아이콘 + 반투명)
            # ------------------------------
            base_icon = get_dice_icon(cur_spec)

            # 기존 육각형 크기에 맞게 스케일
            big_size = (big_r * 3 + 4, big_r * 3 + 4)
            big_icon = pygame.transform.smoothscale(base_icon, big_size)

            # 현재 굴리는 주사위는 약간 반투명
            big_icon = big_icon.copy()
            big_icon.set_alpha(170)  # 0~255 중, 170 정도면 살짝 비침

            big_rect = big_icon.get_rect(center=(big_cx, big_cy))
            surface.blit(big_icon, big_rect)

            # 값 (숫자)는 그대로 중앙에 흰색으로 표시
            val_surf = font.render(str(rolled_value), True, (255, 255, 255))
            surface.blit(val_surf, val_surf.get_rect(center=(big_cx, big_cy)))

            # 현재 굴리는 주사위의 범위 텍스트를 big dice 위쪽에 표시
            rt = f"{cur_spec.min_value}~{cur_spec.max_value}"
            range_surf = small_font.render(rt, True, (255, 255, 255))
            range_rect = range_surf.get_rect(midbottom=(big_cx, big_cy - big_r + 5))
            surface.blit(range_surf, range_rect)

            # ------------------------------
            # 4) 책장 이름 (툴팁 박스 안쪽에 붙이기)
            # ------------------------------
            # 글자 크기를 작게 사용
            name_font = small_font  # 위에서 만든 16pt 폰트 재사용

            # 너무 긴 이름은 말풍선 안에 들어가게 잘라주기
            name_text = page.name

            name_surf = name_font.render(name_text, True, (255, 255, 255))
            name_rect = name_surf.get_rect()

            name_text = page.name
            name_surf = name_font.render(name_text, True, WHITE)
            name_rect = name_surf.get_rect()

            name_w = name_rect.width  # ← 글자 길이 (픽셀 단위)

            if align_left:
                # 아군: 박스 안쪽 왼쪽에서 오른쪽으로 읽히게
                name_rect.midright = (tooltip_rect.left + 80 + name_w, big_cy - 25)
            else:
                # 적군: 박스 안쪽 오른쪽에서 왼쪽으로 읽히게
                name_rect.midleft = (tooltip_rect.right - 80 - name_w, big_cy - 25)

            surface.blit(name_surf, name_rect)

            # ------------------------------
            # 5) 남은 주사위 배치 (툴팁 박스 아래쪽 라인)
            # ------------------------------
            if align_left:
                # 아군: 왼쪽에서 오른쪽으로 나열
                start_x = tooltip_rect.left + 90
                dir = 1
            else:
                # 적군: 오른쪽에서 왼쪽으로 나열
                start_x = tooltip_rect.right - 90
                dir = -1

            for i, spec in enumerate(remaining_specs):
                cx = start_x + dir * (i * (small_r * 2 + 12))
                cy = big_cy + 10

                # 아이콘 선택 후 스케일
                base_icon = get_dice_icon(spec)
                small_size = (small_r * 2 + 4, small_r * 2 + 4)
                small_icon = pygame.transform.smoothscale(base_icon, small_size)
                small_rect = small_icon.get_rect(center=(cx, cy))
                surface.blit(small_icon, small_rect)

                # 각 남은 주사위의 범위 텍스트 (아이콘 위쪽)
                rt = f"{spec.min_value}~{spec.max_value}"
                r_s = small_font.render(rt, True, (255, 255, 255))
                r_rect = r_s.get_rect(midbottom=(cx, cy - small_r + 10))
                surface.blit(r_s, r_rect)

        # ATTENTION_LAST 에서 정보 꺼내기
        unit_a = entry.get("unit_a")
        unit_b = entry.get("unit_b")
        page_a = entry.get("page_a")
        page_b = entry.get("page_b")
        val_a = entry.get("val_a")
        val_b = entry.get("val_b")

        # 두 유닛이 모두 있을 때
        if (
                unit_a is not None and page_a is not None and val_a is not None and
                unit_b is not None and page_b is not None and val_b is not None
        ):
            # 위치랑 상관없이, 아군/적군 기준으로 방향 결정
            draw_side(unit_a, page_a, val_a, align_left=unit_a.is_ally)
            draw_side(unit_b, page_b, val_b, align_left=unit_b.is_ally)

        else:
            # 한쪽만 있는 경우에도 동일하게 아군/적군 기준으로 방향 결정
            if unit_a is not None and page_a is not None and val_a is not None:
                draw_side(unit_a, page_a, val_a, align_left=unit_a.is_ally)

            if unit_b is not None and page_b is not None and val_b is not None:
                draw_side(unit_b, page_b, val_b, align_left=unit_b.is_ally)

    def draw_enemy_hover_page_ui(surface, font, hovered_speed_unit, hovered_speed_token_index):
        if hovered_speed_unit is None or hovered_speed_unit.is_ally:
            return

        enemy = hovered_speed_unit
        token_idx = hovered_speed_token_index

        token_plans = getattr(enemy, "token_plans", {})
        plan = token_plans.get(token_idx, None)
        if plan is None:
            return

        page = plan.get("page")
        if page is None:
            return

    def adjust_actions_after_stagger(actions, cur_index):
        """
        이번 막 도중에 흐트러짐이 된 아군이 있으면,
        남은 actions를 규칙에 맞게 재조정한다.

        - 흐트러진 아군이 '공격자'인 일방공격(one_sided)은 삭제
        - 흐트러진 아군이 포함된 합공(clash)은
            → 비흐트러진 쪽의 일방공격(one_sided)으로 변환
        """
        # 현재 살아 있고 전장에 남아 있는 '흐트러진 아군'들
        staggered_allies = {
            u for u in ally_group
            if getattr(u, "is_staggered", False) and is_unit_alive_and_present(u)
        }

        if not staggered_allies:
            return actions, cur_index

        new_actions = []
        for idx, act in enumerate(actions):
            kind2, spd2, ua, ub, atk2, def2 = act

            # 이미 처리했거나 지금 처리 중인 action은 그대로 둔다.
            if idx <= cur_index:
                new_actions.append(act)
                continue

            a_is_stag = ua in staggered_allies
            b_is_stag = ub in staggered_allies

            if not a_is_stag and not b_is_stag:
                # 흐트러진 아군이 관여하지 않는 action 은 그대로
                new_actions.append(act)
                continue

            # --- 여기부터는 흐트러진 아군이 관여하는 action ---

            if kind2 == "one_sided":
                # 공격자가 흐트러진 아군이면: 이 일방공은 취소 (아무것도 안 일어남)
                if a_is_stag:
                    continue
                # 방어자만 흐트러진 경우: 그대로 남겨서 맞게 둔다.
                new_actions.append(act)
                continue

            if kind2 == "clash":
                # 둘 다 흐트러졌으면 그냥 취소
                if a_is_stag and b_is_stag:
                    continue

                # 한쪽만 흐트러졌으면 나머지 쪽이 일방공격을 한다.
                if a_is_stag and not b_is_stag:
                    attacker2 = ub  # 비흐트러진 쪽
                    defender2 = ua
                    atk_token = def2  # 원래 수비 토큰을 공격 토큰으로 사용
                elif b_is_stag and not a_is_stag:
                    attacker2 = ua
                    defender2 = ub
                    atk_token = atk2
                else:
                    new_actions.append(act)
                    continue

                new_actions.append((
                    "one_sided",
                    spd2,
                    attacker2,
                    defender2,
                    atk_token,
                    None,  # 방어 토큰 인덱스는 사용하지 않음
                ))
                continue

            # 혹시 모르는 다른 kind는 그대로
            new_actions.append(act)

        # 남은 action이 하나도 없을 수도 있음
        if not new_actions:
            return [], 0

        # 현재 인덱스가 리스트 범위를 벗어나지 않도록 보정
        if cur_index >= len(new_actions):
            cur_index = len(new_actions) - 1

        return new_actions, cur_index

    # --- 전투 연출 업데이트 함수 ---
    def start_battle_animation(actions):
        """두 번째 스페이스바 입력 시, 이번 막 actions를 가지고 연출 모드를 시작."""
        anim_state["mode"] = True
        anim_state["actions"] = actions
        anim_state["index"] = 0
        anim_state["phase"] = "approach"
        anim_state["timer"] = 0.0
        anim_state["current_kind"] = None
        anim_state["attacker"] = None
        anim_state["defender"] = None
        anim_state["resolved"] = False
        anim_state["return_timer"] = 0.0
        anim_state["finished"] = False

    def update_battle_animation(dt):
        """
        연출 모드에서만 호출.
        dt: 밀리초(ms)
        한 번에 하나의 action(합공 or 일방)에 대해
        - 접근(approach)
        - 주사위/피해 처리(dice)
        - 잠시 유지(hold)
        순서로 진행하고,
        모든 action이 끝나면 전체 귀환(return) 연출을 한다.
        """

        nonlocal scene_index, scene_started, speed_rolled
        nonlocal selected_unit, selected_card, is_dragging_card

        if not anim_state["mode"]:
            return

        # 행동 리스트가 비었으면 곧바로 귀환 연출로
        if not anim_state["actions"]:
            anim_state["mode"] = False
            anim_state["finished"] = True
            return

        # 상수: 각 phase 시간 (ms)
        APPROACH_TIME = 600  # 0.6초 동안 앞으로 이동 (기존 300보다 느리게)
        DICE_TIME = 200  # 그대로
        HOLD_TIME = 400  # 그대로
        RETURN_TIME = 600  # 0.6초 동안 제자리로 복귀 (기존 400보다 느리게)

        # 아직 귀환 phase 전에, 개별 action들을 처리하는 부분
        if anim_state["phase"] in ("idle", "approach", "dice", "hold"):
            # 현재 action이 없거나 인덱스가 넘어가면 → 귀환 phase로 전환
            if anim_state["index"] >= len(anim_state["actions"]):
                anim_state["phase"] = "return"
                anim_state["return_timer"] = 0.0
                return

            kind, speed, a, b, atk_idx, def_idx = anim_state["actions"][anim_state["index"]]

            # 이번 action 정보 기록
            anim_state["current_kind"] = kind
            anim_state["attacker"] = a
            anim_state["defender"] = b
            anim_state["atk_token_index"] = atk_idx
            anim_state["def_token_index"] = def_idx

            # 👉 action 인덱스가 바뀌면, 이번 합공/일방용 시작 위치 캐시를 비운다
            if anim_state.get("last_index", -1) != anim_state["index"]:
                anim_state.pop("approach_base", None)
                anim_state["last_index"] = anim_state["index"]

            if kind == "clash":
                # 🔹 이번 합공에 쓸 토큰/페이지 세팅
                apply_action_token_plan(kind, a, b, atk_idx, def_idx)

                # 합공: 더 빠른 쪽과 느린 쪽이 서로를 향해 이동
                u1, u2 = a, b

            # 현재 action 캐시
            anim_state["current_kind"] = kind
            anim_state["attacker"] = a
            anim_state["defender"] = b

            # phase 경과 시간 증가
            anim_state["timer"] += dt

            # 1) approach: 빠른 쪽/공격자가 앞으로 이동
            if anim_state["phase"] == "approach":
                raw_t = min(anim_state["timer"] / APPROACH_TIME, 1.0)
                # 부드러운 ease-in-out (천천히 출발 → 중간에 빠름 → 끝에서 다시 천천히)
                t = raw_t * raw_t * (3 - 2 * raw_t)

                if kind == "clash":
                    # 합공: 더 빠른 쪽과 느린 쪽이 서로를 향해 이동
                    u1, u2 = a, b

                    # 각자의 공격 토큰 속도로 속도 비교
                    def get_token_speed(u):
                        sv = getattr(u, "speed_values", [])
                        idx = getattr(u, "attack_token_index", None)
                        if idx is not None and 0 <= idx < len(sv):
                            return sv[idx]
                        return getattr(u, "current_speed", 0) or 0

                    spd1 = get_token_speed(u1)
                    spd2 = get_token_speed(u2)

                    if spd1 >= spd2:
                        fast, slow = u1, u2
                    else:
                        fast, slow = u2, u1

                    # 👉 이번 action의 '시작 위치'와 '목표 위치'를 한 번만 기록해 둔다
                    if "approach_base" not in anim_state:
                        fx0 = float(fast.current_pos[0])
                        fy0 = float(fast.current_pos[1])
                        sx0 = float(slow.current_pos[0])
                        sy0 = float(slow.current_pos[1])

                        dx = sx0 - fx0
                        dy = sy0 - fy0
                        dist = (dx * dx + dy * dy) ** 0.5 or 1.0

                        # fast → slow 방향 단위벡터
                        # fast → slow 방향 단위벡터
                        dir_x = dx / dist
                        dir_y = dy / dist

                        # fast 기준으로 slow 쪽으로 70% 지점 (둘이 "부딪칠" 중심점)
                        ratio = 0.7
                        center_x = fx0 + dx * ratio
                        center_y = fy0 + dy * ratio

                        # ⚙ 중심점 기준으로
                        #   왼쪽에서 오는 유닛은 약간 왼쪽,
                        #   오른쪽에서 오는 유닛은 약간 오른쪽 위치에서 멈추게 한다.
                        OFFSET = 60.0  # 두 유닛 사이 간격의 절반 정도

                        # fast의 시작 x 좌표가 중심점 왼쪽/오른쪽인지에 따라 타겟 x 결정
                        if fx0 <= center_x:
                            fast_target_x = center_x - OFFSET
                        else:
                            fast_target_x = center_x + OFFSET

                        # slow도 동일 규칙
                        if sx0 <= center_x:
                            slow_target_x = center_x - OFFSET
                        else:
                            slow_target_x = center_x + OFFSET

                        # y는 중심 y 근처로 통일
                        fast_target_y = center_y
                        slow_target_y = center_y

                        anim_state["approach_base"] = {
                            "mode": "clash",
                            "fast": fast,
                            "slow": slow,
                            "fast_start": (fx0, fy0),
                            "slow_start": (sx0, sy0),
                            "fast_target": (fast_target_x, fast_target_y),
                            "slow_target": (slow_target_x, slow_target_y),
                        }

                    base = anim_state["approach_base"]
                    fast = base["fast"]
                    slow = base["slow"]
                    fx0, fy0 = base["fast_start"]
                    sx0, sy0 = base["slow_start"]
                    ftx, fty = base["fast_target"]
                    stx, sty = base["slow_target"]

                    # fast: 시작점 → fast_target까지 보간
                    fast.current_pos[0] = fx0 + (ftx - fx0) * t
                    fast.current_pos[1] = fy0 + (fty - fy0) * t

                    # slow: 시작점 → slow_target까지 보간
                    slow.current_pos[0] = sx0 + (stx - sx0) * t
                    slow.current_pos[1] = sy0 + (sty - sy0) * t




                else:

                    # 일방공: 공격자/피격자가 둘 다 9:1 지점 기준으로 좌우로 벌어지도록 이동
                    attacker, defender = a, b

                    # 이번 action에서 한 번만 시작/목표 위치를 계산해서 캐시에 넣어 둔다
                    if "approach_base" not in anim_state:
                        ax0 = float(attacker.current_pos[0])
                        ay0 = float(attacker.current_pos[1])
                        dx0 = float(defender.current_pos[0])
                        dy0 = float(defender.current_pos[1])

                        vx = dx0 - ax0
                        vy = dy0 - ay0
                        dist = (vx * vx + vy * vy) ** 0.5 or 1.0

                        # 공격자 → 피격자 방향으로 90% 지점 (9:1)
                        ratio = 0.9
                        center_x = ax0 + vx * ratio
                        center_y = ay0 + vy * ratio

                        # 9:1 지점을 기준으로, 한 명은 약간 왼쪽 / 한 명은 약간 오른쪽에 서게 한다
                        OFFSET = 90.0  # 두 유닛 사이 간격의 절반 (기존보다 넓게)

                        if ax0 <= center_x:
                            atk_target_x = center_x - OFFSET
                        else:
                            atk_target_x = center_x + OFFSET

                        if dx0 <= center_x:
                            def_target_x = center_x - OFFSET
                        else:
                            def_target_x = center_x + OFFSET

                        atk_target_y = center_y
                        def_target_y = center_y

                        anim_state["approach_base"] = {
                            "mode": "one_sided",
                            "attacker": attacker,
                            "defender": defender,
                            "atk_start": (ax0, ay0),
                            "def_start": (dx0, dy0),
                            "atk_target": (atk_target_x, atk_target_y),
                            "def_target": (def_target_x, def_target_y),
                        }

                    base = anim_state["approach_base"]
                    ax0, ay0 = base["atk_start"]
                    dx0, dy0 = base["def_start"]
                    atk_target_x, atk_target_y = base["atk_target"]
                    def_target_x, def_target_y = base["def_target"]

                    attacker.current_pos[0] = ax0 + (atk_target_x - ax0) * t
                    attacker.current_pos[1] = ay0 + (atk_target_y - ay0) * t

                    defender.current_pos[0] = dx0 + (def_target_x - dx0) * t
                    defender.current_pos[1] = dy0 + (def_target_y - dy0) * t

                # approach 시간이 끝나면 dice phase로
                if anim_state["timer"] >= APPROACH_TIME:
                    anim_state["phase"] = "dice"
                    anim_state["timer"] = 0.0
                    anim_state["resolved"] = False
                return

            # 2) dice phase: 실제 전투 처리 + 간단한 표시
            if anim_state["phase"] == "dice":
                if not anim_state["resolved"]:
                    # 🔹 이번 action에 해당하는 토큰/페이지 세팅
                    apply_action_token_plan(kind, a, b, atk_idx, def_idx)

                    # 🔹 여기서 실제 전투 로직 실행 (피해 계산, 감정코인 등)
                    if kind == "clash":
                        resolve_clash_between_units(a, b)
                    else:
                        resolve_one_sided_sequence(a, b)

                    anim_state["resolved"] = True

                    # 🔹 전투 처리 후, 합 도중 흐트러짐이 발생했으면 남은 action 수정
                    anim_state["actions"], anim_state["index"] = adjust_actions_after_stagger(
                        anim_state["actions"],
                        anim_state["index"],
                    )
                    # 남은 action이 없으면 바로 귀환 연출로 넘어가도록 처리
                    if not anim_state["actions"]:
                        anim_state["phase"] = "return"
                        anim_state["return_timer"] = 0.0
                        return

                if anim_state["timer"] >= DICE_TIME:
                    anim_state["phase"] = "hold"
                    anim_state["timer"] = 0.0
                return

            # 3) hold phase: 잠깐 화면에 결과를 보여주는 시간
            if anim_state["phase"] == "hold":
                if anim_state["timer"] >= HOLD_TIME:
                    # 다음 action으로 넘어감
                    anim_state["index"] += 1
                    anim_state["phase"] = "approach"
                    anim_state["timer"] = 0.0
                    anim_state["resolved"] = False

                    # 🔹 방금 액션의 주사위 표시 제거
                    clear_attention_last()
                    clear_focus_info()
                return

        # 4) 모든 action 처리 후: 전체 귀환(return) 연출
        if anim_state["phase"] == "return":
            anim_state["return_timer"] += dt
            raw_t = min(anim_state["return_timer"] / RETURN_TIME, 1.0)
            t = raw_t * raw_t * (3 - 2 * raw_t)

            for u in all_units:
                if hasattr(u, "home_pos") and hasattr(u, "current_pos"):
                    hx, hy = u.home_pos
                    cx, cy = u.current_pos
                    # cx, cy에서 hx, hy로 lerp
                    u.current_pos[0] = cx + (hx - cx) * t
                    u.current_pos[1] = cy + (hy - cy) * t

            if anim_state["return_timer"] >= RETURN_TIME:
                # 모든 유닛 정확히 제자리로 고정
                for u in all_units:
                    if hasattr(u, "home_pos"):
                        hx, hy = u.home_pos
                        u.current_pos = [hx, hy]
                        u.rect.centerx = int(hx)
                        u.rect.centery = int(hy)

                # 🔹 주사위/포커스 표시 완전히 초기화
                clear_attention_last()
                clear_focus_info()

                # 연출 모드 종료
                anim_state["mode"] = False
                anim_state["finished"] = False  # 이제 SPACE로 처리 안 할 거라 False로

                # ✅ 막 종료 처리 + 다음 막 준비까지 여기에서 바로 해버리기
                end_scene(all_units)

                scene_index += 1
                scene_started = False  # 다음 루프에서 start_scene()이 다시 호출됨
                speed_rolled = False

                selected_unit = None
                selected_card = None
                is_dragging_card = False

    def render_focus_scene():
        """
        주사위 연출용으로 화면을 간단히 다시 그리는 함수.
        - 기존 run_battle의 화면 그리기 전체를 다 복붙하지 않고,
          유닛, 화살표, 감정 UI, 주목 주사위 UI 정도만 그린다.
        """
        screen.fill((30, 30, 40))

        # 상단 정보 텍스트 (스테이지 / 막)
        info = font.render(
            f"스테이지: {stage_code} / 막: {scene_index}",
            True, WHITE
        )
        screen.blit(info, (200, 20))

        # 1) 유닛들 먼저 그리기
        for u in all_units:
            # current_pos 기준으로 rect 위치를 갱신
            if hasattr(u, "current_pos"):
                u.rect.centerx = int(u.current_pos[0])
                u.rect.centery = int(u.current_pos[1])
            u.draw(screen, font, show_speed_token=not anim_state["mode"])

        # 🔹 연출 모드일 때: 전체를 어둡게 덮고, 현재 action의 두 유닛만 위에 다시 그린다.
        if anim_state["mode"]:
            # 전체 화면을 반투명 검은색으로 덮어 디밍 효과
            overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))  # 마지막 값이 알파(0~255)
            screen.blit(overlay, (0, 0))

            a = anim_state["attacker"]
            b = anim_state["defender"]
            focus_units = []
            if a is not None:
                focus_units.append(a)
            if b is not None and b is not a:
                focus_units.append(b)

            for u in focus_units:
                if hasattr(u, "current_pos"):
                    u.rect.centerx = int(u.current_pos[0])
                    u.rect.centery = int(u.current_pos[1])
                u.draw(screen, font, show_speed_token=not anim_state["mode"])

        # 2) 화살표 (합공 + 일방)
        #   - 연출 모드가 아닐 때만 화살표를 그린다.
        mutual_pairs = []

        if not anim_state["mode"]:
            mutual_pairs = find_mutual_target_pairs_per_token(ally_group, enemy_group)

            if show_mutual_arrows:
                draw_mutual_arrows(screen, mutual_pairs, (255, 230, 80))

            if show_enemy_arrows:
                draw_planned_arrows(
                    screen,
                    enemy_group,
                    (255, 80, 80),
                    mutual_pairs=mutual_pairs,
                    highlight_unit=None,
                    highlight_token_index=None,
                )

            if show_ally_arrows:
                draw_planned_arrows(
                    screen,
                    ally_group,
                    (80, 160, 255),
                    mutual_pairs=mutual_pairs,
                    highlight_unit=None,
                    highlight_token_index=None,
                )

        # 3) 감정 UI
        draw_emotion_ui(screen, font, player_emotion, enemy_emotion)

        # 4) A-3에서 만든 주목 주사위 UI가 있다면 같이 그리기
        try:
            draw_attention_dice_ui(screen, font)
        except NameError:
            # 아직 A-3가 안 붙어 있거나 이름이 다를 수도 있어서 그냥 무시
            pass

        all_sprites.draw(screen)

        pygame.display.flip()
        # 창이 '응답 없음' 안 뜨게 이벤트 펌프
        pygame.event.pump()

    global RENDER_FOCUS_SCENE
    RENDER_FOCUS_SCENE = render_focus_scene

    # --- 주사위 1회 연출용: 캐릭터 슬라이드 이동 ---

    def play_focus_motion(
        mover,
        target,
        base_move_dist=200,   # 기본 이동 거리 (픽셀) – 너무 멀지 않게 줄였음
        step_count=12,        # 앞/뒤 각각 12스텝 → 더 부드러운 슬라이드
        step_delay_ms=30,     # 스텝 사이 딜레이 (조금 느리게)
        hold_ms=400           # 앞에 붙어서 멈춰 있는 시간
    ):
        """
        한 유닛(mover)이 target 쪽으로 '천천히' 다가갔다가 돌아오는 연출.

        - 이전 코드처럼 pygame.time.delay + render_focus_scene() 를 사용하지만
          step_count를 늘리고, 이동 거리를 조절해서
          순간이동 느낌이 아니라 슬라이드 느낌이 나도록 만든다.
        """
        if mover is None or target is None:
            return

        # 현재 위치 기준은 rect.center를 쓰되,
        # current_pos가 있다면 같이 갱신해서 나머지 코드랑 어긋나지 않게 맞춰준다.
        if hasattr(mover, "current_pos"):
            orig_x, orig_y = mover.current_pos
        else:
            orig_x, orig_y = mover.rect.center

        # 대상과의 거리/방향 계산 (타겟 바로 앞 safe_margin 만큼만 다가가기)
        tx, ty = target.rect.center
        dx = tx - orig_x
        dy = ty - orig_y
        dist = (dx ** 2 + dy ** 2) ** 0.5 or 1.0

        safe_margin = 60
        max_allowed = max(0, dist - safe_margin)
        move_dist = min(base_move_dist, max_allowed)

        # 이동 벡터
        total_dx = dx / dist * move_dist
        total_dy = dy / dist * move_dist

        step_dx = total_dx / step_count
        step_dy = total_dy / step_count

        anim_x, anim_y = float(orig_x), float(orig_y)

        # 1) 앞으로 다가가기 (step_count번에 나눠서 슬라이드)
        for _ in range(step_count):
            anim_x += step_dx
            anim_y += step_dy

            # 위치 반영
            if hasattr(mover, "current_pos"):
                mover.current_pos[0] = anim_x
                mover.current_pos[1] = anim_y
            mover.rect.center = (int(anim_x), int(anim_y))

            # 한 프레임 렌더
            render_focus_scene()
            pygame.time.delay(step_delay_ms)

        # 2) 앞에서 잠깐 멈추고, 데미지/주사위 값을 볼 시간 주기
        elapsed = 0
        while elapsed < hold_ms:
            render_focus_scene()
            pygame.time.delay(30)
            elapsed += 30

        # 3) 원위치로 슬라이드 복귀
        for _ in range(step_count):
            anim_x -= step_dx
            anim_y -= step_dy

            if hasattr(mover, "current_pos"):
                mover.current_pos[0] = anim_x
                mover.current_pos[1] = anim_y
            mover.rect.center = (int(anim_x), int(anim_y))

            render_focus_scene()
            pygame.time.delay(step_delay_ms)

        # 4) 부동소수점 오차 방지를 위해 정확히 원래 위치로 스냅
        if hasattr(mover, "current_pos"):
            mover.current_pos[0] = orig_x
            mover.current_pos[1] = orig_y
        mover.rect.center = (int(orig_x), int(orig_y))

    def play_focus_clash_animation(unit_a, unit_b,
                                   dice_index=None, va=None, vb=None, winner=None, **kwargs):
        """
        합공 1회 주사위 연출.
        일단 unit_a를 앞으로 나가는 쪽으로 사용한다.
        (나중에 '속도 빠른 쪽' 기준으로 바꾸고 싶으면 여기만 손보면 됨)
        """
        if unit_a is None or unit_b is None:
            return
        mover = unit_a
        target = unit_b
        play_focus_motion(mover, target)

    def play_focus_one_sided_animation(attacker, defender,
                                       dice_index=None, val=None, **kwargs):
        """
        일방 공격 주사위 연출.
        공격자(attacker)가 상대에게 다가갔다가 돌아오는 연출만 한다.
        """
        if attacker is None or defender is None:
            return
        play_focus_motion(attacker, defender)

    def draw_zoom_focus_pair(
            surface,
            unit_a,
            unit_b,
            zoom=1.2,
            vertical_offset=80,
            shake_intensity=0,
    ):
        """
        연출 모드일 때, 현재 주목 대상이 되는 두 유닛 주변을
        화면 전체를 확대(줌)해서 보여주는 함수.

        - unit_a, unit_b 중심의 중간 지점을 기준으로 확대하되,
          그 지점을 vertical_offset 픽셀만큼 위로 올려서 잡는다.
        - 확대 후에는 화면 가장자리에 '안 늘어난 화면'이 보이지 않도록
          offset을 화면 안으로 클램프(clamp)한다.
        - shake_intensity > 0이면 카메라가 약간 흔들리는 효과를 준다.
        """
        if unit_a is None or unit_b is None:
            return

        w, h = surface.get_size()

        # 현재 그려져 있는 화면을 그대로 복사
        base = surface.copy()

        # 확대된 크기 계산
        zoom_w = int(w * zoom)
        zoom_h = int(h * zoom)
        if zoom_w <= 0 or zoom_h <= 0:
            return

        # 부드러운 확대
        zoomed = pygame.transform.smoothscale(base, (zoom_w, zoom_h))

        # 두 유닛 중심점의 중간 지점을 "카메라 기준점"으로 사용
        cx = (unit_a.rect.centerx + unit_b.rect.centerx) / 2.0
        cy = (unit_a.rect.centery + unit_b.rect.centery) / 2.0

        # 🔹 기준점을 위로 조금 올리기 (캐릭터가 만나는 지점보다 위쪽을 더 보여주기)
        cy -= vertical_offset

        # 확대된 화면에서 이 기준점의 좌표
        zx = cx * zoom
        zy = cy * zoom

        # 이 점이 화면 정중앙에 오도록 offset 계산
        offset_x = int(w / 2 - zx)
        offset_y = int(h / 2 - zy)

        # 🔹 카메라 흔들림(Shake) 추가: offset에 랜덤으로 ±shake_intensity 픽셀 더해줌
        if shake_intensity > 0:
            offset_x += random.randint(-shake_intensity, shake_intensity)
            offset_y += random.randint(-shake_intensity, shake_intensity)

        # 🔹 offset 클램프:
        #  - 왼쪽/위쪽은 화면 밖(음수)로 나가도 되지만,
        #  - 오른쪽/아래쪽 끝이 최소한 화면을 다 덮도록 보정해준다.
        #
        #   offset_x <= 0
        #   offset_x + zoom_w >= w  =>  offset_x >= w - zoom_w
        #
        #   그래서 offset_x 는 [w - zoom_w, 0] 범위 안으로 clamp.
        #
        if zoom_w > w:
            offset_x = max(w - zoom_w, min(0, offset_x))
        else:
            # 확대 비율이 1.0 근처라 화면보다 작아질 일은 거의 없지만 안전용
            offset_x = (w - zoom_w) // 2

        if zoom_h > h:
            offset_y = max(h - zoom_h, min(0, offset_y))
        else:
            offset_y = (h - zoom_h) // 2

        # 확대된 화면을 덮어쓰기
        surface.blit(zoomed, (offset_x, offset_y))

    def draw_focus_info_ui(surface, font):
        """감정단계 아래에 현재 주목 중인 주사위 값(간단 버전)을 표시한다."""
        # CURRENT_FOCUS_INFO는 battle 모듈 전역에 정의되어 있다고 가정한다.
        try:
            info = CURRENT_FOCUS_INFO
        except NameError:
            return

        if not info:
            return

        width, height = surface.get_size()
        margin = 10
        emotion_box_h = 80
        gap = 6

        # 감정 박스 바로 아래 y 좌표
        y = margin + emotion_box_h + gap
        center_x = width // 2

        left_value = info.get("left_value")
        right_value = info.get("right_value")
        mode = info.get("mode", "")

        # 둘 다 값이 없다면 굳이 표시하지 않음
        if left_value is None and right_value is None:
            return

        if mode == "clash":
            text_str = f"주사위 값: {left_value if left_value is not None else '-'}  vs  {right_value if right_value is not None else '-'}"
        else:
            # 일방공격일 때는 공격자 값만 표시
            text_str = f"주사위 값: {left_value if left_value is not None else '-'}"

        text_surf = font.render(text_str, True, EMOTION_TEXT)
        rect = text_surf.get_rect()
        rect.centerx = center_x
        rect.top = y + 4
        surface.blit(text_surf, rect)

        # ------- UI 박스 -------
        width, height = surface.get_size()
        emotion_box_h = 80
        margin = 10
        gap = 6
        x = margin
        y = margin + emotion_box_h + gap
        box_w = 260
        box_h = 130

        pygame.draw.rect(surface, (30, 30, 50), (x, y, box_w, box_h), border_radius=8)
        pygame.draw.rect(surface, (200, 200, 220), (x, y, box_w, box_h), 2, border_radius=8)

        title = font.render("적 행동 미리보기", True, (240, 240, 255))
        surface.blit(title, (x + 8, y + 6))

        name_text = font.render(page.name, True, (240, 240, 255))
        surface.blit(name_text, (x + 8, y + 30))

        # 코스트
        small_font = pygame.font.SysFont("malgungothic", 18)
        cost_text = small_font.render(f"코스트 {page.cost}", True, (240, 240, 255))
        surface.blit(cost_text, (x + 8, y + 54))

        # ------ (새로운 부분) 굴린 값/남은 주사위 표시 ------
        ry = y + 78
        if hasattr(page, "runtime_dice_values") and page.runtime_dice_values:
            for kind, value in page.runtime_dice_values:
                txt = f"{kind.name} 주사위 결과: {value}"
                surf = small_font.render(txt, True, (240, 240, 255))
                surface.blit(surf, (x + 8, ry))
                ry += 20

        if hasattr(page, "runtime_remaining") and page.runtime_remaining:
            for dice in page.runtime_remaining:
                t = dice.kind.name
                m1, m2 = dice.min_value, dice.max_value
                txt = f"남은 {t}: {m1}~{m2}"
                surf = small_font.render(txt, True, (240, 240, 255))
                surface.blit(surf, (x + 8, ry))
                ry += 20

    global PLAY_CLASH_FOCUS_ANIM, PLAY_ONESIDED_FOCUS_ANIM
    PLAY_CLASH_FOCUS_ANIM = play_focus_clash_animation
    PLAY_ONESIDED_FOCUS_ANIM = play_focus_one_sided_animation

    while running:
        dt = clock.tick(60)

        all_sprites.update()

        # --- 막이 아직 시작되지 않았으면 여기서 시작 처리 ---
        # --- 막이 아직 시작되지 않았으면 여기서 시작 처리 ---
        if not scene_started:
            start_scene(scene_index, all_units)

            # ✅ 이번 막 시작 시, 이전 막의 공격 계획 초기화 & 속도 미정 상태로
            reset_plans(all_units)
            speed_rolled = False

            # 새 막 기준으로 속도 토큰 스프라이트 다시 구성
            rebuild_speed_token_sprites(all_units, token_group)

            scene_started = True

        # 🔹 전투 연출 모드일 땐 매 프레임 애니메이션 업데이트
        if anim_state["mode"]:
            update_battle_animation(dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                result = "quit"

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_cursor.set_pressed(True)

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                mouse_cursor.set_pressed(False)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # ESC로 전투 강제 종료 → 로비로 돌아가기
                    running = False
                    result = "retreat"

                if event.key == pygame.K_SPACE:
                    # 0. 연출 중이면 스페이스바 무시
                    if anim_state["mode"]:
                        continue

                    # 1. 아직 속도를 안 굴렸으면 → 속도 굴리기 + 적 계획
                    if not speed_rolled:
                        for u in all_units:
                            u.roll_speed()

                        plan_enemy_actions(enemy_group, ally_group)
                        speed_rolled = True
                        # 여기서 바로 return/continue 해서 "속도 굴리는 스페이스"와
                        # "전투 시작 스페이스"를 분리해도 됨
                        continue

                    # 2. 속도는 굴려졌고, 아직 연출을 시작하지 않았다면 → 이번 막 액션 리스트 만들고 연출 시작
                    if not anim_state["finished"] and not anim_state["mode"]:
                        actions = build_scene_actions(all_units, ally_group, enemy_group)
                        if actions:
                            start_battle_animation(actions)
                        else:
                            # 공격 계획이 하나도 없는 경우 → 그냥 막을 넘기고 싶으면 여기서 바로 end_scene 호출해도 됨
                            pass
                        continue

                # N 키: 테스트용으로 '막 종료 후 다음 막 시작'
                if event.key == pygame.K_n:
                    # 이번 막 종료 처리
                    end_scene(all_units)

                    # 다음 막 번호로
                    scene_index += 1
                    scene_started = False   # 다음 루프에서 start_scene()이 다시 호출됨


                # 1번 키: 적이 누구를 노리고 있는지 화살표 표시 토글
                if event.key == pygame.K_1:
                    show_enemy_arrows = not show_enemy_arrows

                # 2번 키: 아군(파란) 화살표 표시 토글
                if event.key == pygame.K_2:
                    show_ally_arrows = not show_ally_arrows

                # 3번 키: 합공격(노란) 화살표 표시 토글
                if event.key == pygame.K_3:
                    show_mutual_arrows = not show_mutual_arrows

            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos

                # ✅ 속도 굴리기 전(0막 느낌) 또는 연출 모드 중에는
                #    토큰/카드 관련 상호작용 금지
                if not speed_rolled or anim_state["mode"]:
                    continue


                # ---- 우클릭 공통: 드래그 취소 우선 ----
                if event.button == 3:
                    # 1) 카드 드래그(파란 화살표) 중이면, 드래그만 취소
                    if is_dragging_card:
                        is_dragging_card = False
                        selected_card = None
                        # 유닛/토큰 선택 상태는 유지
                        continue

                    # 2) 우클릭한 위치의 "아군 토큰"에 걸려 있는 공격 계획/빛 예약을 취소
                    clicked_unit, clicked_token_idx = get_token_at_pos(all_units, mouse_pos)
                    if clicked_unit is not None and clicked_unit.is_ally:
                        u = clicked_unit

                        # (a) 이 토큰에 공격 계획이 있다면 토큰 계획/카드/빛 예약을 되돌린다
                        plans = getattr(u, "token_plans", {})
                        plan = plans.pop(clicked_token_idx, None)

                        # 이 토큰이 원래 노리던 defender (적) 저장
                        defender = None
                        if plan is not None:
                            defender = plan.get("target")
                            page = plan.get("page")
                            # 손패에서 빼놨던 카드 되돌리기
                            if page is not None:
                                if not hasattr(u, "hand") or page not in u.hand:
                                    u.hand.append(page)
                        else:
                            page = None

                        # 예약 빛 되돌리기
                        if hasattr(u, "light_reserved_per_token"):
                            old_cost = u.light_reserved_per_token.pop(clicked_token_idx, 0)
                        else:
                            old_cost = 0
                            if page is not None:
                                old_cost = getattr(page, "cost", 0)

                        if old_cost:
                            u.light_reserved = max(
                                0,
                                getattr(u, "light_reserved", 0) - old_cost
                            )

                        # (b) 남아 있는 다른 토큰 계획이 있다면 그중 하나를 대표 planned_page로 설정
                        if getattr(u, "token_plans", {}):
                            new_idx = sorted(u.token_plans.keys())[0]
                            new_plan = u.token_plans[new_idx]
                            u.planned_page = new_plan.get("page")
                            u.planned_target = new_plan.get("target")
                            u.attack_token_index = new_idx
                        else:
                            u.planned_page = None
                            u.planned_target = None
                            u.attack_token_index = None

                        # 🔹 (c) 방금 공격 취소로 인해 defender 쪽 타겟/합공 재조정
                        if defender is not None:
                            retarget_defender_after_cancel(defender, all_units)

                        # (d) 방금 취소한 토큰을 선택 중이었다면 선택도 해제
                        if selected_unit is u and selected_token_index == clicked_token_idx:
                            selected_unit = None
                            selected_token_index = None
                    continue


                # ---- 좌클릭 ----
                if event.button == 1:
                    # 카드 드래그 중이면: 적 '토큰(속도 코인)' 클릭 시 타깃 확정
                    if is_dragging_card and selected_unit is not None and selected_card is not None:
                        if hasattr(selected_unit, "get_speed_token_centers"):
                            centers_s = selected_unit.get_speed_token_centers()
                            if selected_token_index is not None and 0 <= selected_token_index < len(centers_s):
                                start = centers_s[selected_token_index]
                            else:
                                start = centers_s[0] if centers_s else (selected_unit.rect.centerx,
                                                                        selected_unit.rect.top - 40)
                        else:
                            start = (selected_unit.rect.centerx, selected_unit.rect.top - 40)

                        draw_drag_arrow(screen, start, mouse_pos, (80, 160, 255))


                        clicked_enemy, clicked_enemy_token_idx = get_token_at_pos(enemy_group, mouse_pos)

                        if clicked_enemy is not None:
                            if clicked_enemy_token_idx is None:
                                clicked_enemy_token_idx = 0  # 혹시라도 None이면 0번 토큰으로 fallback

                            if not hasattr(selected_unit, "token_plans"):
                                selected_unit.token_plans = {}

                            # 🔹 이 공격이 "적의 몇 번 토큰"을 때리는지 같이 저장
                            selected_unit.token_plans[selected_token_index] = {
                                "page": selected_card,
                                "target": clicked_enemy,
                                "def_token_index": clicked_enemy_token_idx,  # ✅ 새로 추가된 필드
                            }

                            # 🔹 토큰별 '빛 예약' 기록 (기존 코드 그대로)
                            cost = getattr(selected_card, "cost", 0)
                            if cost > 0:
                                if not hasattr(selected_unit, "light_reserved_per_token"):
                                    selected_unit.light_reserved_per_token = {}
                                old = selected_unit.light_reserved_per_token.get(selected_token_index, 0)
                                total_reserved = getattr(selected_unit, "light_reserved", 0) - old
                                if total_reserved < 0:
                                    total_reserved = 0

                                selected_unit.light_reserved_per_token[selected_token_index] = cost
                                selected_unit.light_reserved = total_reserved + cost

                                selected_unit.light_blink_timer = max(
                                    getattr(selected_unit, "light_blink_timer", 0),
                                    cost * 10
                                )

                            # 유닛 단위 planned_page/planned_target (합공 로직 호환용)
                            selected_unit.planned_page = selected_card
                            selected_unit.planned_target = clicked_enemy

                            if selected_card in selected_unit.hand:
                                selected_unit.hand.remove(selected_card)

                            selected_unit.attack_token_index = selected_token_index


                            # 🔹 이번 공격에 사용한 토큰의 속도를 계산
                            speed_values = getattr(selected_unit, "speed_values", [])
                            if (selected_token_index is not None and
                                    0 <= selected_token_index < len(speed_values)):
                                atk_speed = speed_values[selected_token_index]
                            else:
                                atk_speed = getattr(selected_unit, "current_speed", None)

                            # 🔹 방어 쪽(적)의 "클릭한 코인 속도" 계산
                            def_speed = None
                            def_speed_values = getattr(clicked_enemy, "speed_values", [])
                            if (clicked_enemy_token_idx is not None and
                                    0 <= clicked_enemy_token_idx < len(def_speed_values)):
                                # ✅ 여기서 방금 네가 클릭한 적 코인의 속도를 직접 가져옴
                                def_speed = def_speed_values[clicked_enemy_token_idx]
                            else:
                                # 혹시 값이 없으면 원래 로직대로 전체 defense_speed 사용
                                def_speed = getattr(clicked_enemy, "defense_speed", None)

                            # 🔹 합 뺏기 / 합 맞추기 로직 적용 (이제 방어 토큰 속도까지 넘긴다)
                            update_counter_target_on_attack(
                                attacker=selected_unit,
                                defender=clicked_enemy,
                                atk_speed=atk_speed,
                                def_speed=def_speed,
                            )

                            is_dragging_card = False
                            selected_card = None
                            selected_unit = None
                            selected_token_index = None
                            continue

                    # --- 여기부터는 드래그 중이 아닐 때의 좌클릭 ---

                    # 1) 먼저, 선택된 유닛이 있고 아직 공격 계획이 없다면 → 카드 클릭 여부 확인
                    # 선택된 유닛 + 토큰이 있고,
                    # 그 토큰에 아직 공격 계획이 없는 경우에만 카드 선택 가능
                    if (selected_unit is not None and
                            selected_token_index is not None):

                        token_plans = getattr(selected_unit, "token_plans", {})
                        if token_plans.get(selected_token_index) is None:
                            owner = selected_unit  # 선택된 유닛
                            width, height = screen.get_size()
                            pages = get_hand_pages_for_owner(owner, selected_token_index)
                            card_infos = build_hand_card_rects(pages, width, height)

                            clicked_page = None
                            for page, rect in card_infos:
                                if rect.collidepoint(mouse_pos):
                                    clicked_page = page
                                    break

                            if clicked_page is not None:
                                light = getattr(selected_unit, "light", 0)
                                reserved = getattr(selected_unit, "light_reserved", 0)
                                available_light = max(0, light - reserved)

                                if clicked_page.cost <= available_light:
                                    selected_card = clicked_page
                                    is_dragging_card = True
                                # 코스트 부족이면 아무 일도 안 함

                            continue

                    # 2) 카드가 아니면 토큰 좌클릭 처리 (유닛/토큰 선택/변경)
                    clicked_unit, clicked_token_idx = get_token_at_pos(all_units, mouse_pos)

                    if clicked_unit is not None:
                        # 흐트러짐/행동 불가 유닛은 선택 불가
                        if not can_unit_roll_dice(clicked_unit):
                            continue

                        # 적은 좌클릭으로 선택 불가 (아군만 선택 가능)
                        if not clicked_unit.is_ally:
                            continue

                        # a) 아무것도 선택 안 된 상태 → 이 유닛 + 해당 토큰 선택
                        if selected_unit is None:
                            selected_unit = clicked_unit
                            selected_token_index = clicked_token_idx
                        else:
                            # b) 이미 어떤 유닛이 선택된 상태
                            if clicked_unit is not selected_unit:
                                # 다른 유닛으로 변경
                                selected_unit = clicked_unit
                            # 어떤 경우든, 이번에 클릭한 토큰 인덱스로 갱신
                            selected_token_index = clicked_token_idx

                        continue

                    # 3) 토큰도, 카드도 아니면 → 아무 동작 없음



        # 승리/패배 조건 체크 (예: 적 전멸 → win, 아군 전멸 → lose)
        if all(e.is_dead or e.is_escaped for e in enemy_group):
            result = "win"
            running = False
        elif all(a.is_dead or a.is_escaped for a in ally_group):
            result = "lose"
            running = False

        all_units.update()

        # 속도 토큰 스프라이트도 유닛 위치/속도 변화에 맞춰 갱신
        if 'token_group' in locals():
            token_group.update()

        mouse_pos = pygame.mouse.get_pos()

        hovered_unit = None
        hovered_speed_unit = None
        hovered_speed_token_index = None

        # 마우스 커서와 부딪힌 속도 토큰 전부 가져오기
        hits = pygame.sprite.spritecollide(mouse_cursor, speed_token_sprites, False)

        if hits:
            # 겹친 토큰이 여러 개면, 일단 마지막(혹은 첫 번째) 하나만 사용
            token = hits[-1]
            hovered_speed_unit = token.owner
            hovered_speed_token_index = token.token_index

        # 1) 본체 스프라이트 기준 hover (오른쪽 패널)
        for u in all_units:
            if u.rect.collidepoint(mouse_pos):
                hovered_unit = u
                break

        # 2) 속도 코인 기준 hover (카드/미리보기용)
        for u in all_units:
            # 흐트러짐/행동 불가면 토큰 hover / 손패 미리보기 대상에서 제외
            if not can_unit_roll_dice(u):
                continue

            if hasattr(u, "get_speed_token_centers"):
                centers = u.get_speed_token_centers()
            else:
                centers = [(u.rect.centerx, u.rect.top - 40)]
            for idx, (cx, cy) in enumerate(centers):
                dx = mouse_pos[0] - cx
                dy = mouse_pos[1] - cy
                radius = 28
                if dx * dx + dy * dy <= radius * radius:
                    hovered_speed_unit = u
                    hovered_speed_token_index = idx
                    break
            if hovered_speed_unit is not None:
                break

        enemy_highlight_unit = None
        enemy_highlight_token_index = None
        if hovered_speed_unit is not None and not getattr(hovered_speed_unit, "is_ally", False):
            enemy_highlight_unit = hovered_speed_unit
            enemy_highlight_token_index = hovered_speed_token_index

        # 🔹 각 유닛에 현재 hover 중인 속도 토큰 인덱스를 저장
        for u in all_units:
            if u is hovered_speed_unit:
                u.hovered_token_index = hovered_speed_token_index
            else:
                u.hovered_token_index = None

        # ===== 그리기 시작 =====
        screen.fill((30, 30, 40))

        # 상단 정보 텍스트
        info = font.render(
            f"스테이지: {stage_code} / 막: {scene_index} ",
            True, WHITE
        )

        # 1) 유닛들 먼저 그리기
        for u in all_units:
            # current_pos 기준으로 rect 위치를 갱신
            if hasattr(u, "current_pos"):
                u.rect.centerx = int(u.current_pos[0])
                u.rect.centery = int(u.current_pos[1])

            # 연출 중(anim_state["mode"] == True)에는 머리 위 토큰 숨김
            u.draw(screen, font, show_speed_token=not anim_state["mode"])

        if anim_state["mode"]:
            # 전체 화면을 반투명 검은색으로 덮어 디밍 효과
            overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))  # 마지막 값이 알파(0~255)
            screen.blit(overlay, (0, 0))

            a = anim_state["attacker"]
            b = anim_state["defender"]
            focus_units = []
            if a is not None:
                focus_units.append(a)
            if b is not None and b is not a:
                focus_units.append(b)

            # 주목 대상 유닛 두 명만 다시 그리기
            for u in focus_units:
                if hasattr(u, "current_pos"):
                    u.rect.centerx = int(u.current_pos[0])
                    u.rect.centery = int(u.current_pos[1])
                u.draw(screen, font, show_speed_token=False)

        # 2) 적/아군 계획 화살표 + 합공격(양방향) 표시
        # 합공 쌍 (아군, 적) 유닛 튜플 목록
        mutual_pairs = find_mutual_target_pairs_per_token(ally_group, enemy_group)

        # 🔹 연출 모드가 아닐 때만 화살표 표시
        if not anim_state["mode"]:
            # 노란 합공 화살표 (3번 키)
            if show_mutual_arrows:
                draw_mutual_arrows(screen, mutual_pairs, (255, 230, 80))

            # 파란/빨간 일방 화살표
            if show_enemy_arrows:
                draw_planned_arrows(
                    screen,
                    enemy_group,
                    (255, 80, 80),
                    mutual_pairs=mutual_pairs,
                    highlight_unit=enemy_highlight_unit,
                    highlight_token_index=enemy_highlight_token_index,
                )

            if show_ally_arrows:
                draw_planned_arrows(
                    screen,
                    ally_group,
                    (80, 160, 255),
                    mutual_pairs=mutual_pairs,
                    highlight_unit=None,
                )

        # 3) 카드 드래그 중이면 선택한 '속도 토큰'에서 마우스까지 임시 화살표
        if is_dragging_card and selected_unit is not None and selected_card is not None:
            if hasattr(selected_unit, "get_speed_token_centers"):
                centers_s = selected_unit.get_speed_token_centers()
                if selected_token_index is not None and 0 <= selected_token_index < len(centers_s):
                    start = centers_s[selected_token_index]
                else:
                    start = centers_s[0] if centers_s else (selected_unit.rect.centerx, selected_unit.rect.top - 40)
            else:
                start = (selected_unit.rect.centerx, selected_unit.rect.top - 40)

            draw_drag_arrow(screen, start, mouse_pos, (80, 160, 255))

        # 4) 상단 정보 텍스트
        screen.blit(info, (200, 20))

        # 5) 감정 UI
        draw_emotion_ui(screen, font, player_emotion, enemy_emotion)
        # 5-1) 적 토큰 hover 시, 사용 예정 책장 미리보기
        draw_enemy_hover_page_ui(screen, font, hovered_speed_unit, hovered_speed_token_index)
        # 5-2) 주목: 마지막으로 굴린 주사위 + 남은 주사위 표시
        draw_attention_dice_ui(screen, font)

        # 6) 오른쪽 정보 패널
        draw_unit_info_panel(screen, font, hovered_unit)

        # 7) 중앙 아래 카드 UI
        if speed_rolled:
            hand_owner, hand_token_index = get_hand_owner(
                selected_unit, selected_token_index,
                hovered_speed_unit, hovered_speed_token_index
            )
            draw_hand_cards(screen, font, hand_owner, hand_token_index, selected_unit, mouse_pos)

            # 🔹 연출 모드일 때는 현재 합/일방에 참여 중인 두 캐릭터를 중심으로 화면을 확대해서 보여준다.
            if (
                    anim_state["mode"]
                    and anim_state.get("attacker") is not None
                    and anim_state.get("defender") is not None
            ):
                draw_zoom_focus_pair(screen, anim_state["attacker"], anim_state["defender"], zoom=1.2)

        all_sprites.draw(screen)

        # ✅ 마지막에 한 번만 flip
        pygame.display.flip()

    pygame.mouse.set_visible(True)

    return result
