# main.py
import pygame

from battle import run_battle, set_player_deck_config
from intro_scene import run_intro
from menu_scene import run_menu
from lobby_scene import run_lobby

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SCALED)
    screen = pygame.display.set_mode(
        (SCREEN_WIDTH, SCREEN_HEIGHT),
        pygame.FULLSCREEN | pygame.SCALED
    )
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
            # 3) 스테이지 + 캐릭터 + 책장 선택 로비로 이동
            lobby_result = run_lobby(screen)

            # 로비에서 ESC나 뒤로 가기로 빠져나오면 None이 올 수 있음
            if lobby_result is None:
                continue

            # run_lobby 는 (stage_code, party, deck_config) 튜플을 리턴한다.
            stage_code, party, deck_config = lobby_result

            # 🔹 로비에서 선택한 덱 설정을 전투 모듈에 전달
            set_player_deck_config(deck_config)

            # 🔹 파티 정보를 전투로 넘김 — 전투는 단 한 번만 실행
            battle_result = run_battle(screen, stage_code, party=party)

            if battle_result == "exit":
                # 전투 종료 후 나가기 같은 경우 처리
                return

            print("전투 결과:", battle_result)

    pygame.quit()


if __name__ == "__main__":
    main()
