# stages.py
from unit import DamageType, ResistLevel

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# 스테이지 정의 예시
# 지금은 "test1" 하나만. 나중에 "1-1", "1-2" 이런 식으로 늘리면 됨.
STAGES = {
    "test1": {
        "enemy_units": [
            # 가운데 적
            {
                "pos": (200, int(SCREEN_HEIGHT * 0.60)),
                "max_hp": 50,
                "max_sp": 20,
                "speed_min": 1,
                "speed_max": 3,
                "hp_res": {
                    DamageType.SLASH: ResistLevel.FATAL,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.ENDURE,
                },
                "sp_res": {
                    DamageType.SLASH: ResistLevel.ENDURE,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.NORMAL,
                },
            },
            # 왼쪽 위 적
            {
                "pos": (260, int(SCREEN_HEIGHT * 0.80)),
                "max_hp": 35,
                "max_sp": 25,
                "speed_min": 3,
                "speed_max": 6,
                "hp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.FATAL,
                    DamageType.BLUNT: ResistLevel.NORMAL,
                },
                "sp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.WEAK,
                    DamageType.BLUNT: ResistLevel.ENDURE,
                },
            },
            # 왼쪽 아래 적
            {
                "pos": (260, int(SCREEN_HEIGHT * 0.40)),
                "max_hp": 45,
                "max_sp": 30,
                "speed_min": 2,
                "speed_max": 4,
                "hp_res": {
                    DamageType.SLASH: ResistLevel.NORMAL,
                    DamageType.PIERCE: ResistLevel.ENDURE,
                    DamageType.BLUNT: ResistLevel.RESIST,
                },
                "sp_res": {
                    DamageType.SLASH: ResistLevel.ENDURE,
                    DamageType.PIERCE: ResistLevel.NORMAL,
                    DamageType.BLUNT: ResistLevel.RESIST,
                },
            },
        ]
    }
}
