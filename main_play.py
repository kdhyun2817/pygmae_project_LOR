import pygame
import random
import math
from enum import Enum, auto

# =========================
#  내성 / 데미지 타입 정의
# =========================

class ResistLevel(Enum):
    FATAL = "취약"     # 2.0배
    WEAK = "약점"      # 1.5배
    NORMAL = "보통"    # 1.0배
    ENDURE = "견딤"    # 0.5배
    RESIST = "내성"    # 0.25배
    IMMUNE = "면역"    # 0.0배


RESIST_MULTIPLIER = {
    ResistLevel.FATAL: 2.0,
    ResistLevel.WEAK: 1.5,
    ResistLevel.NORMAL: 1.0,
    ResistLevel.ENDURE: 0.5,
    ResistLevel.RESIST: 0.25,
    ResistLevel.IMMUNE: 0.0,
}


class DamageType(Enum):
    SLASH = auto()    # 참격
    PIERCE = auto()   # 관통
    BLUNT = auto()    # 타격


# 화면에 표시용 한글 이름
DAMAGE_NAME_KO = {
    DamageType.SLASH: "참격",
    DamageType.PIERCE: "관통",
    DamageType.BLUNT: "타격",
}


# =========================
#  색상
# =========================

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


# =========================
#  Unit 클래스
# =========================

class Unit(pygame.sprite.Sprite):
    """
    라오루 스타일 전투용 유닛
    """

    def __init__(
        self,
        x,
        y,
        speed_min,
        speed_max,
        is_ally=True,
        image_path=None,
        max_hp=30.0,
        max_sp=20.0,
        hp_resist=None,
        sp_resist=None,
    ):
        super().__init__()

        # ---------- 기본 스탯 ----------
        self.max_hp = float(max_hp)
        self.hp = float(max_hp)

        self.max_sp = float(max_sp)
        self.sp = float(max_sp)

        self.is_ally = is_ally
        self.is_dead = False
        self.is_escaped = False
        self.is_staggered = False
        self.can_act = True

        # ---------- 내성 테이블 ----------
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

        # ---------- 속도 ----------
        self.speed_min = speed_min
        self.speed_max = speed_max
        self.current_speed = None

        # ---------- 이미지 ----------
        if image_path:
            self.image = pygame.image.load(image_path).convert_alpha()
            self.image = pygame.transform.scale(self.image, (80, 80))
        else:
            self.image = pygame.Surface((80, 80), pygame.SRCALPHA)
            color = ALLY_COLOR if is_ally else ENEMY_COLOR
            self.image.fill(color)

        self.rect = self.image.get_rect(center=(x, y))

    # =========================
    #  속도
    # =========================
    def roll_speed(self):
        if not self.can_act or self.is_dead or self.is_escaped:
            self.current_speed = None
        else:
            self.current_speed = random.randint(self.speed_min, self.speed_max)

    # =========================
    #  데미지 처리
    # =========================
    def take_damage(self, amount, damage_type):
        """한 번의 공격으로 HP/SP 둘 다 감소"""

        if self.is_dead or self.is_escaped:
            return

        # HP
        hp_resist_level = self.hp_resist_cur.get(damage_type, ResistLevel.NORMAL)
        hp_mult = RESIST_MULTIPLIER[hp_resist_level]
        hp_damage = amount * hp_mult
        self.hp -= hp_damage

        # SP
        sp_resist_level = self.sp_resist_cur.get(damage_type, ResistLevel.NORMAL)
        sp_mult = RESIST_MULTIPLIER[sp_resist_level]
        sp_damage = amount * sp_mult
        self.sp -= sp_damage

        # HP 0 → 사망/도주
        if self.hp <= 0 and not (self.is_dead or self.is_escaped):
            self.on_death(escaped=False)

        # SP 0 → 흐트러짐
        if self.sp <= 0 and (not self.is_staggered) and (not self.is_dead) and (not self.is_escaped):
            self.on_staggered()

    def on_death(self, escaped=False):
        self.is_dead = (not escaped)
        self.is_escaped = escaped
        self.can_act = False
        self.current_speed = None

    def on_staggered(self):
        self.is_staggered = True
        self.can_act = False
        self.current_speed = None

        # 내성 전부 취약으로 변경
        for k in self.hp_resist_cur.keys():
            self.hp_resist_cur[k] = ResistLevel.FATAL
        for k in self.sp_resist_cur.keys():
            self.sp_resist_cur[k] = ResistLevel.FATAL

    def recover_stagger_next_scene(self):
        if self.is_dead or self.is_escaped:
            return

        self.is_staggered = False
        self.can_act = True
        self.sp = self.max_sp

        self.hp_resist_cur = dict(self.hp_resist_base)
        self.sp_resist_cur = dict(self.sp_resist_base)

    # =========================
    #  Pygame 표시 관련
    # =========================
    def update(self):
        pass

    def draw_speed_token(self, surface, font):
        token_center_x = self.rect.centerx
        token_center_y = self.rect.top - 40

        radius = 28
        points = []
        for i in range(6):
            angle_deg = 60 * i - 30
            angle_rad = math.radians(angle_deg)
            px = token_center_x + radius * math.cos(angle_rad)
            py = token_center_y + radius * math.sin(angle_rad)
            points.append((px, py))

        pygame.draw.polygon(surface, TOKEN_COLOR, points)
        pygame.draw.polygon(surface, TOKEN_BORDER, points, 3)

        if self.is_dead:
            text_str = "사망"
        elif self.is_escaped:
            text_str = "도주"
        elif self.is_staggered:
            text_str = "흐트러짐!"
        elif self.current_speed is None:
            text_str = f"{self.speed_min}-{self.speed_max}"
        else:
            text_str = str(self.current_speed)

        text_surf = font.render(text_str, True, BLACK)
        text_rect = text_surf.get_rect(center=(token_center_x, token_center_y))
        surface.blit(text_surf, text_rect)

    def draw_hp_sp_bar(self, surface):
        bar_width = 80
        bar_height = 6
        x = self.rect.centerx - bar_width // 2
        y_hp = self.rect.bottom + 4
        y_sp = self.rect.bottom + 14

        # HP 바
        hp_ratio = max(self.hp, 0) / self.max_hp if self.max_hp > 0 else 0
        pygame.draw.rect(surface, BAR_BG_COLOR, (x, y_hp, bar_width, bar_height))
        pygame.draw.rect(
            surface,
            HP_BAR_COLOR,
            (x, y_hp, int(bar_width * hp_ratio), bar_height),
        )

        # SP 바
        sp_ratio = max(self.sp, 0) / self.max_sp if self.max_sp > 0 else 0
        pygame.draw.rect(surface, BAR_BG_COLOR, (x, y_sp, bar_width, bar_height))
        pygame.draw.rect(
            surface,
            SP_BAR_COLOR,
            (x, y_sp, int(bar_width * sp_ratio), bar_height),
        )

    def draw(self, surface, font):
        surface.blit(self.image, self.rect)
        self.draw_speed_token(surface, font)
        self.draw_hp_sp_bar(surface)


