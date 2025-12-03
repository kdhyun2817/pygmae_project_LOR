# menu_scene.py
import pygame
from unit import WHITE, PANEL_BG

MENU_ITEMS = ["게임 시작", "설정", "나가기"]


def run_menu(screen):
    clock = pygame.time.Clock()
    font_title = pygame.font.SysFont("malgungothic", 52)
    font_item = pygame.font.SysFont("malgungothic", 32)

    selected = 0
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "EXIT"

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "EXIT"

                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(MENU_ITEMS)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(MENU_ITEMS)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    item = MENU_ITEMS[selected]
                    if item == "게임 시작":
                        return "START"
                    elif item == "설정":
                        # TODO: 옵션 메뉴 추가할 때 여기서 다른 씬으로 넘기면 됨
                        print("설정 메뉴는 아직 구현되지 않았습니다.")
                    elif item == "나가기":
                        return "EXIT"

        # ----- 화면 그리기 -----
        screen.fill(PANEL_BG)

        # 제목
        title_surf = font_title.render("Project LOR-like", True, WHITE)
        title_rect = title_surf.get_rect(center=(screen.get_width() // 2, 150))
        screen.blit(title_surf, title_rect)

        # 메뉴 항목
        cx = screen.get_width() // 2
        start_y = 280
        gap = 60

        for i, text in enumerate(MENU_ITEMS):
            color = WHITE
            surf = font_item.render(text, True, color)
            rect = surf.get_rect(center=(cx, start_y + i * gap))

            if i == selected:
                # 선택된 항목에 밑줄 / 강조 박스
                pygame.draw.rect(
                    screen,
                    (200, 200, 220),
                    rect.inflate(30, 10),
                    width=2,
                )

            screen.blit(surf, rect)

        pygame.display.flip()
        clock.tick(60)

    return "EXIT"
