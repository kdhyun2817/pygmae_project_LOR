# menu_scene.py
import os
import cv2
import pygame
import math
from ffpyplayer.player import MediaPlayer

from unit import WHITE


# ----------------------------
# 메뉴 리소스 정의
# ----------------------------

MENU_ITEMS = [
    {"key": "start",    "label": "시작하기", "icon": "Icon_Start.png"},
    {"key": "continue", "label": "이어하기", "icon": "Icon_Continue.png"},
    {"key": "option",   "label": "설정",     "icon": "Icon_Option.png"},
    {"key": "exit",     "label": "끝내기",   "icon": "Icon_Exit.png"},
]


def _find_menu_dir():
    """현재 파일 기준으로 menu 폴더 경로 반환."""
    base_dir = os.path.dirname(__file__)
    menu_dir = os.path.join(base_dir, "menu")
    return menu_dir


def _open_background_video(menu_dir):
    """
    menu 폴더 안에서 동영상 파일(mp4 등)을 찾아 첫 번째 것을 연다.
    ffpyplayer.MediaPlayer를 반환하고, 없으면 None을 반환한다.
    """
    if not os.path.isdir(menu_dir):
        return None

    video_exts = (".mp4", ".avi", ".mov", ".mkv")
    candidates = [
        name
        for name in os.listdir(menu_dir)
        if name.lower().endswith(video_exts)
    ]
    if not candidates:
        return None

    candidates.sort()
    path = os.path.join(menu_dir, candidates[0])

    try:
        player = MediaPlayer(
            path,
            ff_opts={
                "out_fmt": "rgb24",
                "sync": "audio",
                "loop": 0,      # 0이면 무한 루프
                "autoexit": False,
            },
        )
    except Exception as e:
        print(f"[메뉴] 동영상을 열 수 없습니다: {path} ({e})")
        return None

    print(f"[메뉴] 배경 동영상 사용: {path}")
    return player



def _read_video_frame_as_surface(player, screen_size):
    """
    ffpyplayer.MediaPlayer에서 한 프레임을 읽어 pygame Surface로 변환.
    """
    frame, val = player.get_frame()

    # 동영상이 끝에 닿았으면 처음으로 되감기
    if val == "eof":
        try:
            player.seek(0.0, relative=False)
        except Exception:
            pass
        return None  # 이 프레임에서는 그냥 배경을 안 그림

    # 아직 프레임이 준비 안 된 경우
    if frame is None:
        return None

    img, t = frame
    vw, vh = img.get_size()
    buf = img.to_bytearray()[0]  # rgb24 기준 단일 plane

    surf = pygame.image.frombuffer(buf, (vw, vh), "RGB")

    w, h = screen_size
    if (vw, vh) != (w, h):
        surf = pygame.transform.smoothscale(surf, (w, h))

    return surf



# ----------------------------
# 타이틀 로고 (TitleLogo.png) 한 장만 사용하는 코드
# ----------------------------

_TITLE_LOGO_SURF = None


def _draw_title_logo(screen, menu_dir):
    """
    menu/TitleLogo.png 이미지를 불러와서
    화면 왼쪽 위에 적당한 크기로 띄운다.
    """
    global _TITLE_LOGO_SURF

    screen_w, screen_h = screen.get_size()

    # 한 번만 로딩해서 캐시에 저장
    if _TITLE_LOGO_SURF is None:
        logo_path = os.path.join(menu_dir, "TitleLogo.png")
        if not os.path.isfile(logo_path):
            print(f"[메뉴] TitleLogo.png 를 찾을 수 없습니다: {logo_path}")
            return

        try:
            img = pygame.image.load(logo_path).convert_alpha()
        except Exception as e:
            print(f"[메뉴] TitleLogo.png 로드 실패: {e}")
            return

        # 너무 크거나 너무 작지 않게 화면 비율에 맞춰 스케일
        # (화면 가로의 60% 정도가 최대)
        max_w = int(screen_w * 0.60)
        scale = 1.0
        if img.get_width() > max_w:
            scale = max_w / img.get_width()

        if scale != 1.0:
            new_size = (int(img.get_width() * scale),
                        int(img.get_height() * scale))
            img = pygame.transform.smoothscale(img, new_size)

        _TITLE_LOGO_SURF = img

    # 캐시된 로고 사용
    logo = _TITLE_LOGO_SURF
    rect = logo.get_rect()

    # 화면 왼쪽 위에 살짝 내려온 위치에 배치 (라오루 느낌)
    rect.topleft = (
        int(screen_w * 0.29),  # 약간 오른쪽
        0  # 위에 딱 붙이기
    )

    screen.blit(logo, rect)

def _action_from_key(key: str):
    """메뉴 key를 main 루프가 사용하는 문자열로 변환."""
    if key == "start":
        return "START"
    if key == "continue":
        return "CONTINUE"
    if key == "option":
        return "OPTION"
    if key == "exit":
        return "EXIT"
    # 혹시 모르는 기본값
    return "EXIT"



