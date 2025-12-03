# intro_scene.py
import os
import pygame
import cv2 #pip install OpenCV_python


def _play_video(screen, filename, allow_skip=True):
    """단일 mp4 파일을 전체 화면으로 재생하는 함수."""
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, "intro", filename)

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"[경고] 영상을 열 수 없습니다: {path}")
        return

    clock = pygame.time.Clock()
    width, height = screen.get_size()

    while True:
        ret, frame = cap.read()
        if not ret:
            break  # 영상 끝

        # OpenCV(BGR) → pygame(RGB) 변환
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.resize(frame, (width, height))
        surf = pygame.surfarray.make_surface(frame.swapaxes(0, 1))

        # 화면에 그리기
        screen.blit(surf, (0, 0))
        pygame.display.flip()

        # 이벤트 처리 (종료 / ESC 스킵)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cap.release()
                pygame.quit()
                raise SystemExit
            if allow_skip and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                cap.release()
                return

        clock.tick(60)

    cap.release()


def run_intro(screen):
    """게임 시작 시 호출: 로고 → 인트로 영상 순서대로 재생."""
    # _play_video(screen, "LogoIntro.mp4", allow_skip=True)
