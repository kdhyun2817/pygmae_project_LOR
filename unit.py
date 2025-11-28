# unit.py — Unit 클래스 전체 버전

import pygame
import random
import math
from enum import Enum, auto

# ----------------------------
# 색상 / UI 상수
# ----------------------------
ALLY_COLOR = (80, 160, 255)
ENEMY_COLOR = (255, 100, 100)

TOKEN_COLOR = (250, 230, 150)
TOKEN_BORDER = (200, 180, 100)

HP_BAR_COLOR = (200, 80, 80)
SP_BAR_COLOR = (80, 80, 200)
BAR_BG_COLOR = (60, 60, 60)

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
PANEL_BG = (20, 20, 30)

LIGHT_FULL_COLOR = (250, 230, 120)   # 빛이 있는 마름모 색
LIGHT_EMPTY_COLOR = (80, 80, 80)     # 빈 마름모 색
LIGHT_BORDER_COLOR = (20, 20, 20)    # 테두리


# ----------------------------
# 내성 / 데미지 타입
# ----------------------------
class ResistLevel(Enum):
    FATAL = "취약"
    WEAK = "약점"
    NORMAL = "보통"
    ENDURE = "견딤"
    RESIST = "내성"
    IMMUNE = "면역"

RESIST_MULTIPLIER = {
    ResistLevel.FATAL: 2.0,
    ResistLevel.WEAK: 1.5,
    ResistLevel.NORMAL: 1.0,
    ResistLevel.ENDURE: 0.5,
    ResistLevel.RESIST: 0.25,
    ResistLevel.IMMUNE: 0.0,
}

class DamageType(Enum):
    SLASH = auto()
    PIERCE = auto()
    BLUNT = auto()

DAMAGE_NAME_KO = {
    DamageType.SLASH: "참격",
    DamageType.PIERCE: "관통",
    DamageType.BLUNT: "타격",
}


# ----------------------------
# 주사위 종류
# ----------------------------
class DiceKind(Enum):
    ATTACK = auto()
    DEFENSE = auto()
    EVADE = auto()

# ----------------------------
# 상태이상
# ----------------------------
class StatusType(Enum):
    HASTE = auto()
    STRENGTH = auto()
    ENDURANCE = auto()
    PROTECT = auto()
    VULNERABLE = auto()
    FRAGILE = auto()
    PARALYSIS = auto()
    BLEED = auto()
    BURN = auto()
    BIND = auto()
    WEAK = auto()
    DISARM = auto()
    SMOKE = auto()
    CHARGE = auto()
    TARGET = auto()
    CORROSION = auto()
    STAGGER_PROTECT = auto()
    NAIL = auto()
    FAIRY = auto()
    FLARE = auto()
    LAST_STAND = auto()
    HP_HEAL = auto()   # 자원 계열
    LIGHT = auto()     # 자원 계열




# ----------------------------
# 상태이상 클래스
# ----------------------------
class StatusEffect:
    def __init__(self, status_type: StatusType, stacks: int, duration: int = 1):
        self.type = status_type
        self.stacks = stacks
        self.duration = duration

