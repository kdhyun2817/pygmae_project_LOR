# main_play.py
import pygame
from unit import WHITE
from battle import run_battle

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("게임 로비 / 메인")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("malgungothic", 28)

    running = True
    last_result = None  # 마지막 전투 결과 기록용

    while running:
        dt = clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                # B 키를 누르면 test1 전투 시작
                if event.key == pygame.K_b:
                    # 전투 씬으로 진입
                    result = run_battle(screen, "test1")
                    last_result = result  # 전투 끝나고 돌아오면 결과 저장

        # 로비 화면 그리기
        screen.fill((10, 10, 20))
        title = font.render("로비 화면 (B: 전투 시작, ESC: 종료)", True, WHITE)
        screen.blit(title, (80, 80))

        if last_result is not None:
            msg = font.render(f"마지막 전투 결과: {last_result}", True, WHITE)
            screen.blit(msg, (80, 140))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
