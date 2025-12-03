# main.py
import pygame

from battle import run_battle
from intro_scene import run_intro
from menu_scene import run_menu
from lobby_scene import run_lobby

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Project LOR-like")

    # 1) 인트로 영상 재생 (로고 → 게임 인트로)
    run_intro(screen)

    # 2) 메인 메뉴 / 로비 / 전투 루프
    running = True
    while running:
        action = run_menu(screen)

        if action in (None, "EXIT"):
            # 메뉴에서 나가기 선택 or 창 닫기
            running = False
            break

        if action == "START":
            # 3) 스테이지 선택 로비로 이동
            stage_code = run_lobby(screen)

            # 로비에서 ESC나 뒤로 가기로 빠져나오면 None이 올 수 있음
            if stage_code is None:
                continue

            # 4) 선택된 스테이지로 전투 진입
            result = run_battle(screen, stage_code)
            # result: "win", "lose" 등 (battle.py에서 이미 그렇게 설계됨)
            # 필요하면 여기서 결과에 따라 처리 추가 가능
            print("전투 결과:", result)

    pygame.quit()


if __name__ == "__main__":
    main()
