# lobby_scene.py
import pygame
from unit import WHITE, PANEL_BG
from stages import STAGES


def run_lobby(screen):
    clock = pygame.time.Clock()
    font_title = pygame.font.SysFont("malgungothic", 44)
    font_item = pygame.font.SysFont("malgungothic", 28)
    font_hint = pygame.font.SysFont("malgungothic", 20)

    stage_codes = list(STAGES.keys())
    if not stage_codes:
        print("[경고] STAGES가 비어 있습니다.")
        return None

    selected = 0
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None

            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    # 메인 메뉴로 돌아가기
                    return None

                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(stage_codes)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(stage_codes)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    # 선택된 스테이지 코드 반환
                    return stage_codes[selected]

        # ----- 화면 그리기 -----
        screen.fill(PANEL_BG)

        # 제목
        title_surf = font_title.render("스테이지 선택", True, WHITE)
        title_rect = title_surf.get_rect(center=(screen.get_width() // 2, 100))
        screen.blit(title_surf, title_rect)

        # 스테이지 리스트
        cx = screen.get_width() // 2
        start_y = 200
        gap = 50

        for i, code in enumerate(stage_codes):
            text = f"{i + 1}. {code}"
            color = WHITE
            surf = font_item.render(text, True, color)
            rect = surf.get_rect(center=(cx, start_y + i * gap))

            if i == selected:
                pygame.draw.rect(
                    screen,
                    (220, 220, 240),
                    rect.inflate(40, 10),
                    width=2,
                )

            screen.blit(surf, rect)

        # 하단 힌트
        hint_text = "↑/↓ : 선택  |  Enter : 전투 시작  |  ESC : 뒤로"
        hint_surf = font_hint.render(hint_text, True, WHITE)
        hint_rect = hint_surf.get_rect(center=(screen.get_width() // 2, screen.get_height() - 60))
        screen.blit(hint_surf, hint_rect)

        pygame.display.flip()
        clock.tick(60)

    return None
