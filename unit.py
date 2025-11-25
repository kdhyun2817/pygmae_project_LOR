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

class DiceKind(Enum):
    ATTACK = auto()
    DEFENSE = auto()
    EVADE = auto()


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
        if self.current_speed is not None:
            return
        if not self.can_act or self.is_dead or self.is_escaped:
            self.current_speed = None
        else:
            self.current_speed = random.randint(self.speed_min, self.speed_max)

    # =============================
    # 데미지 처리
    # =============================
    def take_damage(self, amount, damage_type):
        """공격 주사위용 – 내성 적용 HP/SP 동시 데미지"""
        if self.is_dead or self.is_escaped:
            return

        # HP
        hp_lv = self.hp_resist_cur.get(damage_type, ResistLevel.NORMAL)
        hp_mult = RESIST_MULTIPLIER[hp_lv]
        self.hp -= amount * hp_mult

        # SP
        sp_lv = self.sp_resist_cur.get(damage_type, ResistLevel.NORMAL)
        sp_mult = RESIST_MULTIPLIER[sp_lv]
        self.sp -= amount * sp_mult

        # 사망/흐트러짐 판정
        if self.hp <= 0 and not (self.is_dead or self.is_escaped):
            self.on_death(False)
        if self.sp <= 0 and not self.is_staggered:
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
    # 상태 변화
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
        self.value = random.randint(self.min_value, self.max_value)
        return self.value
