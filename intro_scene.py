# intro_scene.py
import os
import pygame
from ffpyplayer.player import MediaPlayer


def _play_video(screen, filename, allow_skip=True):
    """
    단일 mp4 파일을 전체 화면으로 재생하는 함수 (ffpyplayer 사용).
    - ESC를 누르면 스킵
    - 영상이 끝나면 자동으로 함수 종료
    """
    base_dir = os.path.dirname(__file__)
    path = os.path.join(base_dir, "intro", filename)

    if not os.path.isfile(path):
        print(f"[경고] 영상을 찾을 수 없습니다: {path}")
        return

    screen_w, screen_h = screen.get_size()
    clock = pygame.time.Clock()

    player = MediaPlayer(
        path,
        ff_opts={
            "out_fmt": "rgb24",
            "sync": "audio",
            # loop 기본값(1회 재생) 사용
            "autoexit": True,
        },
    )

    # 🔹 ffpyplayer 메타데이터에서 재생 길이(초)를 가져온다.
    meta = player.get_metadata() or {}
    duration = meta.get("duration", 0) or 0.0

    elapsed = 0.0          # 지나간 시간(초)
    empty_frames = 0       # 연속으로 frame=None인 횟수

    while True:
        # 한 프레임당 경과 시간 (초)
        dt = clock.tick(60) / 1000.0
        elapsed += dt

        # ----- 이벤트 처리 -----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                player.close_player()
                pygame.quit()
                raise SystemExit
            if allow_skip and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                player.close_player()
                return

        # ----- 프레임 읽기 -----
        frame, val = player.get_frame()

        # 1) ffpyplayer가 eof를 알려주면 그대로 종료
        if val == "eof":
            break

        # 2) 프레임이 안 나오는 경우 처리
        if frame is None:
            empty_frames += 1

            # (1) 영상 길이만큼 시간이 지났다면 끝난 걸로 간주
            if duration and elapsed >= duration + 0.5:
                break

            # (2) 1초 이상 프레임이 계속 안 오면 끝난 걸로 간주
            if empty_frames > 60:
                break

            continue
        else:
            empty_frames = 0

        # ----- 프레임 그리기 -----
        img, t = frame
        vw, vh = img.get_size()
        buf = img.to_bytearray()[0]

        surf = pygame.image.frombuffer(buf, (vw, vh), "RGB")
        if (vw, vh) != (screen_w, screen_h):
            surf = pygame.transform.smoothscale(surf, (screen_w, screen_h))

        screen.blit(surf, (0, 0))
        pygame.display.flip()

    player.close_player()

def run_intro(screen):
    """
    게임 시작 시 호출: 로고 → 인트로 영상 순서대로 자동 재생.
    - 로고가 끝나면 바로 인트로 재생
    - 중간에 ESC를 누르면 바로 다음 단계로 넘어감(메뉴/로비 등)
    """
    # # 로고 영상 (스킵 가능)
    # _play_video(screen, "LogoIntro.mp4", allow_skip=True)
    #
    # # 인트로 영상 (원하면 여기 allow_skip=False로 해서 스킵 못 하게 할 수도 있음)
    # _play_video(screen, "GameIntro.mp4", allow_skip=True)
