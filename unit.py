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

        # 전투 그룹 참조 (흐트러짐 시 동료에게 효과를 전달하는 기능 등에서 사용)
        self.ally_group = None
        self.enemy_group = None

        self.status_effects = []

        # --- 빛 시스템 ---
        # 라오루 기준 기본은 3빛, 감정 1단계에서 +1 → 4빛 되는 구조
        self.max_light = 3
        self.light = 3

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
        # --- 신속 / 속박 상태이상 적용 ---
        speed_bonus = 0
        for st in self.status_effects:
            if st.type == StatusType.HASTE:
                speed_bonus += st.stacks
            if st.type == StatusType.BIND:
                speed_bonus -= st.stacks

        if self.current_speed is not None:
            return
        if not self.can_act or self.is_dead or self.is_escaped:
            self.current_speed = None
        else:
            self.current_speed = random.randint(self.speed_min, self.speed_max)

        self.current_speed = max(1, self.current_speed + speed_bonus)


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

        # 2. 취약(FRAGILE)
        fragile_bonus = 0
        for st in self.status_effects:
            if st.type == StatusType.FRAGILE:
                fragile_bonus += st.stacks
        if fragile_bonus > 0:
            hp_damage *= (1 + fragile_bonus)
            sp_damage *= (1 + fragile_bonus)

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
        self.is_staggered = True
        self.can_act = False
        self.current_speed = None

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
        if self.is_dead or self.is_escaped:
            return
        self.is_staggered = False
        self.can_act = True
        self.sp = self.max_sp

        self.hp_resist_cur = dict(self.hp_resist_base)
        self.sp_resist_cur = dict(self.sp_resist_base)

    # =============================
    # UI 관련
    # =============================
    def draw_speed_token(self, surface, font):
        cx = self.rect.centerx
        cy = self.rect.top - 40

        radius = 28
        hex_points = []
        for i in range(6):
            ang = math.radians(60 * i - 30)
            x = cx + radius * math.cos(ang)
            y = cy + radius * math.sin(ang)
            hex_points.append((x, y))

        pygame.draw.polygon(surface, TOKEN_COLOR, hex_points)
        pygame.draw.polygon(surface, TOKEN_BORDER, hex_points, 3)

        if self.is_dead:
            text = "사망"
        elif self.is_escaped:
            text = "도주"
        elif self.is_staggered:
            text = "흐트러짐!"
        elif self.current_speed is None:
            text = f"{self.speed_min}-{self.speed_max}"
        else:
            text = str(self.current_speed)

        surf = font.render(text, True, BLACK)
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

        # 마름모들 간 간격과 크기
        spacing = 16   # 마름모 사이 간격
        size = 4       # 마름모 한 변의 '반' 길이

        # 전체 너비 계산해 가운데 정렬
        total_width = (self.max_light - 1) * spacing
        start_x = self.rect.centerx - total_width / 2

        # 위치: 캐릭터 머리 조금 위 (속도 토큰보다 약간 아래/위는 취향대로)
        y = self.rect.top - 12

        for i in range(self.max_light):
            cx = start_x + i * spacing
            points = [
                (cx, y - size),       # 위
                (cx + size, y),       # 오른쪽
                (cx, y + size),       # 아래
                (cx - size, y),       # 왼쪽
            ]

            # 현재 빛 개수만큼은 채운 색, 나머지는 빈 색
            if i < int(self.light):
                fill_color = LIGHT_FULL_COLOR
            else:
                fill_color = LIGHT_EMPTY_COLOR

            pygame.draw.polygon(surface, fill_color, points)
            pygame.draw.polygon(surface, LIGHT_BORDER_COLOR, points, 1)


    def draw(self, surface, font):
        surface.blit(self.image, self.rect)
        self.draw_speed_token(surface, font)
        self.draw_hp_sp_bar(surface)
        self.draw_light(surface)