# =========================
#  유닛 생성 헬퍼
# =========================

def create_units():
    ally_group = pygame.sprite.Group()
    enemy_group = pygame.sprite.Group()

    # 아군 3명 (그냥 그대로 둬도 됨)
    ally_positions = [(250, 450), (450, 450), (650, 450)]
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

    # ===== 적 3명: 서로 다른 수치로 설정 =====
    enemy_specs = [
        # 1번 적: 참격 HP 취약 / SP 견딤, 체력 많고 속도 느림
        {
            "pos": (250, 200),
            "max_hp": 50,
            "max_sp": 20,
            "speed_min": 1,
            "speed_max": 3,
            "hp_res": {
                DamageType.SLASH: ResistLevel.FATAL,
                DamageType.PIERCE: ResistLevel.NORMAL,
                DamageType.BLUNT: ResistLevel.ENDURE,
            },
            "sp_res": {
                DamageType.SLASH: ResistLevel.ENDURE,
                DamageType.PIERCE: ResistLevel.NORMAL,
                DamageType.BLUNT: ResistLevel.NORMAL,
            },
        },
        # 2번 적: 관통에 약한 유리캐, 속도 빠름
        {
            "pos": (450, 200),
            "max_hp": 35,
            "max_sp": 25,
            "speed_min": 3,
            "speed_max": 6,
            "hp_res": {
                DamageType.SLASH: ResistLevel.NORMAL,
                DamageType.PIERCE: ResistLevel.FATAL,
                DamageType.BLUNT: ResistLevel.NORMAL,
            },
            "sp_res": {
                DamageType.SLASH: ResistLevel.NORMAL,
                DamageType.PIERCE: ResistLevel.WEAK,
                DamageType.BLUNT: ResistLevel.ENDURE,
            },
        },
        # 3번 적: 둔기에 강하고 SP가 튼튼한 탱커형
        {
            "pos": (650, 200),
            "max_hp": 45,
            "max_sp": 30,
            "speed_min": 2,
            "speed_max": 4,
            "hp_res": {
                DamageType.SLASH: ResistLevel.NORMAL,
                DamageType.PIERCE: ResistLevel.ENDURE,
                DamageType.BLUNT: ResistLevel.RESIST,
            },
            "sp_res": {
                DamageType.SLASH: ResistLevel.ENDURE,
                DamageType.PIERCE: ResistLevel.NORMAL,
                DamageType.BLUNT: ResistLevel.RESIST,
            },
        },
    ]

    for spec in enemy_specs:
        x, y = spec["pos"]
        u = Unit(
            x, y,
            spec["speed_min"], spec["speed_max"],
            False,              # is_ally=False (적)
            None,               # image_path (나중에 교체 가능)
            spec["max_hp"],
            spec["max_sp"],
            spec["hp_res"],
            spec["sp_res"],
        )
        enemy_group.add(u)

    return ally_group, enemy_group


