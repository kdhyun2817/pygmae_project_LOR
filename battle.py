# battle.py
import pygame
import random

from unit import (
    Unit, DamageType, ResistLevel, DAMAGE_NAME_KO,
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
    """
    for u in all_units:
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
    - 각 유닛이 책장 1장씩 추가로 뽑음
    """
    for u in all_units:
        if hasattr(u, "on_scene_end"):
            u.on_scene_end()

        # ✅ 덱이 있는 유닛이라면 막 종료 시 카드 1장 뽑기
        if hasattr(u, "draw_cards"):
            u.draw_cards(1)

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
    def __init__(self, owner, kind, min_value, max_value, damage_type=None):
        self.owner = owner
        self.kind = kind
        self.min_value = min_value
        self.max_value = max_value
        self.damage_type = damage_type
        self.value = None

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
        self.max_light_bonus = 0
        self.speed_dice_bonus = 0
        self.next_scene_draw_bonus = 0

        # 환상체(EGO) 획득 횟수
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
        # 공통(아군/적 동일)
        self.ego_count += 1

        if not self.is_player_side:
            return  # 적은 여기서 끝 (추가 효과 없음)

        # 아군만 추가 효과
        self.max_light_bonus += 1

        if self.level == 4:
            self.speed_dice_bonus += 1

        if self.level == 5:
            self.next_scene_draw_bonus += 1


def create_ally_units():
    """아군 유닛 3명 생성 (오른쪽 '<' 모양)"""
    ally_group = pygame.sprite.Group()
    ally_positions = [
        (700, 430),  # 가운데(전방)
        (760, 380),  # 오른쪽 위
        (760, 480),  # 오른쪽 아래
    ]

    for x, y in ally_positions:
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

    기본 규칙:
    1) 공격자의 속도가 defender보다 느리거나 같으면 타겟 변경 없음.
    2) 공격자의 속도가 defender보다 빠를 때만 타겟 변경을 고려.
    3) 기존 타겟이 없거나, 죽었거나, 같은 팀이면 공격자로 변경.
    4) 기존 타겟이 살아 있고 적 팀일 때는
       공격자 속도 > 기존 타겟 속도일 때만 갈아탄다.

    + 추가 규칙(너가 말한 부분):
    A) defender.initial_target 이 이번 공격자라면
       속도와 상관없이 무조건 그 공격자로 타겟을 되돌린다.
    """
    if attacker is None or defender is None:
        return
    if attacker.is_dead or attacker.is_escaped or defender.is_dead or defender.is_escaped:
        return
    # 같은 팀은 반타겟팅 안 함
    if attacker.is_ally == defender.is_ally:
        return

    atk_spd = getattr(attacker, "current_speed", None)
    def_spd = getattr(defender, "current_speed", None)

    # ✅ [추가 규칙 A] 처음에 노리던 애가 나를 때리면 무조건 그 애로 되돌리기
    initial = getattr(defender, "initial_target", None)
    if initial is attacker:
        defender.planned_target = attacker
        return

    # 여기부터는 기존 “속도 기반 역타겟팅” 규칙

    if atk_spd is None or def_spd is None:
        return

    # 1) 공격자가 나보다 느리거나 같으면 → 타겟 유지
    if atk_spd <= def_spd:
        return

    current = getattr(defender, "planned_target", None)

    # 3) 기존 타겟이 없거나, 죽었거나, 같은 팀이면 → 공격자로 변경
    if current is None or current.is_dead or current.is_escaped or current.is_ally == defender.is_ally:
        defender.planned_target = attacker
        return

    cur_spd = getattr(current, "current_speed", None)

    if cur_spd is None:
        defender.planned_target = attacker
        return

    # 4) 공격자가 기존 타겟보다 빠른 경우에만 갈아탄다
    if atk_spd > cur_spd:
        defender.planned_target = attacker
    # 아니면 그대로 유지




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
        name_text = font.render(page.name, True, (0, 0, 0))
        cost_text = font.render(f"코스트 {page.cost}", True, (0, 0, 0))

        surface.blit(
            name_text,
            (draw_rect.x + 8, draw_rect.y + 8)
        )
        surface.blit(
            cost_text,
            (draw_rect.x + 8, draw_rect.y + 36)
        )

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
def resolve_clash(dice_a: Dice, dice_b: Dice):
    """
    라오루식 합 시스템.
    dice_a, dice_b는 각각 owner(Unit), kind(DiceKind), damage_type 등을 가지고 있어야 한다.
    이 함수는:
      - 두 주사위를 굴리고
      - 주사위 종류(공격/방어/회피) 조합에 따라
      - 적절한 데미지/흐트러짐/회복을 적용한다.
    """

    # --- 주사위 굴리기 ---
    va = dice_a.roll()
    vb = dice_b.roll()

    ka = dice_a.kind
    kb = dice_b.kind

    ua = dice_a.owner  # Unit
    ub = dice_b.owner  # Unit

    # 편의를 위해 값 차이
    diff_ab = va - vb
    diff_ba = vb - va

    # ========= 1) 공격 vs 공격 =========
    if ka == DiceKind.ATTACK and kb == DiceKind.ATTACK:
        if va > vb:
            # A 승 → B가 A값만큼 피해
            ub.take_damage(va, dice_a.damage_type)
            winner = "a"
        elif vb > va:
            ua.take_damage(vb, dice_b.damage_type)
            winner = "b"
        else:
            # 무승부: 둘 다 피해 없음 (감정코인 등은 나중에 이 분기에서 처리)
            winner = "tie"

    # ========= 2) 공격 vs 방어 / 방어 vs 공격 =========
    elif ka == DiceKind.ATTACK and kb == DiceKind.DEFENSE:
        # A: 공격 / B: 방어
        if va > vb:
            # 방어 패배 → 방어측 HP,SP에 (공-방)만큼 직접 피해
            ub.take_hp_sp_direct(diff_ab)
            winner = "a"
        elif vb > va:
            # 방어 승리 → 공격측 SP에 (방-공)만큼 흐트러짐 피해
            ua.take_sp_direct(diff_ba)
            winner = "b"
        else:
            winner = "tie"

    elif ka == DiceKind.DEFENSE and kb == DiceKind.ATTACK:
        # A: 방어 / B: 공격 (위 로직과 대칭)
        if va > vb:
            # 방어 승리 → 공격측 SP에 (방-공)만큼 흐트러짐 피해
            ub.take_sp_direct(diff_ab)
            winner = "a"
        elif vb > va:
            # 방어 패배 → 방어측 HP,SP에 (공-방)만큼 직접 피해
            ua.take_hp_sp_direct(diff_ba)
            winner = "b"
        else:
            winner = "tie"

    # ========= 3) 방어 vs 방어 =========
    elif ka == DiceKind.DEFENSE and kb == DiceKind.DEFENSE:
        if va > vb:
            # 승리한 방어 주사위 값만큼 상대 SP에 흐트러짐 피해
            ub.take_sp_direct(va)
            winner = "a"
        elif vb > va:
            ua.take_sp_direct(vb)
            winner = "b"
        else:
            winner = "tie"

    # ========= 4) 방어 vs 회피 / 회피 vs 방어 =========
    elif ka == DiceKind.DEFENSE and kb == DiceKind.EVADE:
        if va > vb:
            # 방어 승리 → 방어값만큼 상대 SP 흐트러짐 피해
            ub.take_sp_direct(va)
            winner = "a"
        elif vb > va:
            # 회피 승리 → 회피값만큼 회피측 SP 회복
            ub.recover_sp(vb)
            winner = "b"
        else:
            winner = "tie"

    elif ka == DiceKind.EVADE and kb == DiceKind.DEFENSE:
        if va > vb:
            # 회피 승리 → 회피값만큼 회피측 SP 회복
            ua.recover_sp(va)
            winner = "a"
        elif vb > va:
            # 방어 승리 → 방어값만큼 상대 SP 흐트러짐 피해
            ua.take_sp_direct(vb)
            winner = "b"
        else:
            winner = "tie"

    # ========= 5) 회피 vs 공격 / 공격 vs 회피 =========
    elif ka == DiceKind.EVADE and kb == DiceKind.ATTACK:
        if va > vb:
            # 회피 승리 → 회피값만큼 SP 회복 (재사용 효과는 나중에 구현 가능)
            ua.recover_sp(va)
            winner = "a"
        elif vb > va:
            # 공격 승리 → 체력 + 흐트러짐 피해 (공격 주사위 값만큼)
            ua.take_hp_sp_direct(vb)
            winner = "b"
        else:
            winner = "tie"

    elif ka == DiceKind.ATTACK and kb == DiceKind.EVADE:
        if va > vb:
            # 공격 승리
            ub.take_hp_sp_direct(va)
            winner = "a"
        elif vb > va:
            # 회피 승리 → SP 회복
            ub.recover_sp(vb)
            winner = "b"
        else:
            winner = "tie"

    # ========= 6) 회피 vs 회피 =========
    elif ka == DiceKind.EVADE and kb == DiceKind.EVADE:
        # 둘 다 소멸, 효과 없음 (감정코인/부가효과는 나중에 추가 가능)
        winner = "tie"

    else:
        # 정의되지 않은 조합 (혹시 모를 예외용)
        winner = "unknown"

    return winner, va, vb


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

    # 감정 UI 색상
    EMOTION_BG = (30, 30, 50)
    EMOTION_BORDER = (200, 200, 220)
    EMOTION_TEXT = (240, 240, 255)
    EMOTION_POS_COLOR = (120, 200, 255)  # 긍정 코인 색
    EMOTION_NEG_COLOR = (255, 120, 140)  # 부정 코인 색

    def draw_emotion_ui(surface, font, player_emotion: BattleEmotionSystem, enemy_emotion: BattleEmotionSystem):
        """화면 양쪽 위에 감정단계를 표시"""

        width, height = surface.get_size()

        box_w = 140
        box_h = 60
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

        # ----- 오른쪽 위: 아군 감정 -----
        px = width - box_w - margin
        py = margin

        pygame.draw.rect(surface, EMOTION_BG, (px, py, box_w, box_h), border_radius=8)
        pygame.draw.rect(surface, EMOTION_BORDER, (px, py, box_w, box_h), 2, border_radius=8)

        player_title = font.render("아군 감정", True, EMOTION_TEXT)
        surface.blit(player_title, (px + 10, py + 6))

        player_lv = font.render(f"Lv. {player_emotion.level}", True, EMOTION_TEXT)
        surface.blit(player_lv, (px + 10, py + 28))

        # (선택) 코인 표시도 넣고 싶으면 아래처럼 간단하게 점 두 줄 정도로 표현할 수 있음.
        # 지금은 감정단계만 필요한 것 같으니 생략해도 됨.

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
                    # 이번 막에서 아직 속도를 안 굴렸을 때만 동작
                    if not speed_rolled:
                        for u in all_units:
                            u.roll_speed()

                        # ✅ 속도 확정 후에 적들이 자동으로 아군을 타겟팅
                        plan_enemy_actions(enemy_group, ally_group)

                        speed_rolled = True

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
                            page = clicked_unit.planned_page
                            if page is not None:
                                clicked_unit.hand.append(page)
                            clicked_unit.planned_page = None
                            clicked_unit.planned_target = None
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

