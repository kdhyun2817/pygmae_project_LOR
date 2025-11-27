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


def draw_speed_hover_info(surface, font, hovered_speed_unit):
    """
    속도 코인 위에 마우스를 올렸을 때 표시할 정보.
    - 아군: 현재 손패(뽑아서 들고 있는 책장들)
    - 적군: 이번 막에 사용 예정인 공격(책장)
    """
    if hovered_speed_unit is None:
        return

    width, height = surface.get_size()
    center_x = width // 2
    base_y = height - 40  # 화면 아래쪽 위치

    if hovered_speed_unit.is_ally:
        # ✅ 아군: '전체 덱'이 아니라 '현재 손패'만 표시
        hand = getattr(hovered_speed_unit, "hand", None)
        if hand:
            names = [p.name for p in hand]
            text = "현재 손패: " + " / ".join(names)
        else:
            text = "현재 손패가 없습니다."
    else:
        # ✅ 적: 이번 막에 사용하려는 공격 책장
        planned = getattr(hovered_speed_unit, "planned_page", None)
        if planned is not None:
            text = f"현재 예정 공격: {planned.name} (코스트 {planned.cost})"
        else:
            text = "현재 예정된 공격이 없습니다."

    info_surf = font.render(text, True, WHITE)
    surface.blit(
        info_surf,
        (center_x - info_surf.get_width() // 2, base_y),
    )



def draw_enemy_target_arrows(surface, enemy_group):
    """
    적 유닛이 계획한 공격 방향을 빨간색 포물선 화살표로 그린다.
    - 시작점: 적 유닛의 속도 코인 중심
    - 끝점: 공격 대상 아군 유닛의 속도 코인 중심
    """
    ARROW_COLOR = (255, 80, 80)

    for e in enemy_group:
        target = getattr(e, "planned_target", None)
        if target is None:
            continue
        if e.is_dead or e.is_escaped:
            continue
        if target.is_dead or target.is_escaped:
            continue

        # 1) 시작/끝점: 각 유닛의 "속도 코인" 중심
        start = (e.rect.centerx, e.rect.top - 40)
        end = (target.rect.centerx, target.rect.top - 40)

        sx, sy = start
        ex, ey = end

        # 2) 포물선(Bezier 곡선) 제어점 설정
        #    중간 지점을 기준으로 살짝 위로 들어올려서 '∩' 모양으로 보이게 함
        mx = (sx + ex) / 2
        my = (sy + ey) / 2

        # 위로 80픽셀 정도 들어올리기 (필요하면 숫자 조정)
        control = (mx, my - 80)

        # 3) 베지어 곡선 점들 계산
        points = []
        steps = 20  # 선분 개수 (값 늘리면 더 부드러워짐)
        for i in range(steps + 1):
            t = i / steps
            # 2차 Bezier: B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
            x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * control[0] + t ** 2 * ex
            y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * control[1] + t ** 2 * ey
            points.append((x, y))

        # 4) 포인트들을 선분으로 이어서 곡선 그리기
        for i in range(len(points) - 1):
            pygame.draw.line(surface, ARROW_COLOR, points[i], points[i + 1], 3)

        # 5) 화살촉: 곡선 마지막 두 점의 방향을 이용해서 삼각형 그리기
        if len(points) >= 2:
            x1, y1 = points[-2]
            x2, y2 = points[-1]
            dx = x2 - x1
            dy = y2 - y1
            length = max((dx * dx + dy * dy) ** 0.5, 1)
            ux, uy = dx / length, dy / length  # 단위 방향 벡터

            # 화살촉 기준점 (끝점에서 약간 뒤쪽)
            base_x = x2 - ux * 12
            base_y = y2 - uy * 12

            # 좌우로 벌어진 두 점 (수직 벡터 사용)
            perp_x, perp_y = -uy, ux
            left = (base_x + perp_x * 6, base_y + perp_y * 6)
            right = (base_x - perp_x * 6, base_y - perp_y * 6)

            pygame.draw.polygon(surface, ARROW_COLOR, [(x2, y2), left, right])




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

    show_enemy_arrows = False  # 1번 키로 토글하는 표시 여부

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

            # ✅ 새 막 시작 시 적 행동 계획 세우기
            plan_enemy_actions(enemy_group, ally_group)

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
                    # 한 번만 속도 정해지게 Unit.roll_speed에 로직 넣어둔 상태
                    for u in all_units:
                        u.roll_speed()

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

        # 1) 본체 스프라이트 기준 hover (오른쪽 패널용)
        for u in all_units:
            if u.rect.collidepoint(mouse_pos):
                hovered_unit = u
                break

        # 2) 속도 코인 기준 hover (손패/예정 공격 표시용)
        for u in all_units:
            # speed token 중심과 반지름은 unit.draw_speed_token과 동일하게 사용
            cx = u.rect.centerx
            cy = u.rect.top - 40
            radius = 28

            dx = mouse_pos[0] - cx
            dy = mouse_pos[1] - cy
            if dx * dx + dy * dy <= radius * radius:
                hovered_speed_unit = u
                break

        # 그리기
        screen.fill((30, 30, 40))

        # 상단 정보 텍스트
        info = font.render(
            f"스테이지: {stage_code} / 막: {scene_index} / SPACE: 속도 / A: 적 참격 / C: 합 테스트 / N: 다음 막 / ESC: 전투 종료",
            True, WHITE
        )
        screen.blit(info, (20, 20))

        # ✅ 감정 UI 그리기
        draw_emotion_ui(screen, font, player_emotion, enemy_emotion)

        # 유닛들 그리기
        for u in all_units:
            u.draw(screen, font)

        # ✅ 적 → 아군 공격 방향 화살표
        if show_enemy_arrows:
            draw_enemy_target_arrows(screen, enemy_group)

        # 마우스 올린 유닛 정보 패널
        draw_unit_info_panel(screen, font, hovered_unit)

        # 속도 코인 위에 마우스를 올렸을 때 손패/예정 공격 표시
        draw_speed_hover_info(screen, font, hovered_speed_unit)

        pygame.display.flip()

    return result

