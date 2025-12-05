# lobby_scene.py

import pygame
from pygame.locals import *

from stages import STAGES  # 스테이지 목록/정보 딕셔너리
from battle import COMBAT_PAGES, build_dice_summary_lines

WHITE = (255, 255, 255)
GRAY = (120, 120, 120)
BLACK = (0, 0, 0)
BG_COLOR = (15, 15, 25)
HIGHLIGHT = (240, 220, 120)


def run_lobby(screen) -> tuple | None:
    """
    스테이지 선택 + 파티(캐릭터) 선택 화면.

    반환:
        (stage_code: str, party: list[str], deck_config: dict[str, list[int]])
    또는 ESC로 나가면 None
    """

    clock = pygame.time.Clock()
    width, height = screen.get_size()

    font_title = pygame.font.SysFont("malgungothic", 48)
    font_small = pygame.font.SysFont("malgungothic", 24)
    font_deck = pygame.font.SysFont("malgungothic", 18)  # 책장 목록용 작은 폰트

    # --- 전체 전투 책장 목록 + 프리셋 정의 ---
    all_pages_list = list(COMBAT_PAGES.values())
    deck_presets = []

    # 필요하면 여기 프리셋 구성을 직접 바꿔도 됨
    if all_pages_list:
        deck_presets.append({
            "name": "프리셋 1",
            "card_ids": [p.card_id for p in all_pages_list[:9]],
        })
    if len(all_pages_list) > 9:
        deck_presets.append({
            "name": "프리셋 2",
            "card_ids": [p.card_id for p in all_pages_list[9:18]],
        })



    # -----------------------------------
    # 1) 스테이지 버튼 만들기
    # -----------------------------------
    stage_codes = list(STAGES.keys())
    stage_buttons = []  # [(rect, code, label), ...]

    start_x = 80
    start_y = 160
    w = 260
    h = 60
    gap_y = 20

    for i, code in enumerate(stage_codes):
        rect = pygame.Rect(start_x, start_y + i * (h + gap_y), w, h)
        label = STAGES[code].get("name", code)
        stage_buttons.append((rect, code, label))

    selected_stage_index = 0 if stage_buttons else -1

    # -----------------------------------
    # 2) 캐릭터 선택 UI
    # -----------------------------------
    # 캐릭터 ID는 characters/<ID>/<ID>_기본.png 구조의 폴더/파일 이름과 같아야 함
    characters = [
        {
            "id": "롤랑",
            "name": "롤랑",
            "selected": True,
            "deck_page_ids": [],
        },
        {
            "id": "말쿠트",
            "name": "말쿠트",
            "selected": False,
            "deck_page_ids": [],
        },
        {
            "id": "예소드",
            "name": "예소드",
            "selected": False,
            "deck_page_ids": [],
        },
        {
            "id": "네짜흐",
            "name": "네짜흐",
            "selected": False,
            "deck_page_ids": [],
        },
        {
            "id": "티페리트",
            "name": "티페리트",
            "selected": False,
            "deck_page_ids": [],
        },
        {
            "id": "헤세드",
            "name": "헤세드",
            "selected": False,
            "deck_page_ids": [],
        },
        {
            "id": "호드",
            "name": "호드",
            "selected": False,
            "deck_page_ids": [],
        },
    ]

    # 캐릭터 카드 영역 (오른쪽 패널)
    party_panel_rect = pygame.Rect(width * 0.55, 140, width * 0.35, height * 0.55)

    # 캐릭터 카드 기본 크기/위치
    card_w = int(party_panel_rect.width * 0.8)
    card_h = 80
    card_x = party_panel_rect.centerx - card_w // 2
    card_y = party_panel_rect.top + 60

    # 캐릭터 카드 사각형 목록
    char_card_rects = []
    for idx, ch in enumerate(characters):
        rect = pygame.Rect(
            card_x,
            card_y + idx * (card_h + 20),
            card_w,
            card_h,
        )
        char_card_rects.append(rect)

    # -----------------------------------
    # 2-1) 캐릭터 카드 스크롤 범위 계산
    # -----------------------------------
    scroll_offset = 0
    max_scroll = 0

    if char_card_rects:
        last_bottom = char_card_rects[-1].bottom
        # 카드가 보일 수 있는 영역의 아래쪽 경계 (패널 안쪽에 여백)
        visible_bottom = party_panel_rect.bottom - 20

        if last_bottom > visible_bottom:
            max_scroll = last_bottom - visible_bottom

    # -----------------------------------
    # 2-2) 책장 선택 UI 상태
    # -----------------------------------
    deck_select_char_index = None   # 어느 캐릭터의 책장 선택 패널이 열려 있는지 (characters 인덱스)
    deck_scroll_offset = 0          # 왼쪽 책장 목록 스크롤(행 단위)

    def build_party_and_deck():
        """
        현재 선택된 캐릭터 목록과,
        캐릭터 ID -> 선택한 card_id 리스트 매핑을 만든다.
        """
        party_ids = [ch["id"] for ch in characters if ch["selected"]]
        deck_config = {}
        for ch in characters:
            if ch["selected"]:
                ids = ch.get("deck_page_ids", [])
                # 빈 리스트면 굳이 넣지 않아도 되지만, battle 쪽에서 빈 리스트는 무시하므로 그냥 넣어도 됨
                deck_config[ch["id"]] = list(ids)
        return party_ids, deck_config

    def get_deck_panel_rects_for_char(idx: int):
        """
        idx 번째 캐릭터 카드 왼쪽에 책장 선택 패널 rect들을 계산.
        - panel_rect: 전체 패널
        - preset_rect: 가장 왼쪽 프리셋 버튼 영역
        - list_rect: 가운데 '보유 책장 목록'
        - selected_rect: 오른쪽 '현재 사용 예정 책장'
        """
        if idx is None or idx < 0 or idx >= len(char_card_rects):
            return None, None, None, None

        # 스크롤 적용된 실제 위치 기준
        base_rect = char_card_rects[idx]
        card_rect = base_rect.move(0, -scroll_offset)

        panel_w = int(party_panel_rect.width * 0.95)
        panel_h = 360

        panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        panel_rect.midright = (card_rect.left - 20, card_rect.centery)

        # 화면 밖으로 안 나가게 보정
        if panel_rect.left < 20:
            panel_rect.left = 20
        if panel_rect.top < 80:
            panel_rect.top = 80
        if panel_rect.bottom > height - 40:
            panel_rect.bottom = height - 40

        margin = 12
        inner = panel_rect.inflate(-margin * 2, -margin * 2)

        # 가로 분할: [프리셋] [보유 책장 목록] [현재 사용 예정]
        preset_w = 90
        gap = 10

        # 프리셋 영역
        preset_rect = pygame.Rect(
            inner.left,
            inner.top + 40,
            preset_w,
            inner.height - 50,
        )

        # 보유 책장 목록 영역
        list_w = int(inner.width * 0.45)
        list_rect = pygame.Rect(
            preset_rect.right + gap,
            inner.top + 40,
            list_w,
            inner.height - 50,
        )

        # 현재 사용 예정 책장 영역
        selected_left = list_rect.right + 20
        selected_w = inner.right - selected_left
        if selected_w < 80:
            selected_w = 80
        selected_rect = pygame.Rect(
            selected_left,
            inner.top + 40,
            selected_w,
            inner.height - 50,
        )

        return panel_rect, preset_rect, list_rect, selected_rect

    # -----------------------------------
    # 3) 시작 버튼
    # -----------------------------------
    start_button_rect = pygame.Rect(width // 2 - 120, height - 140, 240, 70)

    running = True
    while running:
        dt = clock.tick(60)

        for event in pygame.event.get():
            if event.type == QUIT:
                return None

            # 마우스 휠 스크롤 (pygame 2.x)
            if event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()

                # 1) 책장 선택 패널이 열려 있고, "책장 목록" 위에서 휠을 돌리는 경우 → 덱만 스크롤
                if deck_select_char_index is not None:
                    panel_rect, preset_rect, list_rect, selected_rect = get_deck_panel_rects_for_char(
                        deck_select_char_index
                    )
                    if list_rect is not None and list_rect.collidepoint(mx, my):
                        item_h = 52
                        all_pages = all_pages_list  # 아래에서 만들 프리셋용 전체 리스트
                        visible_rows = max(1, list_rect.height // item_h)
                        max_offset = max(0, len(all_pages) - visible_rows)

                        # pygame: event.y > 0 이면 휠 위로
                        deck_scroll_offset -= event.y  # 위로 = -1, 아래로 = +1

                        if deck_scroll_offset < 0:
                            deck_scroll_offset = 0
                        if deck_scroll_offset > max_offset:
                            deck_scroll_offset = max_offset

                        # 🔴 덱 스크롤 했으면 캐릭터 스크롤은 건드리지 않고 여기서 끝낸다
                        continue

                # 2) 그 외에는 기존처럼 캐릭터 카드 스크롤
                if event.y > 0:  # 휠 위로
                    scroll_offset = max(scroll_offset - 20, 0)
                elif event.y < 0:  # 휠 아래로
                    scroll_offset = min(scroll_offset + 20, max_scroll)

            if event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    return None

                # ↑/↓로 스테이지 이동
                if event.key == K_UP and stage_buttons:
                    selected_stage_index = (selected_stage_index - 1) % len(stage_buttons)
                if event.key == K_DOWN and stage_buttons:
                    selected_stage_index = (selected_stage_index + 1) % len(stage_buttons)

                if event.key == K_RETURN:
                    if stage_buttons and any(ch["selected"] for ch in characters):
                        _, stage_code, _ = stage_buttons[selected_stage_index]
                        party, deck_config = build_party_and_deck()
                        return stage_code, party, deck_config

            # 마우스 버튼 (휠 up/down + 좌/우클릭)
            if event.type == MOUSEBUTTONDOWN:
                mx, my = event.pos

                # 옛날 방식 휠(버튼 4/5) 처리 부분은 그대로 두면 됨
                if event.button == 4:
                    scroll_offset = max(scroll_offset - 20, 0)
                    continue
                if event.button == 5:
                    scroll_offset = min(scroll_offset + 20, max_scroll)
                    continue

                # 1) 책장 선택 패널 안에서의 클릭 처리
                if deck_select_char_index is not None:
                    panel_rect, preset_rect, list_rect, selected_rect = get_deck_panel_rects_for_char(
                        deck_select_char_index
                    )

                    # (1-0) 프리셋 선택: 프리셋 영역에서 좌클릭 → 해당 프리셋으로 덱 덮어쓰기
                    if event.button == 1 and preset_rect is not None and preset_rect.collidepoint(mx, my):
                        preset_item_h = 40
                        rel_y = my - preset_rect.top
                        p_idx = rel_y // preset_item_h
                        if 0 <= p_idx < len(deck_presets):
                            preset = deck_presets[p_idx]
                            ch = characters[deck_select_char_index]
                            # 프리셋으로 덱을 통째로 교체 (중복 허용)
                            ch["deck_page_ids"] = list(preset["card_ids"])
                        continue

                    # (1-1) 왼쪽 책장 목록에서 좌클릭 → 해당 책장을 현재 덱에 추가
                    if event.button == 1 and list_rect is not None and list_rect.collidepoint(mx, my):
                        item_h = 52
                        rel_y = my - list_rect.top
                        row = rel_y // item_h

                        all_pages = all_pages_list
                        page_index = deck_scroll_offset + row
                        if 0 <= page_index < len(all_pages):
                            page = all_pages[page_index]
                            ch = characters[deck_select_char_index]
                            if "deck_page_ids" not in ch:
                                ch["deck_page_ids"] = []
                            # 카드 id 기준으로 저장 (중복 허용)
                            ch["deck_page_ids"].append(page.card_id)
                        continue

                    # (1-2) 오른쪽 '현재 사용 예정 책장'에서 우클릭 → 해당 칸 제거
                    if event.button == 3 and selected_rect is not None and selected_rect.collidepoint(mx, my):
                        ch = characters[deck_select_char_index]
                        ids = ch.get("deck_page_ids", [])
                        item_h2 = 40
                        rel_y = my - selected_rect.top
                        idx_slot = rel_y // item_h2
                        if 0 <= idx_slot < len(ids):
                            del ids[idx_slot]
                        continue

                    # (1-3) 패널 밖을 우클릭하면 패널 닫기
                    if event.button == 3 and panel_rect is not None and not panel_rect.collidepoint(mx, my):
                        deck_select_char_index = None
                        continue

                # 2) 캐릭터 카드 우클릭 → 출전 중이면 책장 선택 패널 토글
                if event.button == 3:
                    for idx, base_rect in enumerate(char_card_rects):
                        rect = base_rect.move(0, -scroll_offset)
                        if rect.collidepoint(mx, my):
                            ch = characters[idx]
                            if ch.get("selected"):
                                if deck_select_char_index == idx:
                                    deck_select_char_index = None
                                else:
                                    deck_select_char_index = idx
                                    deck_scroll_offset = 0
                            break

                # 3) 좌클릭 – 기존 스테이지/캐릭터/시작 버튼 처리 그대로 유지...
                if event.button == 1:
                    # 3-1) 스테이지 선택
                    for i, (rect, code, label) in enumerate(stage_buttons):
                        if rect.collidepoint(mx, my):
                            selected_stage_index = i

                    # 3-2) 캐릭터 카드 클릭 → 선택 토글
                    for idx, base_rect in enumerate(char_card_rects):
                        rect = base_rect.move(0, -scroll_offset)
                        if rect.collidepoint(mx, my):
                            characters[idx]["selected"] = not characters[idx]["selected"]
                            # 선택 해제된 캐릭터의 패널이 열려 있으면 닫기
                            if not characters[idx]["selected"] and deck_select_char_index == idx:
                                deck_select_char_index = None

                    # 3-3) 시작 버튼 클릭
                    if start_button_rect.collidepoint(mx, my):
                        if stage_buttons and any(ch["selected"] for ch in characters):
                            _, stage_code, _ = stage_buttons[selected_stage_index]
                            party, deck_config = build_party_and_deck()
                            return stage_code, party, deck_config

        # =========================
        #  화면 그리기
        # =========================
        screen.fill(BG_COLOR)

        # 제목
        title_surf = font_title.render("로비 - 스테이지 & 파티 선택", True, WHITE)
        screen.blit(title_surf, (width // 2 - title_surf.get_width() // 2, 40))

        # -------- 왼쪽: 스테이지 --------
        stage_title = font_small.render("스테이지 선택", True, WHITE)
        screen.blit(stage_title, (start_x, start_y - 40))

        for i, (rect, code, label) in enumerate(stage_buttons):
            if i == selected_stage_index:
                pygame.draw.rect(screen, HIGHLIGHT, rect, border_radius=10)
            else:
                pygame.draw.rect(screen, GRAY, rect, border_radius=10)

            txt = font_small.render(label, True, BLACK)
            screen.blit(txt, (rect.centerx - txt.get_width() // 2,
                              rect.centery - txt.get_height() // 2))

        # -------- 오른쪽: 파티(롤랑) --------
        pygame.draw.rect(screen, (30, 30, 60), party_panel_rect, border_radius=16)
        party_title = font_small.render("파티 편성", True, WHITE)
        screen.blit(party_title, (party_panel_rect.left + 20, party_panel_rect.top + 20))

        for idx, ch in enumerate(characters):
            base_rect = char_card_rects[idx]
            # 스크롤 적용된 실제 화면 좌표
            rect = base_rect.move(0, -scroll_offset)
            selected = ch["selected"]

            # 패널 영역 밖으로 완전히 나간 카드들은 그리지 않기 (성능 + 보기용)
            if rect.bottom < party_panel_rect.top + 120:
                continue
            if rect.top > party_panel_rect.bottom - 100:
                continue

            pygame.draw.rect(
                screen,
                HIGHLIGHT if selected else GRAY,
                rect,
                border_radius=12,
            )

            name_text = font_small.render(ch["name"], True, BLACK)
            id_text = font_small.render(f"ID: {ch['id']}", True, BLACK)

            screen.blit(name_text, (rect.left + 16, rect.top + 12))
            screen.blit(id_text, (rect.left + 16, rect.top + 40))

            if selected:
                check_text = font_small.render("선택됨", True, BLACK)
                screen.blit(
                    check_text,
                    (rect.right - check_text.get_width() - 16,
                     rect.centery - check_text.get_height() // 2),
                )

        # -------- 하단: 시작 버튼 --------
        able_to_start = stage_buttons and any(ch["selected"] for ch in characters)
        btn_color = HIGHLIGHT if able_to_start else (80, 80, 80)

        pygame.draw.rect(screen, btn_color, start_button_rect, border_radius=18)
        start_txt = font_small.render("전투 시작 (Enter)", True, BLACK)
        screen.blit(start_txt, (start_button_rect.centerx - start_txt.get_width() // 2,
                                start_button_rect.centery - start_txt.get_height() // 2))

        # -------- 책장 선택 패널 그리기 --------
        # -------- 책장 선택 패널 그리기 --------
        if deck_select_char_index is not None:
            panel_rect, preset_rect, list_rect, selected_rect = get_deck_panel_rects_for_char(
                deck_select_char_index
            )
            if panel_rect is not None:
                # 반투명 배경
                panel_surf = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
                panel_surf.fill((10, 10, 20, 220))
                screen.blit(panel_surf, panel_rect.topleft)
                pygame.draw.rect(screen, (200, 200, 220), panel_rect, 2, border_radius=8)

                ch = characters[deck_select_char_index]

                # 제목
                title_text = f"{ch['name']} - 책장 선택"
                title_surf = font_small.render(title_text, True, WHITE)
                title_rect = title_surf.get_rect()
                title_rect.midtop = (panel_rect.centerx, panel_rect.top + 8)
                screen.blit(title_surf, title_rect)

                # 1) 프리셋 영역
                if preset_rect is not None:
                    pygame.draw.rect(screen, (25, 25, 40), preset_rect)
                    pygame.draw.rect(screen, (150, 150, 200), preset_rect, 1)

                    preset_title = font_deck.render("프리셋", True, (200, 200, 220))
                    screen.blit(preset_title, (preset_rect.left, preset_rect.top - 24))

                    preset_item_h = 40
                    y_p = preset_rect.top + 4
                    for i, preset in enumerate(deck_presets):
                        label = preset["name"]
                        txt = font_deck.render(label, True, WHITE)
                        screen.blit(txt, (preset_rect.left + 6, y_p))
                        y_p += preset_item_h

                # 2) 왼쪽: 전체 책장 목록
                if list_rect is not None:
                    pygame.draw.rect(screen, (30, 30, 50), list_rect)
                    pygame.draw.rect(screen, (150, 150, 200), list_rect, 1)

                    list_title = font_deck.render("보유 책장 목록 (좌클릭으로 추가)", True, (200, 200, 220))
                    screen.blit(list_title, (list_rect.left, list_rect.top - 24))

                    item_h = 52
                    all_pages = all_pages_list
                    start_idx = deck_scroll_offset
                    visible_rows = max(1, list_rect.height // item_h)
                    end_idx = min(len(all_pages), start_idx + visible_rows)

                    y = list_rect.top + 4
                    for i in range(start_idx, end_idx):
                        page = all_pages[i]
                        name = getattr(page, "name", str(page.card_id))

                        name_surf = font_deck.render(name, True, WHITE)
                        screen.blit(name_surf, (list_rect.left + 6, y))

                        dice_lines = build_dice_summary_lines(page)
                        if dice_lines:
                            info_surf = font_deck.render(dice_lines[0], True, (200, 200, 220))
                            screen.blit(info_surf, (list_rect.left + 6, y + 22))

                        y += item_h

                # 3) 오른쪽: 현재 사용 예정 책장 목록
                if selected_rect is not None:
                    pygame.draw.rect(screen, (30, 30, 50), selected_rect)
                    pygame.draw.rect(screen, (150, 150, 200), selected_rect, 1)

                    sel_title = font_deck.render("현재 사용 예정 책장 (우클릭으로 제거)", True, (200, 200, 220))
                    screen.blit(sel_title, (selected_rect.left, selected_rect.top - 24))

                    ids = ch.get("deck_page_ids", [])
                    item_h2 = 40
                    y = selected_rect.top + 4
                    for idx_slot, cid in enumerate(ids):
                        page = COMBAT_PAGES.get(cid)
                        if page is not None:
                            label = f"{idx_slot + 1}. {page.name}"
                        else:
                            label = f"{idx_slot + 1}. {cid}"
                        lab_surf = font_deck.render(label, True, WHITE)
                        screen.blit(lab_surf, (selected_rect.left + 6, y))
                        y += item_h2

        pygame.display.flip()
