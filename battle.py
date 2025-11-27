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

        # 기본 속도 주사위 개수는 1, 감정 4단계 이상이면 +speed_dice_bonus
        base_speed_dice = 1
        if emo is not None:
            u.speed_dice_count = base_speed_dice + emo.speed_dice_bonus
        else:
            u.speed_dice_count = base_speed_dice

        # 최대 빛 보너스는 플레이어 측에만 적용
        if emo is not None and emo.is_player_side:
            base_max_light = 3
            u.max_light = base_max_light + emo.max_light_bonus
            if u.light > u.max_light:
                u.light = u.max_light

        # 빛 1개 획득
        if hasattr(u, "gain_light"):
            u.gain_light(1)

        # 이전 막에서 흐트러졌던 유닛 복구
        if hasattr(u, "recover_stagger_next_scene"):
            u.recover_stagger_next_scene()

        # 속도 주사위 리셋 (다음에 SPACE로 다시 굴릴 수 있게)
        if hasattr(u, "reset_speed_for_new_turn"):
            u.reset_speed_for_new_turn()




def end_scene(all_units):
    """
    막 종료 시 호출.
    - 화상/출혈 등 상태이상 처리 및 지속시간 감소
    - 각 유닛이 책장 1장씩 추가로 뽑음 (+ 감정 단계 보너스)
    """
    for u in all_units:
        if hasattr(u, "on_scene_end"):
            u.on_scene_end()

        # ✅ 덱이 있는 유닛이라면 막 종료 시 카드 1장 + 감정 보너스만큼 추가 드로우
        if hasattr(u, "draw_cards"):
            extra_draw = 0
            emo = None
            try:
                emo = get_emotion_system_for(u)
            except NameError:
                emo = None

            if emo is not None and emo.is_player_side:
                extra_draw = emo.next_scene_draw_bonus

            u.draw_cards(1 + extra_draw)



def reset_plans(all_units):
    """새 막 시작 시 모든 유닛의 planned_page / planned_target / initial_target 리셋"""
    for u in all_units:
        if hasattr(u, "planned_page"):
            u.planned_page = None
        if hasattr(u, "planned_target"):
            u.planned_target = None
        # ✅ '처음에 공격하려던 애' 기록도 막 시작할 때 리셋
        if hasattr(u, "initial_target"):
            u.initial_target = None



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
        u = Unit(x, y, 2, 5, True, None, 40, 20, hp_res, sp_res)

        # ⭐ 테스트: 첫 번째 아군만 속도 주사위 2개
        if idx == 0:
            u.speed_dice_count = 2

        ally_group.add(u)

    return ally_group



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
        enemy_group.add(u)

    return enemy_group


def plan_enemy_actions(enemy_group, ally_group):
    """
    이번 막에서 적들이 어떤 책장으로 누구를 공격할지 미리 정해둔다.
    - 본인이 가진 hand 중에서 코스트가 현재 빛(self.light) 이하인 책장만 후보
    - 그 중 하나를 랜덤 선택
    - 아군 중 살아있는 유닛 하나를 랜덤 선택해서 타깃으로 지정
    """
    # 현재 살아있는 아군 목록
    alive_allies = [a for a in ally_group if not a.is_dead and not a.is_escaped]

    for e in enemy_group:
        # 기본값 초기화
        if hasattr(e, "planned_page"):
            e.planned_page = None
        if hasattr(e, "planned_target"):
            e.planned_target = None

        if e.is_dead or e.is_escaped:
            continue
        if not alive_allies:
            continue

        hand = getattr(e, "hand", None)
        if not hand:
            continue

        current_light = getattr(e, "light", 0)

        # 현재 빛으로 사용할 수 있는 책장만 필터링
        affordable = [p for p in hand if p.cost <= current_light]

        if not affordable:
            continue

        page = random.choice(affordable)
        target = random.choice(alive_allies)

        e.planned_page = page
        e.planned_target = target

        e.initial_target = target

