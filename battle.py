# battle.py
import pygame
import random

from unit import (
    Unit, ResistLevel, DAMAGE_NAME_KO,
    WHITE, PANEL_BG, DiceKind, DamageType, StatusType
)
from stages import STAGES

from pages_structured import load_combat_pages, CombatPage, EffectTarget, EffectTrigger

COMBAT_PAGES = load_combat_pages("combat_pages_structured.csv")


# ---- 막(턴) 시스템 헬퍼 ----

def start_scene(scene_index, all_units):
    """
    새 막 시작 시 호출.
    - 각 유닛 빛 +1
    - 흐트러짐 회복
    - 속도 주사위 리셋
    - 감정 단계 보너스(최대 빛 / 속도 주사위 개수) 적용
    """

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

        # 여기서 흐트러짐 회복 / 빛 +1 / 속도 리셋 등 기존 로직 계속...
        u.reset_speed_for_new_turn()
        # etc...

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

        # 속도 주사위 리셋 (다음에 SPACE로 다시 굴릴 수 있게)
        if hasattr(u, "reset_speed_for_new_turn"):
            u.reset_speed_for_new_turn()

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




def use_page(page: CombatPage, user, allies, enemies):
    # 코스트 체크
    if not user.spend_light(page.cost):
        print("빛 부족:", page.name)
        return

    # 사용 효과
    if page.use_effect:
        t = page.use_effect.target
        if t == EffectTarget.SELF:
            apply_effect(page.use_effect, user, user)
        elif t == EffectTarget.ALLY_ALL:
            for a in allies:
                apply_effect(page.use_effect, user, a)
        # 필요하면 ENEMY_ALL 등 추가

    # 주사위 생성해서 실제 공격 (간단 버전)
    dice_objs = []
    for spec in page.dice_list:
        d = Dice(
            owner=user,
            kind=spec.kind,
            min_value=spec.min_value,
            max_value=spec.max_value,
            damage_type=spec.damage_type,
        )
        # spec.effect는 나중에 on_hit / on_clash_win에서 쓰면 됨
        dice_objs.append((d, spec.effect))

    # 일단 테스트용으로 첫 적에게 그냥 공격
    target = next(e for e in enemies if not e.is_dead and not e.is_escaped)
    for d, eff in dice_objs:
        val = d.roll()
        if d.kind == DiceKind.ATTACK:
            dmg_type = d.damage_type or DamageType.SLASH
            target.take_damage(val, dmg_type)
            print(f"{page.name} 공격 주사위 {val} → 적 HP {target.hp:.1f}")
            # 추후: ON_HIT 효과 여기서 eff.trigger == EffectTrigger.ON_HIT이면 적용


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