# ----------------------------
# Unit 클래스
# ----------------------------
class Unit(pygame.sprite.Sprite):
    def __init__(
        self,
        x, y,
        speed_min, speed_max,
        is_ally=True,
        image_path=None,
        max_hp=30.0,
        max_sp=20.0,
        hp_resist=None,
        sp_resist=None,




    ):
        super().__init__()

        # --- 기본 스탯 ---
        self.max_hp = float(max_hp)
        self.hp = float(max_hp)

        self.max_sp = float(max_sp)
        self.sp = float(max_sp)

        self.is_ally = is_ally
        self.is_dead = False
        self.is_escaped = False
        self.is_staggered = False
        self.can_act = True

        # 흐트러짐 회복까지 남은 막 수 (0이면 바로 회복 대상 아님)
        self.stagger_recover_scenes = 0

        # 🔹 속도 관련
        self.current_speed = None
        self.defense_speed = None
        self.speed_values = []

        # 🔹 토큰별 공격 계획: token_index -> {"page": CombatPage, "target": Unit}
        self.token_plans = {}

        # 🔹 이번 막에 공격에 사용 중인 토큰 인덱스(화살표 시작 위치용)
        self.attack_token_index = None

        # 🔹 이번 막에 방어에 사용 중인 토큰 인덱스(화살표 끝 위치용)
        self.defense_token_index = None

        # 전투 그룹 참조 (흐트러짐 시 동료에게 효과를 전달하는 기능 등에서 사용)
        self.ally_group = None
        self.enemy_group = None

        self.status_effects = []

        # --- 카드(책장) 시스템 ---
        # deck_all : 이 유닛이 전투 시작 시 가지고 있는 전체 책장 9장
        # draw_pile: 아직 뽑지 않은 덱 (기본적으로 deck_all 복사본)
        # hand     : 현재 손에 들고 있는 책장
        self.deck_all = []
        self.draw_pile = []
        self.hand = []

        # 이번 막 동안 이 유닛이 사용한 책장 수 (감정 5단계 추가 드로우 계산용)
        self.pages_used_this_scene = 0

        # 적 AI용: 이번 막에 사용할 예정인 책장과 타깃
        self.planned_page = None
        self.planned_target = None

        # --- 속도 주사위 개수 ---
        # 기본은 1개, 감정 4단계 이상에서 증가할 수 있다.
        self.speed_dice_count = 1

        # --- 빛 시스템 ---
        # 라오루 기준 기본은 3빛, 감정 1단계에서 +1 → 4빛 되는 구조
        self.max_light = 3
        self.light = 3

        # --- 빛 시스템 ---
        # 라오루 기준 기본은 3빛, 감정 1단계에서 +1 → 4빛 되는 구조
        self.max_light = 3
        self.light = 3

        # --- 빛 예약(플레이 계획용) ---
        # 여러 토큰이 책장을 예약할 때, 실제로는 나중에 소모되지만
        # UI 상에서는 미리 빠진 것처럼 보이게 하기 위한 임시 값
        self.light_reserved = 0  # 예약된 빛 총합
        self.light_reserved_per_token = {}  # token_index -> cost
        self.light_blink_timer = 0  # 빛 UI 깜빡임 시간(프레임 카운트)


        # --- 내성 (HP/SP 분리) ---
        default_resist = {
            DamageType.SLASH: ResistLevel.NORMAL,
            DamageType.PIERCE: ResistLevel.NORMAL,
            DamageType.BLUNT: ResistLevel.NORMAL,
        }

        if hp_resist is None:
            hp_resist = dict(default_resist)
        if sp_resist is None:
            sp_resist = dict(default_resist)

        self.hp_resist_base = dict(hp_resist)
        self.sp_resist_base = dict(sp_resist)

        self.hp_resist_cur = dict(hp_resist)
        self.sp_resist_cur = dict(sp_resist)

        # --- 속도 ---
        self.speed_min = speed_min
        self.speed_max = speed_max
        self.current_speed = None




        # --- 이미지 ---
        if image_path:
            self.image = pygame.image.load(image_path).convert_alpha()
            self.image = pygame.transform.scale(self.image, (80, 80))
        else:
            self.image = pygame.Surface((80, 80), pygame.SRCALPHA)
            self.image.fill(ALLY_COLOR if is_ally else ENEMY_COLOR)

        self.rect = self.image.get_rect(center=(x, y))

    # =============================
    # 속도 굴리기
    # =============================
    def roll_speed(self):
        """이번 막에서 이 유닛의 속도 주사위를 모두 굴린다.

        - self.speed_dice_count 개수만큼 speed_values 리스트에 저장
        - current_speed : 공격에 사용하는 '메인' 속도 (가장 높은 값)
        - defense_speed : 공격을 받을 때 기준이 되는 속도 (가장 낮은 값)
        """
        # speed_values 초기화 보장
        if getattr(self, "speed_values", None) is None:
            self.speed_values = []

        # 이미 굴려진 상태면 다시 굴리지 않는다.
        if self.current_speed is not None:
            return

        # 행동 불가 / 사망 / 도주 상태면 속도 0 취급
        if not self.can_act or self.is_dead or self.is_escaped:
            self.current_speed = None
            self.defense_speed = None
            self.speed_values = []
            return

        # 가속 / 속도저하 상태이상 반영
        speed_bonus = 0
        for st in self.status_effects:
            if st.type == StatusType.HASTE:
                speed_bonus += st.stacks
            if st.type == StatusType.BIND:
                speed_bonus -= st.stacks

        # 실제 주사위 굴리기
        self.speed_values = []
        dice_count = max(1, int(getattr(self, "speed_dice_count", 1)))
        for _ in range(dice_count):
            base = random.randint(self.speed_min, self.speed_max)
            val = max(1, base + speed_bonus)
            self.speed_values.append(val)

        if self.speed_values:
            # 🔹 공격용 메인 토큰 속도 (가장 높은 속도)
            self.current_speed = max(self.speed_values)
            # 🔹 방어용 토큰 속도 (가장 낮은 속도)
            self.defense_speed = min(self.speed_values)
            # 🔹 기본 공격/방어 토큰 인덱스도 같이 지정
            try:
                self.attack_token_index = self.speed_values.index(self.current_speed)
            except ValueError:
                self.attack_token_index = None
            try:
                self.defense_token_index = self.speed_values.index(self.defense_speed)
            except ValueError:
                self.defense_token_index = None
        else:
            self.current_speed = None
            self.defense_speed = None
            self.attack_token_index = None
            self.defense_token_index = None

    def reset_speed_for_new_turn(self):
        self.current_speed = None
        self.defense_speed = None
        self.speed_values = []
        self.attack_token_index = None
        self.defense_token_index = None
        self.token_plans = {}

        # 새 막 시작할 때 빛 예약도 초기화
        self.light_reserved = 0
        self.light_reserved_per_token = {}
        self.light_blink_timer = 0

    # =============================
    # 상태이상 리스트
    # =============================
    def add_status(self, status_type: StatusType, stacks: int, duration: int = 1):
        for st in self.status_effects:
            if st.type == status_type:
                st.stacks += stacks
                st.duration = max(st.duration, duration)
                return
        self.status_effects.append(StatusEffect(status_type, stacks, duration))

    # =============================
    # 빛 시스템: 획득 / 소모 / 회복
    # =============================
    def gain_light(self, amount: int):
        """빛을 얻는다. 최대 빛을 넘지 않도록 클램프."""
        if amount <= 0:
            return
        if self.max_light <= 0:
            return

        self.light += amount
        if self.light > self.max_light:
            self.light = self.max_light

    def spend_light(self, cost: int) -> bool:
        """빛을 소비. 충분하면 True, 부족하면 False."""
        if cost <= 0:
            return True
        if self.light >= cost:
            self.light -= cost
            return True
        return False

    def set_light_to_max(self):
        """현재 빛을 최대치로 맞춘다 (감정등급 상승 시 등에서 사용)."""
        if self.max_light > 0:
            self.light = self.max_light

    def increase_max_light(self, amount: int = 1, fill: bool = True):
        """
        최대 빛을 증가시킨다. 감정등급 상승 시 사용 예정.
        fill=True이면 현재 빛도 새 최대치로 채운다.
        """
        if amount <= 0:
            return
        self.max_light += amount
        if fill:
            self.light = self.max_light


    # =============================
    # 카드(책장) 관련 메서드
    # =============================
    def set_deck(self, pages):
        """
        이 유닛의 덱을 설정한다.
        pages: CombatPage 객체 9개(같은 페이지 여러 번 들어가도 됨).
        """
        # 전체 덱(정보용)과 실제 뽑기용 덱을 분리
        self.deck_all = list(pages)
        self.draw_pile = list(pages)
        self.hand = []

    def draw_cards(self, count: int):
        """
        덱에서 count장 만큼 뽑아 손패에 넣는다.

        - draw_pile이 비면 deck_all을 기준으로 다시 리필한다.
          (보유하고 있던 책장을 모두 소모하면 같은 구성을 다시 한 번 쓰는 느낌)
        - draw_pile과 deck_all이 모두 비어 있으면 더 이상 뽑지 않는다.
        """
        import random

        for _ in range(count):
            # 남은 덱이 없으면 한 번 리필 시도
            if not self.draw_pile:
                if self.deck_all:
                    # 원래 가지고 있던 책장 구성으로 다시 채움
                    self.draw_pile = list(self.deck_all)
                else:
                    # 애초에 덱이 없다면 더 이상 뽑을 수 없음
                    break

            if not self.draw_pile:
                break

            page = random.choice(self.draw_pile)
            self.draw_pile.remove(page)
            self.hand.append(page)

    # =============================
    # 데미지 처리
    # =============================
    def take_damage(self, amount, damage_type):
        """공격 주사위로 들어오는 피해 처리 (내성 + 상태이상 포함)"""

        if self.is_dead or self.is_escaped:
            return

        hp_resist_level = self.hp_resist_cur.get(damage_type, ResistLevel.NORMAL)
        sp_resist_level = self.sp_resist_cur.get(damage_type, ResistLevel.NORMAL)

        hp_mult = RESIST_MULTIPLIER[hp_resist_level]
        sp_mult = RESIST_MULTIPLIER[sp_resist_level]

        # 1. 내성 기반 기본 피해
        hp_damage = amount * hp_mult
        sp_damage = amount * sp_mult

        # 2. 취약/FRAGILE/VULNERABLE
        vuln_bonus = 0
        for st in self.status_effects:
            if st.type in (StatusType.FRAGILE, StatusType.VULNERABLE):
                vuln_bonus += st.stacks

        if vuln_bonus > 0:
            hp_damage *= (1 + vuln_bonus)
            sp_damage *= (1 + vuln_bonus)

        # 3. 표적 / 연기 / 부식 같은 "피해 증폭" 상태이상들
        # --- 표적(Target): +50%
        for st in self.status_effects:
            if st.type == StatusType.TARGET:
                hp_damage *= 1.5
                sp_damage *= 1.5

        # --- 연기(Smoke): 1스택당 +5%
        for st in self.status_effects:
            if st.type == StatusType.SMOKE:
                hp_damage *= (1 + 0.05 * st.stacks)
                sp_damage *= (1 + 0.05 * st.stacks)

        # --- 부식(Corrosion): 스택만큼 고정 추가
        for st in self.status_effects:
            if st.type == StatusType.CORROSION:
                hp_damage += st.stacks
                sp_damage += st.stacks

        # 4. 보호 / 흐트러짐 보호 (최종값에서 깎기)
        protect = 0
        stagger_protect = 0
        for st in self.status_effects:
            if st.type == StatusType.PROTECT:
                protect += st.stacks
            elif st.type == StatusType.STAGGER_PROTECT:
                stagger_protect += st.stacks

        hp_damage = max(0, hp_damage - protect)
        sp_damage = max(0, sp_damage - stagger_protect)

        # 5. 최종 피해 적용
        self.hp -= hp_damage
        self.sp -= sp_damage

        # 6. 못 / 요정 같은 "추가 직격 피해" (보호 무시)
        if damage_type == DamageType.BLUNT:
            for st in self.status_effects:
                if st.type == StatusType.NAIL:
                    extra = st.stacks * 5
                    self.hp -= extra
                    self.sp -= extra
                    st.stacks = 0

        for st in self.status_effects:
            if st.type == StatusType.FAIRY:
                self.hp -= st.stacks
                self.sp -= st.stacks

        # 7. 사망 / 흐트러짐 판정
        if self.hp <= 0 and not (self.is_dead or self.is_escaped):
            self.on_death(escaped=False)

        if self.sp <= 0 and (not self.is_staggered) and (not self.is_dead) and (not self.is_escaped):
            self.on_staggered()

    def take_hp_sp_direct(self, amount):
        """방어/회피 주사위용 – 내성 무시 HP/SP 데미지"""
        if self.is_dead or self.is_escaped:
            return
        self.hp -= amount
        self.sp -= amount

        if self.hp <= 0 and not (self.is_dead or self.is_escaped):
            self.on_death(False)
        if self.sp <= 0 and not self.is_staggered:
            self.on_staggered()

    def take_sp_direct(self, amount):
        """흐트러짐 피해"""
        if self.is_dead or self.is_escaped:
            return
        self.sp -= amount

        if self.sp <= 0 and not self.is_staggered:
            self.on_staggered()

    def recover_sp(self, amount):
        self.sp = min(self.sp + amount, self.max_sp)


    # =============================
    # 막 종료 판정
    # =============================
    def on_scene_end(self):
        to_remove = []

        for st in self.status_effects:

            # ----- 연기(Smoke) : 막 종료 시 1 감소 -----
            if st.type == StatusType.SMOKE:
                st.stacks -= 1
                if st.stacks <= 0:
                    to_remove.append(st)

            # ----- 부식(Corrosion) : 막 종료 시 부식스택만큼 피해 + 스택 1 감소 -----
            if st.type == StatusType.CORROSION:
                self.take_hp_sp_direct(st.stacks)
                st.stacks -= 1
                if st.stacks <= 0:
                    to_remove.append(st)

            # ----- 요정(Fairy) : 막 종료 시 요정스택만큼 피해 + 스택 절반 감소 -----
            if st.type == StatusType.FAIRY:
                self.take_hp_sp_direct(st.stacks)
                st.stacks //= 2
                if st.stacks <= 0:
                    to_remove.append(st)

            # ----- 표적(Target) 지속은 1막만 -----
            if st.type == StatusType.TARGET:
                st.duration -= 1
                if st.duration <= 0:
                    to_remove.append(st)

            # ----- 요원지화(Flare) : 흐트러짐 상태일 때 트리거됨 (나중에 expand) -----
            if st.type == StatusType.FLARE:
                st.duration -= 1
                if st.duration <= 0:
                    to_remove.append(st)

            # 기본 지속 시간 감소
            if hasattr(st, "duration"):
                st.duration -= 1
                if st.duration <= 0:
                    to_remove.append(st)

        for r in to_remove:
            if r in self.status_effects:
                self.status_effects.remove(r)

    # =============================
    # 사망 및 흐트러짐 판정
    # =============================
    def on_death(self, escaped=False):
        self.is_dead = (not escaped)
        self.is_escaped = escaped
        self.can_act = False
        self.current_speed = None

        # 끈질김(Last Stand)
        last_stand = None
        for st in self.status_effects:
            if st.type == StatusType.LAST_STAND:
                last_stand = st
                break

        if last_stand and not escaped:
            import random
            chance = 0.8 * (0.5 ** (last_stand.stacks - 1))  # 80%, 이후 절반씩 감소
            if random.random() < chance:
                self.hp = 30  # 부활
                last_stand.stacks += 1  # 부활 성공 → 스택 1 증가
                self.is_dead = False
                self.can_act = True
                self.is_staggered = False
                return

    def on_staggered(self):
        # 이미 흐트러져 있으면 다시 처리할 필요 없음
        if self.is_staggered:
            return

        self.is_staggered = True
        self.can_act = False
        self.current_speed = None

        # 🔹 다음 막 하나는 통째로 쉰 뒤, 그 다음 막에서 회복하도록
        #    (현재 막 + 다음 막 = 총 2막 동안 행동 불가)
        self.stagger_recover_scenes = 2

        for k in self.hp_resist_cur:
            self.hp_resist_cur[k] = ResistLevel.FATAL
        for k in self.sp_resist_cur:
            self.sp_resist_cur[k] = ResistLevel.FATAL

        # 요원지화 : 흐트러짐 시 화상 절반을 아군 전체에게 전달
        for st in self.status_effects:
            if st.type == StatusType.FLARE:
                burn_amount = 0
                for fx in self.status_effects:
                    if fx.type == StatusType.BURN:
                        burn_amount = fx.stacks // 2

                # 같은 편에게 화상 부여 (자기 제외)
                group = self.ally_group if self.is_ally else self.enemy_group
                for ally in group:
                    if ally is not self:
                        ally.add_status(StatusType.BURN, burn_amount)

    def recover_stagger_next_scene(self):
        """흐트러짐이 끝났을 때 실제로 회복시키는 함수."""
        if self.is_dead or self.is_escaped:
            return

        # 진짜 흐트러져 있을 때만 의미 있음
        if not self.is_staggered:
            return

        self.is_staggered = False
        self.can_act = True
        self.sp = self.max_sp
        self.stagger_recover_scenes = 0

        self.hp_resist_cur = dict(self.hp_resist_base)
        self.sp_resist_cur = dict(self.sp_resist_base)



    # =============================
    # UI 관련
    # =============================
    def get_speed_token_centers(self):
        """이 유닛의 속도 토큰(코인) 중심 좌표들을 반환한다."""
        n = max(1, int(getattr(self, "speed_dice_count", 1)))
        radius = 28
        centers = []
        # 가운데 기준으로 좌우로 배치
        for i in range(n):
            offset = (i - (n - 1) / 2.0) * (radius * 2 + 8)
            cx = self.rect.centerx + offset
            cy = self.rect.top - 40
            centers.append((cx, cy))
        return centers

    def draw_speed_token(self, surface, font):
        """속도 토큰(여러 개일 수 있음)을 그린다."""
        centers = self.get_speed_token_centers()
        radius = 28

        # 표시 텍스트를 위해 미리 상태 플래그 확인
        if self.is_dead:
            base_state_text = "사망"
        elif self.is_escaped:
            base_state_text = "도주"
        elif self.is_staggered:
            base_state_text = "흐트러짐!"
        else:
            base_state_text = None

        # 아직 속도를 안 굴렸으면 범위만 표시
        if base_state_text is None:
            if not getattr(self, "speed_values", None):
                base_text = f"{self.speed_min}-{self.speed_max}"
                texts = [base_text for _ in centers]
            else:
                # 굴려진 경우 각 토큰마다 실제 속도 표시
                texts = []
                for i in range(len(centers)):
                    if i < len(self.speed_values):
                        texts.append(str(self.speed_values[i]))
                    else:
                        texts.append(f"{self.speed_min}-{self.speed_max}")
        else:
            # 사망/도주/흐트러짐이면 모든 토큰에 같은 텍스트
            texts = [base_state_text for _ in centers]

        # 실제 그리기
        for idx, (cx, cy) in enumerate(centers):
            hex_points = []
            for k in range(6):
                ang = math.radians(60 * k - 30)
                x = cx + radius * math.cos(ang)
                y = cy + radius * math.sin(ang)
                hex_points.append((x, y))

            pygame.draw.polygon(surface, TOKEN_COLOR, hex_points)
            pygame.draw.polygon(surface, TOKEN_BORDER, hex_points, 3)

            token_text = texts[idx]
            surf = font.render(token_text, True, (0, 0, 0))
            surface.blit(surf, surf.get_rect(center=(cx, cy)))

    def draw_hp_sp_bar(self, surface):
        bar_width = 80
        bar_height = 6

        x = self.rect.centerx - bar_width // 2
        y_hp = self.rect.bottom + 4
        y_sp = self.rect.bottom + 14

        # HP
        ratio_hp = max(self.hp, 0) / self.max_hp
        pygame.draw.rect(surface, BAR_BG_COLOR, (x, y_hp, bar_width, bar_height))
        pygame.draw.rect(surface, HP_BAR_COLOR, (x, y_hp, int(bar_width * ratio_hp), bar_height))

        # SP
        ratio_sp = max(self.sp, 0) / self.max_sp
        pygame.draw.rect(surface, BAR_BG_COLOR, (x, y_sp, bar_width, bar_height))
        pygame.draw.rect(surface, SP_BAR_COLOR, (x, y_sp, int(bar_width * ratio_sp), bar_height))

    def draw_light(self, surface):
        """머리 위에 빛(마름모)를 그린다."""
        if self.max_light <= 0:
            return

        spacing = 16
        size = 4

        total_width = (self.max_light - 1) * spacing
        start_x = self.rect.centerx - total_width / 2
        y = self.rect.top - 12

        # 🔹 실제 논리상의 빛(self.light)은 건들지 않고,
        #     '예약된 빛(light_reserved)'만큼 UI에서 미리 빠진 것처럼 보이게 한다.
        reserved = getattr(self, "light_reserved", 0)
        effective_light = max(0, self.light - reserved)

        # 🔹 깜빡임: 예약이 갓 생겼을 때 일정 시간 동안 반짝이게
        # 🔹 깜빡임: 예약된 빛이 있는 동안 계속 반짝이게
        blink_on = False
        if reserved > 0:
            # pygame 전체 시간 기준으로 on/off (약 0.2초 주기)
            ticks = pygame.time.get_ticks()
            if (ticks // 200) % 2 == 0:
                blink_on = True

        # 몇 개가 예약되어 있는지 (빈 칸 중 깜빡일 개수)
        reserved_count = int(reserved)

        for i in range(self.max_light):
            cx = start_x + i * spacing
            points = [
                (cx, y - size),
                (cx + size, y),
                (cx, y + size),
                (cx - size, y),
            ]

            if i < int(effective_light):
                # 실제 사용 가능한 빛 부분
                fill_color = LIGHT_FULL_COLOR
            else:
                # 여기부터는 빈 칸
                fill_color = LIGHT_EMPTY_COLOR

                # 빈 칸 중에서 '예약된 빛' 만큼은 깜빡이게
                # 예: effective_light = 2, reserved = 1 → i == 2인 칸이 깜빡
                if (blink_on and
                        i >= int(effective_light) and
                        i < int(effective_light) + reserved_count):
                    fill_color = (255, 255, 200)  # 조금 더 밝게 반짝

            pygame.draw.polygon(surface, fill_color, points)
            pygame.draw.polygon(surface, LIGHT_BORDER_COLOR, points, 1)


    def draw(self, surface, font):
        surface.blit(self.image, self.rect)
        self.draw_speed_token(surface, font)
        self.draw_hp_sp_bar(surface)
        self.draw_light(surface)