# =========================
#  선택된 유닛 내성 표시 UI
# =========================

def draw_selected_unit_panel(surface, font, selected_unit):
    """화면 오른쪽에 선택된 유닛의 내성 정보 패널 그리기"""
    if selected_unit is None:
        return

    panel_x = 620
    panel_y = 80
    panel_w = 260
    panel_h = 200

    # 패널 배경
    pygame.draw.rect(surface, PANEL_BG, (panel_x, panel_y, panel_w, panel_h))
    pygame.draw.rect(surface, WHITE, (panel_x, panel_y, panel_w, panel_h), 2)

    lines = []

    # 제목
    side = "아군" if selected_unit.is_ally else "적"
    lines.append(f"[선택된 캐릭터] ({side})")

    # HP / SP / 상태
    lines.append(f"HP: {int(max(selected_unit.hp, 0))}/{int(selected_unit.max_hp)}")
    lines.append(f"SP: {int(max(selected_unit.sp, 0))}/{int(selected_unit.max_sp)}")

    if selected_unit.is_dead:
        lines.append("상태: 사망")
    elif selected_unit.is_escaped:
        lines.append("상태: 도주")
    elif selected_unit.is_staggered:
        lines.append("상태: 흐트러짐")
    else:
        lines.append("상태: 정상")

    lines.append("")  # 빈 줄
    lines.append("[내성 정보] (HP / SP)")

    # 각 속성별 내성
    for dmg_type in DamageType:
        name = DAMAGE_NAME_KO[dmg_type]
        hp_lv = selected_unit.hp_resist_cur.get(dmg_type, ResistLevel.NORMAL).value
        sp_lv = selected_unit.sp_resist_cur.get(dmg_type, ResistLevel.NORMAL).value
        lines.append(f"{name}: HP {hp_lv} / SP {sp_lv}")

    # 텍스트 출력
    offset_y = 8
    for text in lines:
        surf = font.render(text, True, WHITE)
        surface.blit(surf, (panel_x + 10, panel_y + offset_y))
        offset_y += 22


# =========================
#  메인 루프
# =========================

def main():
    pygame.init()
    screen = pygame.display.set_mode((900, 600))
    pygame.display.set_caption("라오루 스타일 전투 프로토타입")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("malgungothic", 22)

    ally_group, enemy_group = create_units()
    all_units = pygame.sprite.Group()
    all_units.add(ally_group)
    all_units.add(enemy_group)

    selected_unit = None  # 클릭해서 선택된 유닛

    running = True
    while running:
        dt = clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # 키 입력
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                # 스페이스: 속도 굴리기
                if event.key == pygame.K_SPACE:
                    for u in all_units:
                        u.roll_speed()

                # A 키: 적 전체에게 참격 10 데미지 테스트
                if event.key == pygame.K_a:
                    for e in enemy_group:
                        e.take_damage(10, DamageType.SLASH)

            # 마우스 클릭으로 유닛 선택
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_pos = event.pos
                clicked = None
                for u in all_units:
                    if u.rect.collidepoint(mouse_pos):
                        clicked = u
                        break
                selected_unit = clicked  # 아무 것도 안 눌렀으면 None으로 됨

        # 업데이트
        all_units.update()

        # 그리기
        screen.fill((30, 30, 40))
        info1 = font.render("좌클릭: 캐릭터 선택 / SPACE: 속도 / A: 적 참격 10 / ESC: 종료", True, WHITE)
        screen.blit(info1, (20, 20))

        for u in all_units:
            u.draw(screen, font)

        # 선택된 유닛 내성 패널
        draw_selected_unit_panel(screen, font, selected_unit)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