def create_ally_units():
    """아군 유닛 3명 생성 (오른쪽 '<' 모양)"""
    ally_group = pygame.sprite.Group()
    ally_positions = [
        (700, 430),  # 가운데(전방)
        (760, 380),  # 오른쪽 위
        (760, 480),  # 오른쪽 아래
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

        u.speed_dice_count = 2

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
        u.speed_dice_count = 2

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

def get_token_at_pos(all_units, pos):
    """
    마우스 좌표 pos가 어느 유닛의 '몇 번 속도 토큰' 위에 있는지 찾아서
    (unit, token_index)를 돌려준다.
    없으면 (None, None).
    """
    mx, my = pos
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


def get_unit_at_token(all_units, pos):
    """
    기존 인터페이스 유지용: unit만 필요할 때 사용.
    """
    u, _ = get_token_at_pos(all_units, pos)
    return u



def get_hand_owner(selected_unit, selected_token_index,
                   hovered_speed_unit, hovered_speed_token_index):
    """
    중앙 아래에 어떤 '유닛/토큰'의 카드를 보여줄지 결정.
    우선순위:
      1) 선택된 유닛 + 선택된 토큰
      2) 아니면, 마우스가 올라간 속도 토큰
      3) 그 외에는 (None, None)
    """
    # 1) 명시적으로 선택된 토큰이 있으면 그걸 최우선
    if selected_unit is not None and selected_token_index is not None:
        return selected_unit, selected_token_index

    # 2) 선택된 게 없으면 hover 중인 토큰
    if hovered_speed_unit is not None and hovered_speed_token_index is not None:
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

    mutual_pairs: find_mutual_target_pairs 로 구해진 (아군, 적) 유닛 쌍 목록.
      - 이 쌍에 해당하는 (공격 유닛, 타깃 유닛) 조합은
        노란 합공 화살표로 따로 그리게 되므로,
        여기서는 파란/빨간 화살표를 중복해서 그리지 않는다.
      - 같은 유닛의 다른 토큰이 다른 적을 때리는 건 그대로 일방 화살표 유지.

    highlight_unit, highlight_token_index:
      - 특정 유닛(u)의 특정 토큰(token_idx)이 하이라이트 대상이면
        그 토큰에서 나가는 화살표만 깜빡이게 한다.
    """
    pair_set = set()
    if mutual_pairs is not None:
        for a, e in mutual_pairs:
            pair_set.add((a, e))
            pair_set.add((e, a))  # 양방향 모두 제외

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

            # 🔹 이 (공격 유닛, 타깃 유닛) 조합이 합공 쌍이면
            #    → 노란 합공 화살표만 보여주고, 파란/빨간 화살표는 전부 숨긴다.
            if (u, target) in pair_set:
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


def draw_mutual_arrows(surface, pairs, color):
    """
    find_mutual_target_pairs 로 구해진 (아군, 적) 유닛 쌍 목록을 받아서,
    각 유닛의 '공격 토큰 코인' ↔ '공격 토큰 코인' 방향으로 노란 화살표를 그린다.

    pairs: [(ally_unit, enemy_unit), ...]
    color: (R, G, B)
    """
    if not pairs:
        return

    for a, e in pairs:
        if not is_unit_alive_and_present(a) or not is_unit_alive_and_present(e):
            continue

        # 아군 A 시작점: 실제로 E를 노리는 토큰 인덱스를 우선 사용
        atk_idx_a = None
        token_plans_a = getattr(a, "token_plans", {})
        for t_idx, plan in token_plans_a.items():
            if plan.get("target") is e:
                atk_idx_a = t_idx
                break

        if hasattr(a, "get_speed_token_centers"):
            centers_a = a.get_speed_token_centers()
            # token_plans 에서 못 찾았으면 대표 attack_token_index 또는 0번 토큰 사용
            if atk_idx_a is None:
                atk_idx_a = getattr(a, "attack_token_index", 0) or 0
            if 0 <= atk_idx_a < len(centers_a):
                start_a = centers_a[atk_idx_a]
            else:
                start_a = centers_a[0] if centers_a else (a.rect.centerx, a.rect.top - 40)
        else:
            start_a = (a.rect.centerx, a.rect.top - 40)

        # 적 E 시작점: 실제로 A를 노리는 토큰 인덱스를 우선 사용
        atk_idx_e = None
        token_plans_e = getattr(e, "token_plans", {})
        for t_idx, plan in token_plans_e.items():
            if plan.get("target") is a:
                atk_idx_e = t_idx
                break

        if hasattr(e, "get_speed_token_centers"):
            centers_e = e.get_speed_token_centers()
            if atk_idx_e is None:
                atk_idx_e = getattr(e, "attack_token_index", 0) or 0
            if 0 <= atk_idx_e < len(centers_e):
                start_e = centers_e[atk_idx_e]
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



# ----------------------------
# 합 시스템
# ----------------------------
def resolve_clash(dice_a, dice_b):
    """
    dice_a: A 유닛의 주사위
    dice_b: B 유닛의 주사위

    합공 주사위 1회 판정 (감정코인 + 상태이상 트리거 포함)
    """

    ua, ub = dice_a.owner, dice_b.owner
    ka, kb = dice_a.kind, dice_b.kind

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
            return "a"

        elif vb > va:
            ua.take_damage(vb, dice_b.damage_type)
            is_kill = ua.is_dead
            award_emotion_for_hit(ub, ua, vb, is_kill)

            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_HIT)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_BE_HIT)
            return "b"

        else:
            return "tie"

    # ================================================================
    # 2) ATTACK vs DEFENSE
    # ================================================================
    if ka == DiceKind.ATTACK and kb == DiceKind.DEFENSE:
        if va > vb:
            # 공격이 방어를 뚫고 직접 피해
            ub.take_damage(va - vb, dice_a.damage_type)
            is_kill = ub.is_dead
            award_emotion_for_hit(ua, ub, va - vb, is_kill)

            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_HIT)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_BE_HIT)
            return "a"
        else:
            # 방어 승
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DEFEND)
            return "b"

    # ================================================================
    # 3) ATTACK vs EVADE
    # ================================================================
    if ka == DiceKind.ATTACK and kb == DiceKind.EVADE:
        if va > vb:
            # 공격 성공
            ub.take_damage(va, dice_a.damage_type)
            is_kill = ub.is_dead
            award_emotion_for_hit(ua, ub, va, is_kill)

            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_HIT)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_BE_HIT)
            return "a"
        else:
            # 회피 성공 → 보통 피해 없음
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DODGE)
            return "b"

    # ================================================================
    # 4) DEFENSE vs DEFENSE
    # ================================================================
    if ka == DiceKind.DEFENSE and kb == DiceKind.DEFENSE:
        # 승패만, 피해 없음
        if va > vb:
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_DEFEND)
            return "a"
        elif vb > va:
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DEFEND)
            return "b"
        else:
            return "tie"

    # ================================================================
    # 5) DEFENSE vs EVADE
    # ================================================================
    if ka == DiceKind.DEFENSE and kb == DiceKind.EVADE:
        if va > vb:
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_DEFEND)
            return "a"
        elif vb > va:
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DODGE)
            return "b"
        else:
            return "tie"

    # ================================================================
    # 6) EVADE vs EVADE
    # ================================================================
    if ka == DiceKind.EVADE and kb == DiceKind.EVADE:
        # 피해 없음, 승패만 존재
        if va > vb:
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_DODGE)
            return "a"
        elif vb > va:
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_CLASH_WIN)
            apply_dice_trigger(dice_a, ua, ub, EffectTrigger.ON_CLASH_LOSS)
            apply_dice_trigger(dice_b, ub, ua, EffectTrigger.ON_DODGE)
            return "b"
        else:
            return "tie"


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
    if not can_unit_roll_dice(attacker):
        return
    if not is_unit_alive_and_present(defender):
        return

    val = dice.roll()

    if dice.kind == DiceKind.ATTACK:
        dmg_type = dice.damage_type or DamageType.SLASH
        defender.take_damage(val, dmg_type)

        # 🔹 일방 공격도 감정 코인 지급
        award_emotion_for_hit(attacker, defender, val, defender.is_dead)
    else:
        pass



def resolve_clash_between_units(unit_a, unit_b):
    """
    unit_a ↔ unit_b 가 서로를 노리는 합공 1쌍에 대한 전체 처리.
    - 각자의 planned_page를 사용.
    - 코스트(빛)를 먼저 지불.
    - 주사위를 인덱스 순서대로 1:1로 합 처리.
    - 더 많은 주사위를 가진 쪽의 남은 주사위는 일방공격.
    """
    if not is_unit_alive_and_present(unit_a) or not is_unit_alive_and_present(unit_b):
        return

    page_a = getattr(unit_a, "planned_page", None)
    page_b = getattr(unit_b, "planned_page", None)

    if page_a is None or page_b is None:
        return

    # 코스트 지불 실패 시 그 쪽 행동은 스킵
    if not unit_a.spend_light(page_a.cost):
        print(f"[빛 부족] {page_a.name}")
        page_a = None
    else:
        # 🔹 실제로 코스트를 지불했다면, 이 막에서 사용한 책장 수 +1
        if hasattr(unit_a, "pages_used_this_scene"):
            unit_a.pages_used_this_scene += 1

    if not unit_b.spend_light(page_b.cost):
        print(f"[빛 부족] {page_b.name}")
        page_b = None
    else:
        if hasattr(unit_b, "pages_used_this_scene"):
            unit_b.pages_used_this_scene += 1

    dice_a = build_dice_list_for_page(page_a, unit_a) if page_a else []
    dice_b = build_dice_list_for_page(page_b, unit_b) if page_b else []

    len_a = len(dice_a)
    len_b = len(dice_b)
    max_len = max(len_a, len_b)

    for i in range(max_len):
        d_a = dice_a[i] if i < len_a else None
        d_b = dice_b[i] if i < len_b else None

        # 둘 다 더 이상 유효하지 않으면 종료
        if (not is_unit_alive_and_present(unit_a)) and (not is_unit_alive_and_present(unit_b)):
            break

        # 현재 시점에서 주사위를 굴릴 수 있는지 체크
        can_a = d_a is not None and can_unit_roll_dice(unit_a)
        can_b = d_b is not None and can_unit_roll_dice(unit_b)

        # 둘 다 주사위를 굴릴 수 있음 → 합 처리
        if can_a and can_b:
            resolve_clash(d_a, d_b)
        # A만 굴릴 수 있음 → A 일방 공격
        elif can_a and (not can_b):
            resolve_one_sided_attack(d_a, unit_a, unit_b)
        # B만 굴릴 수 있음 → B 일방 공격
        elif can_b and (not can_a):
            resolve_one_sided_attack(d_b, unit_b, unit_a)
        # 둘 다 못 굴리면 이 인덱스는 그냥 스킵

def resolve_one_sided_sequence(attacker, defender):
    """
    공격자 attacker가 defender를 향해 planned_page로 일방 공격하는 전체 처리.
    - 코스트 지불
    - 주사위 순서대로 굴리며, ATTACK 주사위만 실제 피해를 준다.
    """
    if not is_unit_alive_and_present(attacker):
        return
    if not is_unit_alive_and_present(defender):
        return

    page = getattr(attacker, "planned_page", None)
    if page is None:
        return

    if not attacker.spend_light(page.cost):
        print(f"[빛 부족] {page.name}")
        return
    else:
        # 🔹 코스트 지불 성공 → 이 막에서 사용한 책장 수 +1
        if hasattr(attacker, "pages_used_this_scene"):
            attacker.pages_used_this_scene += 1

    dice_list = build_dice_list_for_page(page, attacker)

    for d in dice_list:
        if not can_unit_roll_dice(attacker):
            break
        if not is_unit_alive_and_present(defender):
            break
        resolve_one_sided_attack(d, attacker, defender)

def execute_scene_actions(all_units, ally_group, enemy_group):
    """
    이번 막에서 모든 planned_page / planned_target을
    속도 순서대로 처리하고, 막을 종료하는 함수.

    🔹중요 변경점:
      - 더 이상 speed_dice_count를 "행동 횟수"로 사용하지 않는다.
        → 유닛당 공격 행동은 최대 1번.
      - speed_dice_count는 순수하게 "속도 주사위(토큰) 개수"만 의미한다.
        (공격 vs 방어 토큰을 구분하는 데 사용)
    """
    # 1) 합공 쌍 찾기 (여전히 유닛 단위)
    mutual_pairs = find_mutual_target_pairs(ally_group, enemy_group)
    units_in_pairs = set()
    for a, e in mutual_pairs:
        units_in_pairs.add(a)
        units_in_pairs.add(e)

    # 2) 액션 리스트 구성
    #    (kind, speed, 공격자/유닛A, 피격자/유닛B)
    #    kind = "clash" 또는 "one_sided"
    actions = []

    # 합공 액션들
    # 합공 액션들
    for a, e in mutual_pairs:
        # 양쪽의 '실제로 공격에 사용하는 토큰' 속도를 기준으로 정렬용 속도 결정
        sv_a = getattr(a, "speed_values", [])
        idx_a = getattr(a, "attack_token_index", None)
        if idx_a is not None and 0 <= idx_a < len(sv_a):
            spd_a = sv_a[idx_a]
        else:
            spd_a = getattr(a, "current_speed", 0) or 0

        sv_e = getattr(e, "speed_values", [])
        idx_e = getattr(e, "attack_token_index", None)
        if idx_e is not None and 0 <= idx_e < len(sv_e):
            spd_e = sv_e[idx_e]
        else:
            spd_e = getattr(e, "current_speed", 0) or 0

        effective_speed = max(spd_a, spd_e)

        actions.append(("clash", effective_speed, a, e))

    # 합공에 포함되지 않은 유닛들의 일방 공격
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

        # ✅ 더 이상 speed_dice_count만큼 여러 번 넣지 않는다.
        #    대신, 실제로 책장을 사용한 속도 토큰의 값을 사용한다.
        sv_u = getattr(u, "speed_values", [])
        idx_u = getattr(u, "attack_token_index", None)
        if idx_u is not None and 0 <= idx_u < len(sv_u):
            spd = sv_u[idx_u]
        else:
            spd = getattr(u, "current_speed", 0) or 0
        actions.append(("one_sided", spd, u, target))

    # 3) 속도 내림차순 정렬 (빠른 순서대로 처리)
    actions.sort(key=lambda x: x[1], reverse=True)

    # 4) 실제 처리
    for kind, _, a, b in actions:
        if not is_unit_alive_and_present(a) or not is_unit_alive_and_present(b):
            continue
        if kind == "clash":
            resolve_clash_between_units(a, b)
        elif kind == "one_sided":
            resolve_one_sided_sequence(a, b)




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

    ally_group = create_ally_units()
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

    #  전투 시작 시 각 유닛에게 책장 9장 배정 + 손패 3장
    init_decks_for_units(ally_group, enemy_group)

    scene_index = 1  # 현재 막 번호
    scene_started = False  # 막이 시작됐는지 여부
    speed_rolled = False  # ✅ 이번 막에서 속도를 이미 굴렸는지 여부

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

    player_emotion = BattleEmotionSystem(is_player_side=True)
    enemy_emotion = BattleEmotionSystem(is_player_side=False)

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

    def draw_enemy_hover_page_ui(surface, font, hovered_speed_unit, hovered_speed_token_index):
        """왼쪽 위 감정 단계 아래에, 마우스로 올린 적 속도 토큰의 책장 정보를 간단히 표시한다."""
        # hover 대상이 없거나 아군이면 표시하지 않음
        if hovered_speed_unit is None or getattr(hovered_speed_unit, "is_ally", False):
            return

        enemy = hovered_speed_unit
        token_idx = hovered_speed_token_index

        # 어떤 토큰에서 어떤 책장을 쓰는지 찾기
        page = None
        token_plans = getattr(enemy, "token_plans", {})
        if isinstance(token_plans, dict) and token_idx is not None:
            plan = token_plans.get(token_idx)
            if plan is not None:
                page = plan.get("page")

        # 🔹 이 토큰에 배정된 책장이 없으면 아무것도 표시하지 않음
        if page is None:
            return

        # ------- UI 박스 위치 (왼쪽 위 감정 패널 바로 아래) -------
        width, height = surface.get_size()
        emotion_box_w = 180
        emotion_box_h = 80
        margin = 10
        gap = 6

        x = margin
        y = margin + emotion_box_h + gap
        box_w = 260
        box_h = 96

        pygame.draw.rect(surface, EMOTION_BG, (x, y, box_w, box_h), border_radius=8)
        pygame.draw.rect(surface, EMOTION_BORDER, (x, y, box_w, box_h), 2, border_radius=8)

        title = font.render("적 행동 미리보기", True, EMOTION_TEXT)
        surface.blit(title, (x + 8, y + 6))

        # 책장 이름
        name_text = font.render(page.name, True, EMOTION_TEXT)
        surface.blit(name_text, (x + 8, y + 30))

        # 코스트 + 주사위 요약 (작은 폰트)
        small_font = pygame.font.SysFont("malgungothic", 18)
        cost_text = small_font.render(f"코스트 {page.cost}", True, EMOTION_TEXT)
        surface.blit(cost_text, (x + 8, y + 54))

        # 주사위 간단 요약 1~2줄
        try:
            dice_lines = build_dice_summary_lines(page)
        except Exception:
            dice_lines = []

        line_y = y + 54
        for i, line in enumerate(dice_lines[:2]):
            if i > 0:
                line_y += 20
            dice_text = small_font.render(line, True, EMOTION_TEXT)
            surface.blit(dice_text, (x + 140, line_y))

    while running:
        dt = clock.tick(60)

        # --- 막이 아직 시작되지 않았으면 여기서 시작 처리 ---
        # --- 막이 아직 시작되지 않았으면 여기서 시작 처리 ---
        if not scene_started:
            start_scene(scene_index, all_units)

            # ✅ 이번 막 시작 시, 이전 막의 공격 계획 초기화 & 속도 미정 상태로
            reset_plans(all_units)
            speed_rolled = False

            scene_started = True

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                result = "quit"

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # ESC로 전투 강제 종료 → 로비로 돌아가기
                    running = False
                    result = "retreat"

                if event.key == pygame.K_SPACE:
                    # 1) 아직 이번 막의 속도를 안 굴렸다면 → 속도 굴리기 + 적 계획 잡기
                    if not speed_rolled:
                        for u in all_units:
                            u.roll_speed()

                        # 속도 확정 후에 적들이 자동으로 아군을 타겟팅
                        plan_enemy_actions(enemy_group, ally_group)

                        speed_rolled = True

                    # 2) 이미 속도가 굴려진 상태라면 → 실제 전투(합/일방 공격) 실행
                    else:
                        execute_scene_actions(all_units, ally_group, enemy_group)

                        # 막 종료 처리 (상태이상, 카드 드로우 등)
                        end_scene(all_units)

                        # 다음 막으로
                        scene_index += 1
                        scene_started = False  # 다음 루프에서 start_scene 이 호출됨

                        # 유저 선택 상태 초기화
                        selected_unit = None
                        selected_card = None
                        is_dragging_card = False



                if event.key == pygame.K_a:
                    # 테스트용: 적 전체에게 참격 10
                    for e in enemy_group:
                        e.take_damage(10, DamageType.SLASH)

                # N 키: 테스트용으로 '막 종료 후 다음 막 시작'
                if event.key == pygame.K_n:
                    # 이번 막 종료 처리
                    end_scene(all_units)

                    # 다음 막 번호로
                    scene_index += 1
                    scene_started = False   # 다음 루프에서 start_scene()이 다시 호출됨

                # C 키: 테스트용 합 시뮬레이션
                if event.key == pygame.K_c:
                    # 아군 중 살아있는 첫 유닛, 적군 중 살아있는 첫 유닛 찾기
                    attacker = None
                    defender = None
                    for u in ally_group:
                        if not u.is_dead and not u.is_escaped:
                            attacker = u
                            break
                    for e in enemy_group:
                        if not e.is_dead and not e.is_escaped:
                            defender = e
                            break

                    if attacker is not None and defender is not None:
                        # 예시: 아군 공격 주사위 (3~7 참격), 적 방어 주사위 (2~5)
                        atk_dice = Dice(attacker, DiceKind.ATTACK, 3, 7, DamageType.SLASH)
                        def_dice = Dice(defender, DiceKind.DEFENSE, 2, 5, None)

                        winner, va, vb = resolve_clash(atk_dice, def_dice)
                        print(f"합 결과: A({atk_dice.kind.name})={va}, B({def_dice.kind.name})={vb}, winner={winner}")
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

                # ✅ 속도 굴리기 전(0막 느낌)에는 토큰/카드 관련 상호작용 금지
                if not speed_rolled:
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

                    # 우클릭 처리 후에는 더 이상 이 이벤트로 할 일이 없음
                    continue

                    if clicked_unit is not None:
                        # 적은 좌클릭으로 선택 불가 (아군만 선택 가능)
                        if not clicked_unit.is_ally:
                            continue

                        # a) 아직 아무 유닛도 선택 안 한 상태 → 이 유닛 + 해당 토큰 선택
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

                        # (b) 현재 선택된 유닛을 우클릭 → 선택 해제
                        if clicked_unit is selected_unit:
                            selected_unit = None
                            selected_token_index = None
                            continue

                    # (3) 빈 곳 우클릭은 아무 동작 없음
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

                        # 🔴 여기! 유닛만 가져오던 걸 → (유닛, 토큰 인덱스) 로 가져오게 수정
                        # 기존:
                        # clicked_enemy = get_unit_at_token(enemy_group, mouse_pos)
                        # 변경:
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

                            # 이하 speed 계산 + update_counter_target_on_attack 부분은 기존 코드 그대로 유지
                            ...

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

        mouse_pos = pygame.mouse.get_pos()
        hovered_unit = None
        hovered_speed_unit = None
        hovered_speed_token_index = None

        # 1) 본체 스프라이트 기준 hover (오른쪽 패널)
        for u in all_units:
            if u.rect.collidepoint(mouse_pos):
                hovered_unit = u
                break

        # 2) 속도 코인 기준 hover (카드/미리보기용)
        for u in all_units:
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

        # ===== 그리기 시작 =====
        screen.fill((30, 30, 40))

        # 상단 정보 텍스트
        info = font.render(
            f"스테이지: {stage_code} / 막: {scene_index} ",
            True, WHITE
        )

        # 1) 유닛들 먼저 그리기
        for u in all_units:
            u.draw(screen, font)

        # 2) 적/아군 계획 화살표 + 합공격(양방향) 표시

        # 합공 쌍 (아군, 적) 유닛 튜플 목록
        mutual_pairs = find_mutual_target_pairs(ally_group, enemy_group)

        # 노란 합공 화살표 (3번 키)
        if show_mutual_arrows:
            draw_mutual_arrows(screen, mutual_pairs, (255, 230, 80))

        # 파란/빨간 일방 화살표 (합공에 해당하는 쌍은 빼고 그림)
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
                highlight_unit=None,  # 아군 화살표는 그대로
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

        # 6) 오른쪽 정보 패널
        draw_unit_info_panel(screen, font, hovered_unit)

        # 7) 중앙 아래 카드 UI
        if speed_rolled:
            hand_owner, hand_token_index = get_hand_owner(
                selected_unit, selected_token_index,
                hovered_speed_unit, hovered_speed_token_index
            )
            draw_hand_cards(screen, font, hand_owner, hand_token_index, selected_unit, mouse_pos)

        # ✅ 마지막에 한 번만 flip
        pygame.display.flip()

    return result

