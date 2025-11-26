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
    BURN = auto()          # 화상
    PARALYSIS = auto()     # 마비
    BLEED = auto()         # 출혈
    PROTECT = auto()       # 보호
    STAGGER_PROTECT = auto() # 흐트러짐 보호
    STRENGTH = auto()      # 힘
    ENDURANCE = auto()     # 인내
    HASTE = auto()         # 신속
    FRAGILE = auto()       # 취약
    WEAK = auto()          # 허약
    DISARM = auto()        # 무장 해제
    BIND = auto()          # 속박

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

        self.status_effects=[]


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
    # 데미지 처리
    # =============================
    def take_damage(self, amount, damage_type):
        """공격 주사위로 들어오는 피해 처리 (내성 + 상태이상 포함)"""

        if self.is_dead or self.is_escaped:
            return

        # 1) 내성에 따른 기본 피해 계산
        hp_resist_level = self.hp_resist_cur.get(damage_type, ResistLevel.NORMAL)
        sp_resist_level = self.sp_resist_cur.get(damage_type, ResistLevel.NORMAL)

        hp_mult = RESIST_MULTIPLIER[hp_resist_level]
        sp_mult = RESIST_MULTIPLIER[sp_resist_level]

        hp_damage = amount * hp_mult
        sp_damage = amount * sp_mult

        # 2) 취약(FRAGILE) → 피해량 증가
        fragile_bonus = 0
        for st in self.status_effects:
            if st.type == StatusType.FRAGILE:
                fragile_bonus += st.stacks

        if fragile_bonus > 0:
            hp_damage *= (1 + fragile_bonus)
            sp_damage *= (1 + fragile_bonus)

        # 3) 보호(PROTECT) / 흐트러짐 보호(STAGGER_PROTECT) → 피해량 감소
        protect = 0
        stagger_protect = 0
        for st in self.status_effects:
            if st.type == StatusType.PROTECT:
                protect += st.stacks
            elif st.type == StatusType.STAGGER_PROTECT:
                stagger_protect += st.stacks

        hp_damage = max(0, hp_damage - protect)
        sp_damage = max(0, sp_damage - stagger_protect)

        # 4) 실제 HP/SP 적용
        self.hp -= hp_damage
        self.sp -= sp_damage

        # 5) 사망 / 흐트러짐 판정
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

            # --- 화상 ---
            if st.type == StatusType.BURN:
                dmg = st.stacks
                self.take_hp_sp_direct(dmg)
                st.stacks = st.stacks * 2 // 3  # 2/3 소수점 버림

            # --- 출혈 (막 종료 시 감소) ---
            if st.type == StatusType.BLEED:
                st.stacks = (st.stacks * 2 + 2) // 3  # 2/3 소수점 올림

            # 턴 지속 시간 감소
            st.duration -= 1
            if st.duration <= 0 or st.stacks <= 0:
                to_remove.append(st)

        for st in to_remove:
            self.status_effects.remove(st)

    # =============================
    # 사망 및 흐트러짐 판정
    # =============================
    def on_death(self, escaped=False):
        self.is_dead = (not escaped)
        self.is_escaped = escaped
        self.can_act = False
        self.current_speed = None

    def on_staggered(self):
        self.is_staggered = True
        self.can_act = False
        self.current_speed = None

        for k in self.hp_resist_cur:
            self.hp_resist_cur[k] = ResistLevel.FATAL
        for k in self.sp_resist_cur:
            self.sp_resist_cur[k] = ResistLevel.FATAL

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

    def draw(self, surface, font):
        surface.blit(self.image, self.rect)
        self.draw_speed_token(surface, font)
        self.draw_hp_sp_bar(surface)



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

