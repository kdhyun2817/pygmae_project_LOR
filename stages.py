# stages.py
from __future__ import annotations

from unit import DamageType, ResistLevel

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# 화면 해상도는 main.py 에서 1280x720으로 쓰고 있으니,
# 여기서는 그냥 그 기준으로 직접 좌표를 적어준다.

STAGES: dict[str, dict] = {
    # --------------------------------------
    # 튜토리얼 스테이지
    # 이름: 튜토리얼
    # 적: 레니, 망치, 피트
    # --------------------------------------
    "tutorial": {
        "name": "튜토리얼",
        "enemy_units": [
            # 레니: 가운데 쯤
            {
                "name": "레니",
                "max_hp": 90,
                "max_sp": 45,
                "speed_min": 1,
                "speed_max": 4,
                "pos": (200, int(SCREEN_HEIGHT * 0.60)),
                "hp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.NORMAL,
                },
                "sp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.NORMAL,
                },
            },
            # 망치: 약간 위, 좀 더 왼쪽
            {
                "name": "망치",
                "max_hp": 80,
                "max_sp": 40,
                "speed_min": 1,
                "speed_max": 4,
                "pos": (260, int(SCREEN_HEIGHT * 0.80)),
                "hp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.NORMAL,
                },
                "sp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.NORMAL,
                },
            },
            # 피트: 아래쪽, 오른쪽
            {
                "name": "피트",
                "max_hp": 70,
                "max_sp": 40,
                "speed_min": 1,
                "speed_max": 4,
                "pos": (260, int(SCREEN_HEIGHT * 0.40)),
                "hp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.NORMAL,
                },
                "sp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.NORMAL,
                },
            },
        ],
    },
}
