# ============================================================
#  개인 AI 비서 - 트레이 앱 실행 파일
#  콘솔·카메라 창 없이 시스템 트레이 아이콘으로만 상주한다.
#
#  실행(콘솔 창 없이):  pythonw.exe tray_main.py
#  실행(콘솔 창 포함, 디버깅용):  python tray_main.py
#
#  트레이 메뉴: 카메라 미리보기 / 설정(준비 중) / 로그 보기 / 일시정지·재개 / 종료
#  로그: app/logs/assistant.log  (콘솔 출력도 모두 이 파일로 저장)
# ============================================================

import os
import sys
import time
import threading
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)  # 모듈들이 상대 경로로 만드는 진단 파일(debug_*.txt)이 app/ 안에 생기게 함
sys.path.insert(0, APP_DIR)

LOG_DIR = os.path.join(APP_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "assistant.log")
MAX_LOG_BYTES = 1_000_000  # 시작할 때 이보다 크면 비우고 새로 시작


# ── 로그 파일 ───────────────────────────────────────────────
# pythonw.exe로 실행하면 콘솔이 없어서 print가 사라지므로, 표준 출력·오류를 로그 파일로 돌린다.
def _open_log():
    os.makedirs(LOG_DIR, exist_ok=True)
    mode = "w" if (os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_LOG_BYTES) else "a"
    return open(LOG_PATH, mode, encoding="utf-8", buffering=1)


_log_file = _open_log()
sys.stdout = _log_file
sys.stderr = _log_file
_log_lock = threading.Lock()


def log(text):
    with _log_lock:
        _log_file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")


log("=== 트레이 앱 시작 ===")

try:
    import pystray
    from PIL import Image, ImageDraw
    import win32api
    import win32event
    import winerror

    import main as assistant_main
except Exception:
    log("필요한 모듈을 불러오지 못했습니다:\n" + traceback.format_exc())
    raise


# ── 중복 실행 방지 ──────────────────────────────────────────
# 카메라와 마이크는 하나라서 두 개가 동시에 돌면 서로 방해한다.
_mutex = win32event.CreateMutex(None, False, "gesture-pc-assistant-tray")
if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
    log("이미 실행 중이라 종료합니다.")
    sys.exit(0)


# ── 아이콘 이미지 ───────────────────────────────────────────
COLORS = {
    "loading": (240, 160, 48),   # 주황: 모델 로딩 중
    "running": (74, 111, 165),   # 파랑: 실행 중
    "paused":  (136, 136, 136),  # 회색: 일시정지
    "error":   (192, 57, 43),    # 빨강: 중지됨·오류
}
TITLES = {
    "loading": "개인 AI 비서 - 시작하는 중",
    "running": "개인 AI 비서 - 실행 중",
    "paused":  "개인 AI 비서 - 일시정지",
    "error":   "개인 AI 비서 - 중지됨 (로그를 확인하세요)",
}


def make_icon(state):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=COLORS[state])
    d.ellipse((22, 22, 42, 42), fill="white")
    return img


# ── 상태와 비서 ─────────────────────────────────────────────
# 시스템 시작 시 카메라 창은 띄우지 않고, 창의 'q'·X는 미리보기만 닫게 한다.
assistant = assistant_main.Assistant(show_window=False, quit_on_q=False)
assistant_main.set_event_handler(lambda tag, msg: log(f"[{tag}] {msg}"))

state = {"phase": "loading", "quitting": False}


def refresh(icon):
    """상태에 맞게 아이콘·툴팁·메뉴를 갱신"""
    phase = state["phase"]
    if phase == "running" and assistant.is_paused():
        phase = "paused"
    icon.icon = make_icon(phase)
    icon.title = TITLES[phase]
    icon.update_menu()


# ── 메뉴 동작 ───────────────────────────────────────────────
def _is_ready(item):
    return state["phase"] == "running"


def _preview_checked(item):
    return assistant.preview_on()


def _toggle_preview(icon, item):
    assistant.set_preview(not assistant.preview_on())
    log(f"카메라 미리보기 {'켜기' if assistant.preview_on() else '끄기'}")


def _open_log(icon, item):
    try:
        os.startfile(LOG_PATH)
    except OSError as e:
        log(f"로그 파일을 열지 못했습니다: {e}")


def _pause_text(item):
    return "재개" if assistant.is_paused() else "일시정지"


def _toggle_pause(icon, item):
    if assistant.is_paused():
        assistant.resume()
    else:
        assistant.pause()
    refresh(icon)


def _quit(icon, item):
    # 종료 정리(Whisper·카메라 스레드 정리)가 오래 걸릴 수 있어 별도 스레드로 처리
    def _shutdown():
        state["quitting"] = True
        log("종료 요청")
        assistant.stop()
        icon.stop()
    threading.Thread(target=_shutdown, daemon=True).start()


menu = pystray.Menu(
    pystray.MenuItem("카메라 미리보기", _toggle_preview, checked=_preview_checked, enabled=_is_ready),
    pystray.MenuItem("설정 (준비 중)", lambda icon, item: None, enabled=False),
    pystray.MenuItem("로그 보기", _open_log),
    pystray.MenuItem(_pause_text, _toggle_pause, enabled=_is_ready),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem("종료", _quit),
)


# ── 시작 ────────────────────────────────────────────────────
def _boot(icon):
    """모델 로딩(수십 초 걸릴 수 있음)을 트레이 아이콘이 뜬 뒤에 별도 스레드로 처리"""
    try:
        assistant.start()
        state["phase"] = "running"
        log("비서 시작 완료")
    except Exception:
        state["phase"] = "error"
        log("비서를 시작하지 못했습니다:\n" + traceback.format_exc())
        refresh(icon)
        return
    refresh(icon)

    # 카메라를 열 수 없는 등으로 루프가 스스로 끝나면 오류 상태로 표시
    assistant.wait()
    if not state["quitting"]:
        state["phase"] = "error"
        log("비서 루프가 종료되었습니다 (카메라 오류 등). 위쪽 로그를 확인하세요.")
        refresh(icon)


def _setup(icon):
    icon.visible = True
    threading.Thread(target=_boot, args=(icon,), daemon=True).start()


if __name__ == "__main__":
    icon = pystray.Icon("gesture-pc-assistant", make_icon("loading"), TITLES["loading"], menu)
    icon.run(setup=_setup)
    log("=== 트레이 앱 종료 ===")
