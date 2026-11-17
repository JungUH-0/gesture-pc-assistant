# ============================================================
#  개인 AI 비서 - 확인 팝업 (창 닫기 확인)
#  tkinter 창을 별도 스레드에서 띄운다 (메인 스레드는 트레이 아이콘이 쓰고 있음).
#
#  - 포커스를 가져가지 않는다(WS_EX_NOACTIVATE). 팝업이 활성 창이 되면 사용자가 쓰던 창이
#    바뀌어 버리므로, 클릭해도 활성 창이 그대로 유지되게 한다.
#  - 항상 위에 떠 있고, 화면 오른쪽 아래에 표시한다.
#  - tkinter는 스레드에 안전하지 않아서, 모든 tk 호출은 이 팝업 스레드 안에서만 한다.
#    바깥에서는 close()로 플래그만 세우고, 팝업 스레드가 0.1초마다 확인해서 스스로 닫는다.
# ============================================================

import ctypes
import gc
import threading
import time
import tkinter as tk

from windowcontrol import POPUP_WINDOW_TITLE

GWL_EXSTYLE      = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST    = 0x00000008
WIDTH, HEIGHT    = 360, 190
MARGIN           = 24


class ClosePopup:
    """
    창 닫기 확인 팝업 하나. show()로 띄우고, 사용자가 버튼을 누르면 on_answer(True/False)를
    호출한다. 제스처로 응답이 끝났을 때는 close()로 바깥에서 닫는다.
    """

    def __init__(self):
        self._thread = None
        self._close_flag = threading.Event()

    def is_open(self):
        return self._thread is not None and self._thread.is_alive()

    def show(self, window_title, timeout_sec, on_answer):
        if self.is_open():
            return
        self._close_flag.clear()
        self._thread = threading.Thread(
            target=self._run, args=(window_title, timeout_sec, on_answer), daemon=True)
        self._thread.start()

    def close(self):
        self._close_flag.set()

    def _run(self, window_title, timeout_sec, on_answer):
        try:
            self._run_ui(window_title, timeout_sec, on_answer)
        finally:
            # tkinter 객체는 만든 스레드에서 정리해야 한다. 순환 참조로 남은 것을 여기서 수거하지 않으면
            # 나중에 다른 스레드(주로 종료 시 메인 스레드)가 정리하다가 Tcl_AsyncDelete 오류가 난다.
            gc.collect()

    def _run_ui(self, window_title, timeout_sec, on_answer):
        try:
            root = tk.Tk()
        except Exception:
            return  # 화면을 만들 수 없는 환경이면 팝업 없이 제스처 응답만 사용

        root.withdraw()  # 스타일을 걸기 전에 화면에 나타나서 포커스를 가져가지 않도록 숨겨 둠
        root.title(POPUP_WINDOW_TITLE)
        root.attributes("-topmost", True)
        root.resizable(False, False)
        x = root.winfo_screenwidth() - WIDTH - MARGIN
        y = root.winfo_screenheight() - HEIGHT - MARGIN - 40  # 작업 표시줄을 피함
        root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

        def answer(yes):
            try:
                on_answer(yes)
            finally:
                root.destroy()

        shown = window_title if window_title else "(창 정보 없음)"
        if len(shown) > 36:
            shown = shown[:35] + "…"

        tk.Label(root, text="창을 닫을까요?", font=("Malgun Gothic", 13, "bold")).pack(pady=(14, 2))
        tk.Label(root, text=f"대상: {shown}", font=("Malgun Gothic", 10), fg="#444444").pack()
        row = tk.Frame(root)
        row.pack(pady=12)
        tk.Button(row, text="예", width=9, font=("Malgun Gothic", 11, "bold"),
                  command=lambda: answer(True)).pack(side="left", padx=8)
        tk.Button(row, text="아니오", width=9, font=("Malgun Gothic", 11),
                  command=lambda: answer(False)).pack(side="left", padx=8)
        hint = tk.Label(root, text="", font=("Malgun Gothic", 9), fg="#666666")
        hint.pack()
        tk.Label(root, text="엄지척·끄덕임 = 예 / 엄지다운·가로젓기 = 아니오",
                 font=("Malgun Gothic", 8), fg="#888888").pack()

        # 숨겨진 상태에서 확장 스타일을 걸어 포커스를 가져가지 않게 한 뒤 화면에 표시한다
        user32 = ctypes.windll.user32
        prev_foreground = user32.GetForegroundWindow()
        hwnd = None
        try:
            root.update_idletasks()
            hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
        except Exception:
            pass  # 실패해도 팝업은 동작 (포커스를 가져갈 수 있을 뿐)
        root.deiconify()
        root.update()
        # 그래도 팝업이 활성 창이 됐다면 원래 쓰던 창으로 되돌림
        try:
            if hwnd and prev_foreground and user32.GetForegroundWindow() == hwnd:
                user32.SetForegroundWindow(prev_foreground)
        except Exception:
            pass

        deadline = time.time() + timeout_sec

        def tick():
            remaining = deadline - time.time()
            if self._close_flag.is_set() or remaining < -0.5:
                root.destroy()
                return
            hint.config(text=f"{max(int(remaining + 0.99), 0)}초 안에 응답 · 무응답이면 자동 취소")
            root.after(100, tick)

        root.protocol("WM_DELETE_WINDOW", lambda: answer(False))  # X 버튼 = 아니오
        tick()
        root.mainloop()