def update_counter_target_on_attack(attacker, defender):
    """
    공격자(attacker)가 defender를 타겟팅했을 때,
    defender가 누구를 노릴지(반타겟)를 갱신하는 함수.

    규칙 정리:

    1) 공격자의 속도가 defender보다 느리거나 같으면 → 타겟 변경 없음.
       (attacker_speed <= defender_speed 이면 그대로 유지)

    2) 공격자의 속도가 defender보다 빠르면 → 무조건 공격자로 갈아탄다.
       (attacker_speed > defender_speed 이면 defender.planned_target = attacker)

    3) 단, defender.initial_target 이 공격자라면
       속도와 관계없이 무조건 그 공격자로 되돌린다.
    """
    if attacker is None or defender is None:
        return
    if attacker.is_dead or attacker.is_escaped or defender.is_dead or defender.is_escaped:
        return

    # 같은 팀이면 반타겟팅 안 함
    if attacker.is_ally == defender.is_ally:
        return

    atk_spd = getattr(attacker, "current_speed", None)
    def_spd = getattr(defender, "current_speed", None)

    # ✅ [규칙 3] 처음에 노리던 애가 나를 때리면 → 속도 상관없이 그 애로 되돌리기
    initial = getattr(defender, "initial_target", None)
    if initial is attacker:
        defender.planned_target = attacker
        return

    # 속도 정보 없으면 안전하게 무시
    if atk_spd is None or def_spd is None:
        return

    # ✅ [규칙 1] 공격자가 나보다 느리거나 같으면 타겟 유지
    if atk_spd <= def_spd:
        return

    # ✅ [규칙 2] 공격자가 나보다 빠르면 무조건 그 공격자로 갈아탄다
    defender.planned_target = attacker


