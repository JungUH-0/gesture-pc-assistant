# ============================================================
#  개인 AI 비서 - 앱 설정 저장 (app/settings.json)
#  설정창에서 바꾼 값을 다음 실행에도 유지한다. 개인 설정이라 git에는 올리지 않는다.
#  파일이 없거나 깨져 있으면 기본값으로 시작한다.
# ============================================================

import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULTS = {
    "voice_enabled": True,   # 음성 명령(웨이크워드·손등 3초) 사용 여부
    "dev_mode": False,       # 개발 모드: 카메라 미리보기에 점·선 외에 FPS·판정 수치 등 지표도 표시
}


def load():
    settings = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            settings.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return settings


def save(settings):
    """저장에 실패해도(읽기 전용 폴더 등) 앱이 죽지 않도록 성공 여부만 반환"""
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False