def run_menu(screen):
    """
    메인 메뉴 화면.
    - 뒤쪽에는 menu 폴더의 동영상이 루프 재생.
    - 그 위에 TitleInk 전체 화면, 그 위에 UITitletextbg를 덮어씌움.
    - 왼쪽 위에는 TitleLogo.png 한 장을 배치.
    - 중앙 근처에 4개의 아이콘을 2×2로 배치.
    - 아이콘에 마우스를 올리면 Image_AlarmPopup.png가 옆으로 튀어나오며
      한글 라벨(시작하기/이어하기/설정/끝내기)을 표시.
    """
    pygame.mouse.set_visible(True)
    clock = pygame.time.Clock()

    screen_w, screen_h = screen.get_size()
    menu_dir = _find_menu_dir()

    # 팝업용 폰트 (조금 크게)
    font_label = pygame.font.SysFont("malgungothic", 34)

    # TitleInk 전체 화면 오버레이
    title_ink = None
    for name in ("TitleInk.png", "titleink.png", "UITitleInk.png"):
        title_path = os.path.join(menu_dir, name)
        if os.path.isfile(title_path):
            try:
                img = pygame.image.load(title_path).convert_alpha()
                title_ink = pygame.transform.smoothscale(img, (screen_w, screen_h))
            except Exception as e:
                print(f"[메뉴] {name} 로드 실패: {e}")
            break

    # 텍스트 배경 오버레이 이미지 (UITitletextbg)
    bg_overlay = None
    overlay_path = os.path.join(menu_dir, "UITitletextbg.png")
    if os.path.isfile(overlay_path):
        try:
            img = pygame.image.load(overlay_path).convert_alpha()
            bg_overlay = pygame.transform.smoothscale(img, (screen_w, screen_h))
        except Exception as e:
            print(f"[메뉴] UITitletextbg.png 로드 실패: {e}")

    # 툴팝 배경 (Image_AlarmPopup)
    popup_bg = None
    popup_path = os.path.join(menu_dir, "Image_AlarmPopup.png")
    if os.path.isfile(popup_path):
        try:
            popup_bg = pygame.image.load(popup_path).convert_alpha()
        except Exception as e:
            print(f"[메뉴] Image_AlarmPopup.png 로드 실패: {e}")

    # ----------------------------
    # 아이콘 로드 및 위치 계산 (퍼센트 배치)
    # ----------------------------
    icons = []
    loaded_surfs = []

    for item in MENU_ITEMS:
        icon_path = os.path.join(menu_dir, item["icon"])
        try:
            surf = pygame.image.load(icon_path).convert_alpha()
        except Exception as e:
            print(f"[메뉴] 아이콘 로드 실패 ({icon_path}): {e}")
            surf = pygame.Surface((120, 120), pygame.SRCALPHA)
            pygame.draw.polygon(
                surf,
                (255, 200, 0),
                [(10, 10), (110, 10), (110, 110), (10, 110)],
                3,
            )

        # 아이콘 크기 축소 (지금 쓰던 크기 유지)
        base_scale = 0.3
        new_size = (
            int(surf.get_width() * base_scale),
            int(surf.get_height() * base_scale),
        )
        surf = pygame.transform.smoothscale(surf, new_size)

        loaded_surfs.append((item, surf))

    # 화면 가로/세로에 대한 비율로 아이콘 위치 지정
    # 0: 시작하기, 1: 이어하기, 2: 설정, 3: 끝내기
    icon_pos_ratios = [
        (0.28, 0.33),  # 시작하기  (좌상)
        (0.75, 0.45),  # 이어하기 (우상)
        (0.27, 0.67),  # 설정     (좌하)
        (0.70, 0.75),  # 끝내기   (우하)
    ]

    for idx, (item, surf) in enumerate(loaded_surfs):
        rect = surf.get_rect()

        if idx < len(icon_pos_ratios):
            rx, ry = icon_pos_ratios[idx]
        else:
            # 혹시 메뉴가 늘어났을 때를 위한 안전장치 (중앙 아래로 떨어뜨려 배치)
            rx, ry = 0.5, 0.5 + 0.1 * idx

        cx = int(screen_w * rx)
        cy = int(screen_h * ry)
        rect.center = (cx, cy)

        icons.append(
            {
                "key": item["key"],
                "label": item["label"],
                "surf": surf,
                "rect": rect,
            }
        )

    # 배경 동영상 열기 (ffpyplayer)
    bg_player = _open_background_video(menu_dir)


    selected_idx = 0
    running = True

    while running:
        dt = clock.tick(60) / 1000.0  # dt는 지금은 안 쓰지만 남겨둠

        # ----- 배경 그리기 -----
        if bg_player is not None:
            frame_surf = _read_video_frame_as_surface(bg_player, (screen_w, screen_h))
            if frame_surf is not None:
                screen.blit(frame_surf, (0, 0))
            else:
                screen.fill((0, 0, 0))
        else:
            screen.fill((0, 0, 0))

        # 1) 타이틀 먼저
        _draw_title_logo(screen, menu_dir)

        # 2) 그 위에 잉크/텍스트 오버레이
        if title_ink is not None:
            screen.blit(title_ink, (0, 0))
        if bg_overlay is not None:
            screen.blit(bg_overlay, (0, 0))

        # ----- 입력 처리 -----
        mouse_pos = pygame.mouse.get_pos()
        hovered_idx = None
        for i, info in enumerate(icons):
            if info["rect"].collidepoint(mouse_pos):
                hovered_idx = i
                break

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if bg_player is not None:
                    bg_player.close_player()
                return "EXIT"

            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected_idx = (selected_idx - 1) % len(icons)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected_idx = (selected_idx + 1) % len(icons)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    key = icons[selected_idx]["key"]
                    if bg_player is not None:
                        bg_player.close_player()
                    return _action_from_key(key)
                elif event.key == pygame.K_ESCAPE:
                    if bg_player is not None:
                        bg_player.close_player()
                    return "EXIT"

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hovered_idx is not None:
                    key = icons[hovered_idx]["key"]
                    if bg_player is not None:
                        bg_player.close_player()
                    return _action_from_key(key)

        if hovered_idx is not None:
            selected_idx = hovered_idx

        # ----- 아이콘 + 팝업 그리기 -----
        for i, info in enumerate(icons):
            surf = info["surf"]
            base_rect = info["rect"]
            rect = base_rect.copy()

            # 선택/호버된 아이콘이면 살짝 키우기
            is_hot = i == selected_idx
            if is_hot:
                scale = 1.05
                new_size = (int(rect.width * scale), int(rect.height * scale))
                scaled = pygame.transform.smoothscale(surf, new_size)
                rect = scaled.get_rect(center=rect.center)
                screen.blit(scaled, rect)
            else:
                screen.blit(surf, rect)

            # ----- 팝업 -----
            if popup_bg is not None and i == hovered_idx:
                base_popup = popup_bg

                # 1) 팝업이 향할 "목표 방향" 계산
                icon_cx, icon_cy = rect.center

                if i < len(icons) - 1:
                    # 다음 아이콘 방향으로
                    nx, ny = icons[i + 1]["rect"].center
                    target_cx, target_cy = nx, ny
                elif len(icons) >= 3:
                    # 마지막 아이콘: 2번→3번(인덱스 1→2)의 기울기와 동일한 방향
                    ax, ay = icons[1]["rect"].center
                    bx, by = icons[2]["rect"].center
                    dir_x = bx - ax
                    dir_y = by - ay
                    target_cx = icon_cx + dir_x
                    target_cy = icon_cy + dir_y
                else:
                    # 아이콘이 2개 이하인 특수 케이스: 그냥 오른쪽
                    target_cx = icon_cx + rect.width
                    target_cy = icon_cy

                dx = target_cx - icon_cx
                dy = target_cy - icon_cy
                dist = math.hypot(dx, dy)
                if dist < 1:
                    dist = rect.width  # 안전장치

                # 2) 팝업 크기: 아이콘→다음 아이콘까지 거의 닿을 정도 길이
                aspect = base_popup.get_width() / base_popup.get_height()
                popup_w = int(dist * 0.95)  # 두 아이콘 사이 거리의 95%
                popup_h = max(int(popup_w / aspect), int(rect.height * 0.6))
                popup = pygame.transform.smoothscale(base_popup, (popup_w, popup_h))

                # 3) 각도 계산
                angle_rad = math.atan2(dy, dx)
                angle_deg = math.degrees(angle_rad)

                # 팝업 배경 회전 (선 방향에 맞춤)
                popup_rot = pygame.transform.rotate(popup, -angle_deg)

                # 팝업 중심: 아이콘과 목표 지점의 중간
                mid_x = (icon_cx + target_cx) // 2
                mid_y = (icon_cy + target_cy) // 2
                popup_rect = popup_rot.get_rect(center=(mid_x, mid_y))

                # 4) 텍스트 렌더링 (노란 계열 색)
                text_color = (255, 230, 160)
                label = info["label"]
                text_surf = font_label.render(label, True, text_color)

                # 텍스트도 팝업 각도에 맞추되, 거꾸로 보이지 않게 조정
                text_rot_deg = -angle_deg
                if text_rot_deg > 90 or text_rot_deg < -90:
                    # 너무 많이 돌아가면 180도 더 돌려서 바로 세움
                    text_rot_deg += 180

                text_rot = pygame.transform.rotate(text_surf, text_rot_deg)
                text_rect = text_rot.get_rect(center=popup_rect.center)

                # 5) 그리기 순서: 팝업 → 텍스트
                screen.blit(popup_rot, popup_rect)
                screen.blit(text_rot, text_rect)

        pygame.display.flip()

    if bg_player  is not None:
        bg_player .close_player()
    return None