def retarget_defender_after_cancel(defender, all_units):
    """
    어떤 유닛이 defender를 향한 공격을 취소했을 때,
    defender의 planned_target을 다시 잡아주는 함수.

    규칙:
      1) defender를 현재 타겟팅 중인 유닛들 중
         (살아 있고, 반대 진영이며, 속도가 정해진 유닛)
         가장 속도가 빠른 유닛이 있다면 그 유닛으로 타겟 변경
         → 합공 상태 형성 (서로를 노리게 됨)

      2) 그런 유닛이 없다면 defender.initial_target 으로 복귀
         (initial_target이 살아 있을 때만)
    """
    if defender is None:
        return
    if defender.is_dead or defender.is_escaped:
        return

    best_attacker = None
    best_speed = -1

    for u in all_units:
        if u is defender:
            continue
        if u.is_dead or u.is_escaped:
            continue

        # 나를 타겟팅 중인 유닛인지, 그리고 반대 진영인지 확인
        if getattr(u, "planned_target", None) is defender and (u.is_ally != defender.is_ally):
            spd = getattr(u, "current_speed", None)
            if spd is None:
                continue
            if spd > best_speed:
                best_speed = spd
                best_attacker = u

    if best_attacker is not None:
        # 가장 빠른 공격자와 합공
        defender.planned_target = best_attacker
    else:
        # 아무도 나를 안 때리면 → 원래 타겟으로 복귀
        initial = getattr(defender, "initial_target", None)
        if initial is not None and not initial.is_dead and not initial.is_escaped:
            defender.planned_target = initial
        else:
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
    없으면 None.
    """
    mx, my = pos
    for u in all_units:
        cx = u.rect.centerx
        cy = u.rect.top - 40   # draw_speed_token과 동일한 위치
        radius = 28            # draw_speed_token에서 쓰는 값과 맞춰야 함

        dx = mx - cx
        dy = my - cy
        if dx * dx + dy * dy <= radius * radius:
            return u
    return None



def get_hand_owner(selected_unit, hovered_speed_unit):
    """
    중앙 아래에 어떤 유닛의 카드를 보여줄지 결정.
    - 캐릭터를 선택한 상태면: 항상 그 캐릭터 기준
    - 아니면: 속도 코인 위에 마우스가 올라간 유닛 기준
    """
    if selected_unit is not None:
        return selected_unit
    return hovered_speed_unit


def get_hand_pages_for_owner(owner, selected_unit):
    """
    hand에 어떤 페이지들을 보여줄지 결정.
    - 아군:
        - 선택된 상태면: 현재 손패(hand)
        - 선택되지 않았고 planned_page가 있으면: 그 planned_page 1장만
        - 그 외: 현재 손패(hand)
    - 적:
        - planned_page가 있으면: 그 카드 1장
        - 아니면: 빈 리스트
    """
    if owner is None:
        return []

    # 적
    if not owner.is_ally:
        page = getattr(owner, "planned_page", None)
        return [page] if page is not None else []

    # 아군
    if owner is selected_unit:
        return list(getattr(owner, "hand", []))

    planned = getattr(owner, "planned_page", None)
    if planned is not None:
        return [planned]

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


def draw_hand_cards(surface, font, owner, selected_unit, mouse_pos):
    """
    화면 아래쪽에 카드(책장)를 실제 UI처럼 그린다.
    - owner: 카드를 보여줄 유닛
    - selected_unit: 현재 선택된 유닛(카드 인터랙션 가능한 대상)
    - mouse_pos: 마우스 위치 (hover 시 카드 확대)
    """

    small_font = pygame.font.SysFont("malgungothic", 18)

    width, height = surface.get_size()
    pages = get_hand_pages_for_owner(owner, selected_unit)
    card_infos = build_hand_card_rects(pages, width, height)

    if not card_infos:
        return card_infos  # 빈 리스트

    # 어떤 카드 위에 마우스가 올라갔는지
    hovered_index = None
    for idx, (page, rect) in enumerate(card_infos):
        if rect.collidepoint(mouse_pos):
            hovered_index = idx
            break

    for idx, (page, rect) in enumerate(card_infos):
        is_hovered = (idx == hovered_index)
        # 기본 카드 크기
        draw_rect = rect.copy()

        # 선택 가능한 상황(아군 + 선택된 유닛 == owner + 아직 공격 계획 없음)에서만 확대 효과
        if (
            owner is selected_unit
            and owner.is_ally
            and getattr(owner, "planned_page", None) is None
            and is_hovered
        ):
            # 살짝 크게, 위로 올리기
            scale = 1.2
            new_w = int(rect.width * scale)
            new_h = int(rect.height * scale)
            draw_rect.width = new_w
            draw_rect.height = new_h
            draw_rect.centerx = rect.centerx
            draw_rect.bottom = rect.bottom + 10  # 위로 약간 올려서 강조

        # 카드 색상
        if owner.is_ally:
            base_color = (220, 240, 255)
        else:
            base_color = (255, 230, 230)

        border_color = (80, 80, 80)
        # 코스트가 빛보다 크면 회색 처리
        light = getattr(owner, "light", 0)
        afford = (page is not None and page.cost <= light)
        if not afford:
            base_color = (180, 180, 180)

        pygame.draw.rect(surface, base_color, draw_rect)
        pygame.draw.rect(surface, border_color, draw_rect, 2)

        if page is None:
            continue

        # 카드 텍스트: 맨 위 이름, 그 아래 코스트
        name_text = small_font.render(page.name, True, (0, 0, 0))
        cost_text = small_font.render(f"코스트 {page.cost}", True, (0, 0, 0))

        surface.blit(name_text, (draw_rect.x + 8, draw_rect.y + 8))
        surface.blit(cost_text, (draw_rect.x + 8, draw_rect.y + 36))

        # --- 주사위 정보 한 줄씩 그리기 ---
        dice_lines = build_dice_summary_lines(page)

        # 시작 Y 위치 (코스트 아래부터)
        line_y = draw_rect.y + 64
        line_h = 22  # 줄 간격

        for line in dice_lines:
            txt = small_font.render(line, True, (0, 0, 0))
            surface.blit(txt, (draw_rect.x + 8, line_y))
            line_y += line_h

    return card_infos



def draw_planned_arrows(surface, units, color, exclude_units=None):
    """
    planned_page/planned_target 가 설정된 유닛들의 토큰 코인 → 타깃 코인 방향으로 화살표를 그린다.
    exclude_units에 포함된 유닛은 시작점으로 그리지 않는다.
    """
    if exclude_units is None:
        exclude_units = set()

    for u in units:
        if u in exclude_units:
            continue

        page = getattr(u, "planned_page", None)
        target = getattr(u, "planned_target", None)
        if page is None or target is None:
            continue
        if u.is_dead or u.is_escaped or target.is_dead or target.is_escaped:
            continue

        start = (u.rect.centerx, u.rect.top - 40)        # 속도 코인 위치
        end = (target.rect.centerx, target.rect.top - 40)

        draw_drag_arrow(surface, start, end, color)


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
    합공격 상태인 쌍들(A, E)에 대해
    양쪽 방향으로 노란 화살표를 그린다.
    """
    for a, e in pairs:
        if a.is_dead or a.is_escaped or e.is_dead or e.is_escaped:
            continue

        start_a = (a.rect.centerx, a.rect.top - 40)
        start_e = (e.rect.centerx, e.rect.top - 40)

        # A → E, E → A 두 방향 모두 그림
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
    if not unit_b.spend_light(page_b.cost):
        print(f"[빛 부족] {page_b.name}")
        page_b = None

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
    속도 주사위 개수(speed_dice_count)가 2 이상이라면,
    그만큼 여러 번 행동할 수 있다.
    """
    # 1) 합공 쌍 찾기
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
    for a, e in mutual_pairs:
        spd_a = getattr(a, "current_speed", 0) or 0
        spd_e = getattr(e, "current_speed", 0) or 0
        effective_speed = max(spd_a, spd_e)

        # 기본 1번은 합공으로 처리
        actions.append(("clash", effective_speed, a, e))

        # 남은 속도 주사위 개수만큼은 일방 공격으로 한 번 더 행동
        extra_a = max(0, getattr(a, "speed_dice_count", 1) - 1)
        extra_e = max(0, getattr(e, "speed_dice_count", 1) - 1)

        target_a = getattr(a, "planned_target", None) or e
        target_e = getattr(e, "planned_target", None) or a

        for _ in range(extra_a):
            if is_unit_alive_and_present(a) and is_unit_alive_and_present(target_a):
                actions.append(("one_sided", spd_a, a, target_a))
        for _ in range(extra_e):
            if is_unit_alive_and_present(e) and is_unit_alive_and_present(target_e):
                actions.append(("one_sided", spd_e, e, target_e))

    # 일방 공격 액션들 (합공에 포함되지 않은 유닛들)
    for u in all_units:
        if u in units_in_pairs:
            continue
        page = getattr(u, "planned_page", None)
        target = getattr(u, "planned_target", None)
        if page is None or target is None:
            continue
        if not is_unit_alive_and_present(u):
            continue

        spd = getattr(u, "current_speed", 0) or 0
        extra = max(1, getattr(u, "speed_dice_count", 1))
        for _ in range(extra):
            if not is_unit_alive_and_present(u) or not is_unit_alive_and_present(target):
                break
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

    show_enemy_arrows = False  # 1번 키로 토글하는 표시 여부
    show_ally_arrows = True  # ✅ 2번 키: 아군(파란) 화살표 표시 여부
    show_mutual_arrows = True  # ✅ 3번 키: 합공격(노란) 화살표 표시 여부

    # ✅ 유저 입력/선택 상태
    selected_unit = None  # 현재 선택된 아군 유닛
    selected_card = None  # 현재 선택해서 드래그 중인 책장(CombatPage)
    is_dragging_card = False  # 책장 선택 후 타깃 지정 중인지 여부

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
                        # 유닛 선택 상태는 유지
                        continue

                    # 2) 토큰(속도 코인) 위 우클릭 처리
                    clicked_unit = get_unit_at_token(all_units, mouse_pos)

                    if clicked_unit is not None:
                        # (a) 이미 공격 계획이 있는 아군 → 계획 취소 + 카드 되돌리기
                        if clicked_unit.is_ally and getattr(clicked_unit, "planned_page", None) is not None:
                            # ✅ 취소하기 전에 내가 노리던 대상(적)을 저장
                            old_target = getattr(clicked_unit, "planned_target", None)

                            page = clicked_unit.planned_page
                            if page is not None:
                                clicked_unit.hand.append(page)

                            clicked_unit.planned_page = None
                            clicked_unit.planned_target = None

                            # ✅ 이제 그 적의 타겟팅을 다시 계산
                            if old_target is not None:
                                retarget_defender_after_cancel(old_target, all_units)

                            continue

                        # (b) 현재 선택된 유닛을 우클릭 → 선택 해제
                        if clicked_unit is selected_unit:
                            selected_unit = None
                            continue

                    # (3) 빈 곳 우클릭은 아무 동작 없음
                    continue


                # ---- 좌클릭 ----
                if event.button == 1:
                    # 카드 드래그 중이면: 적 '토큰(속도 코인)' 클릭 시 타깃 확정
                    if is_dragging_card and selected_unit is not None and selected_card is not None:
                        # ✅ 적 그룹에서 "토큰 위에 있는 유닛" 찾기
                        clicked_enemy = get_unit_at_token(enemy_group, mouse_pos)

                        if clicked_enemy is not None:
                            # 타깃 확정 → 유닛의 planned_page/target 설정 + 손패에서 카드 제거
                            selected_unit.planned_page = selected_card
                            selected_unit.planned_target = clicked_enemy
                            if selected_card in selected_unit.hand:
                                selected_unit.hand.remove(selected_card)

                            # ✅ 공격자가 selected_unit, 피격자가 clicked_enemy
                            update_counter_target_on_attack(attacker=selected_unit, defender=clicked_enemy)

                            # 선택 상태 종료
                            is_dragging_card = False
                            selected_card = None
                            selected_unit = None

                        # 적 토큰이 아니면: 그대로 드래그 유지
                        continue

                    # --- 여기부터는 드래그 중이 아닐 때의 좌클릭 ---

                    # 1) 먼저, 선택된 유닛이 있고 아직 공격 계획이 없다면 → 카드 클릭 여부 확인
                    if selected_unit is not None and getattr(selected_unit, "planned_page", None) is None:
                        owner = selected_unit  # 선택된 유닛의 손패만 인터랙티브
                        width, height = screen.get_size()
                        pages = get_hand_pages_for_owner(owner, selected_unit)
                        card_infos = build_hand_card_rects(pages, width, height)

                        clicked_page = None
                        for page, rect in card_infos:
                            if rect.collidepoint(mouse_pos):
                                clicked_page = page
                                break

                        if clicked_page is not None:
                            # 코스트 체크: 현재 빛보다 높으면 선택 불가
                            if clicked_page.cost <= getattr(selected_unit, "light", 0):
                                selected_card = clicked_page
                                is_dragging_card = True
                            # 코스트 부족이면 아무 일도 안 함
                            continue

                    # 2) 카드가 아니면 토큰 좌클릭 처리 (유닛 선택/변경)
                    clicked_unit = get_unit_at_token(all_units, mouse_pos)

                    if clicked_unit is not None:
                        # 적이거나, 이미 공격 계획이 잡힌 아군은 좌클릭으로 선택 불가
                        if not clicked_unit.is_ally:
                            continue
                        if getattr(clicked_unit, "planned_page", None) is not None:
                            continue

                        # a) 아무것도 선택 안 된 상태 → 이 유닛 선택
                        if selected_unit is None:
                            selected_unit = clicked_unit
                        else:
                            # b) 다른 유닛이 선택된 상태 → 그 선택 해제 + 새 유닛 선택
                            if clicked_unit is not selected_unit:
                                selected_unit = clicked_unit
                        continue

                    # 3) 아무 토큰도 클릭 안 했으면: 선택 유지 (별도 동작 없음)


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

        # 1) 본체 스프라이트 기준 hover (오른쪽 패널)
        for u in all_units:
            if u.rect.collidepoint(mouse_pos):
                hovered_unit = u
                break

        # 2) 속도 코인 기준 hover (카드 보기용)
        for u in all_units:
            cx = u.rect.centerx
            cy = u.rect.top - 40
            radius = 28
            dx = mouse_pos[0] - cx
            dy = mouse_pos[1] - cy
            if dx * dx + dy * dy <= radius * radius:
                hovered_speed_unit = u
                break

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

        # 합공격(서로 타겟팅) 쌍 찾기
        mutual_pairs = find_mutual_target_pairs(ally_group, enemy_group)
        mutual_allies = {a for (a, e) in mutual_pairs}
        mutual_enemies = {e for (a, e) in mutual_pairs}

        # 합공격 상태: 노란색 양방향 화살표 (3번 키)
        if show_mutual_arrows:
            draw_mutual_arrows(screen, mutual_pairs, (255, 230, 80))

        # 그 외 일반 타겟팅 화살표
        if show_enemy_arrows:
            draw_planned_arrows(screen, enemy_group, (255, 80, 80), exclude_units=mutual_enemies)

        if show_ally_arrows:
            draw_planned_arrows(screen, ally_group, (80, 160, 255), exclude_units=mutual_allies)

        # 3) 카드 드래그 중이면 드래그 화살표
        if is_dragging_card and selected_unit is not None and selected_card is not None:
            start = (selected_unit.rect.centerx, selected_unit.rect.top - 40)
            draw_drag_arrow(screen, start, mouse_pos, (80, 160, 255))

        # 4) 상단 정보 텍스트
        screen.blit(info, (200, 20))

        # 5) 감정 UI
        draw_emotion_ui(screen, font, player_emotion, enemy_emotion)

        # 6) 오른쪽 정보 패널
        draw_unit_info_panel(screen, font, hovered_unit)

        # 7) 중앙 아래 카드 UI
        if speed_rolled:
            hand_owner = get_hand_owner(selected_unit, hovered_speed_unit)
            draw_hand_cards(screen, font, hand_owner, selected_unit, mouse_pos)

        # ✅ 마지막에 한 번만 flip
        pygame.display.flip()

    return result

