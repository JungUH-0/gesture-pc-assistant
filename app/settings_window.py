# ============================================================
#  개인 AI 비서 - 설정창 (tkinter)
#  탭: 명령 등록 / 음성
#
#  - 확인 팝업과 마찬가지로 전용 스레드에서 띄운다 (메인 스레드는 트레이 아이콘이 쓰고 있음).
#    tkinter는 스레드에 안전하지 않으므로 모든 tk 호출은 이 스레드 안에서만 한다.
#  - 명령 저장은 LLM 호출이 최대 60초 걸릴 수 있어서 별도 스레드로 돌리고, 결과는 큐에 담아
#    창 스레드가 0.15초마다 꺼내서 화면에 반영한다.
#  - 창이 이미 열려 있을 때 다시 열면 새 창을 만들지 않고 앞으로 가져온다.
# ============================================================

import gc
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

FONT = ("Malgun Gothic", 10)
FONT_BOLD = ("Malgun Gothic", 10, "bold")
WINDOW_TITLE = "gesture-pc-assistant 설정"


def _format_command(cmd):
    """{action, target} → 'open_app · chrome' 형태의 한 줄"""
    if not isinstance(cmd, dict):
        return str(cmd)
    action, target = cmd.get("action"), cmd.get("target")
    return f"{action} · {target}" if target else f"{action}"


class SettingsWindow:
    """
    names:          등록할 수 있는 동작 이름 목록 (main.KNOWN_COMMAND_NAMES)
    register_fn:    (이름, 내용) -> (성공 여부, 결과 또는 오류) — LLM 해석 후 저장
    list_fn:        () -> {이름: {action, target}}
    delete_fn:      (이름) -> 지웠는지 여부
    get_voice/set_voice:  음성 기능 켜기/끄기
    on_registered:  (성공 여부, 이름, 결과) 저장이 끝났을 때 호출 (알림용, 선택)
    """

    def __init__(self, names, register_fn, list_fn, delete_fn, get_voice, set_voice,
                 on_registered=None, get_dev=None, set_dev=None):
        self.get_dev = get_dev
        self.set_dev = set_dev
        self.names = list(names)
        self.register_fn = register_fn
        self.list_fn = list_fn
        self.delete_fn = delete_fn
        self.get_voice = get_voice
        self.set_voice = set_voice
        self.on_registered = on_registered

        self._thread = None
        self._raise_flag = threading.Event()
        self._results = queue.Queue()

    def is_open(self):
        return self._thread is not None and self._thread.is_alive()

    def show(self):
        """창을 열고, 이미 열려 있으면 앞으로 가져온다"""
        if self.is_open():
            self._raise_flag.set()
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ── 창 스레드 ───────────────────────────────────────────
    def _run(self):
        try:
            self._run_ui()
        finally:
            gc.collect()  # tk 객체를 만든 스레드에서 정리 (다른 스레드에서 정리되면 Tcl_AsyncDelete 오류)

    def _run_ui(self):
        try:
            root = tk.Tk()
        except Exception:
            return

        root.title(WINDOW_TITLE)
        root.geometry("760x540")
        root.minsize(680, 480)
        style = ttk.Style(root)
        style.configure("TNotebook.Tab", font=FONT_BOLD, padding=(14, 6))
        style.configure("Treeview", font=FONT, rowheight=26)
        style.configure("Treeview.Heading", font=FONT_BOLD)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        # ── 명령 등록 탭 ────────────────────────────────────
        tab_cmd = ttk.Frame(notebook, padding=14)
        notebook.add(tab_cmd, text="명령 등록")

        form = ttk.Frame(tab_cmd)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="동작 이름", font=FONT).grid(row=0, column=0, sticky="w")
        ttk.Label(form, text="하고 싶은 일", font=FONT).grid(row=0, column=1, sticky="w", padx=(14, 0))

        name_var = tk.StringVar(value=self.names[0] if self.names else "")
        name_box = ttk.Combobox(form, textvariable=name_var, values=self.names, state="readonly",
                                width=18, font=FONT)
        name_box.grid(row=1, column=0, sticky="w", pady=(2, 0))

        text_var = tk.StringVar()
        text_entry = ttk.Entry(form, textvariable=text_var, font=FONT)
        text_entry.grid(row=1, column=1, sticky="ew", padx=(14, 8), pady=(2, 0), ipady=3)

        save_btn = ttk.Button(form, text="저장")
        save_btn.grid(row=1, column=2, pady=(2, 0))

        status_var = tk.StringVar(value="동작 이름을 고르고, 하고 싶은 일을 자연어로 입력하세요. (예: 크롬 열어줘)")
        status = tk.Label(tab_cmd, textvariable=status_var, anchor="w", justify="left", font=FONT,
                          bg="#F2F2F2", fg="#444444", padx=10, pady=7, wraplength=680)
        status.pack(fill="x", pady=(12, 0))

        ttk.Label(tab_cmd, text="등록된 명령", font=FONT_BOLD).pack(anchor="w", pady=(16, 4))

        tree_frame = ttk.Frame(tab_cmd)
        tree_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(tree_frame, columns=("name", "content"), show="headings", selectmode="browse")
        tree.heading("name", text="동작 이름")
        tree.heading("content", text="등록 내용")
        tree.column("name", width=170, anchor="w")
        tree.column("content", width=470, anchor="w")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        bottom = ttk.Frame(tab_cmd)
        bottom.pack(fill="x", pady=(8, 0))
        delete_btn = ttk.Button(bottom, text="선택한 명령 삭제")
        delete_btn.pack(side="right")
        ttk.Label(bottom, text="목록에서 명령을 고르면 위 입력칸에 해당 이름이 선택됩니다.",
                  font=("Malgun Gothic", 9), foreground="#777777").pack(side="left")

        def set_status(text, kind="info"):
            colors = {"info": ("#F2F2F2", "#444444"), "ok": ("#E8F5E9", "#2E5E3A"),
                      "error": ("#FBE9E7", "#B03A2E"), "busy": ("#FFF8E1", "#7A5B00")}
            bg, fg = colors[kind]
            status.config(bg=bg, fg=fg)
            status_var.set(text)

        def refresh_list():
            tree.delete(*tree.get_children())
            try:
                commands = self.list_fn()
            except Exception as e:
                set_status(f"등록 목록을 읽지 못했습니다: {e}", "error")
                return
            for name in sorted(commands):
                tree.insert("", "end", iid=name, values=(name, _format_command(commands[name])))

        def on_tree_select(_event=None):
            selected = tree.selection()
            if selected and selected[0] in self.names:
                name_var.set(selected[0])

        tree.bind("<<TreeviewSelect>>", on_tree_select)

        def do_save(_event=None):
            name, text = name_var.get().strip(), text_var.get().strip()
            if not name:
                set_status("동작 이름을 선택하세요.", "error")
                return
            if not text:
                set_status("하고 싶은 일을 입력하세요.", "error")
                return
            save_btn.state(["disabled"])
            set_status("해석 중... (LLM 응답에 최대 60초가 걸릴 수 있습니다)", "busy")

            def worker():
                try:
                    ok, result = self.register_fn(name, text)
                except Exception as e:  # 저장 실패가 창을 죽이지 않게
                    ok, result = False, str(e)
                # 알림은 창이 닫혔어도 나가야 하므로 여기서 바로 보낸다 (창 쪽 반영은 큐로)
                if self.on_registered:
                    try:
                        self.on_registered(ok, name, result)
                    except Exception:
                        pass
                self._results.put((ok, name, result))

            threading.Thread(target=worker, daemon=True).start()

        save_btn.config(command=do_save)
        text_entry.bind("<Return>", do_save)

        def do_delete():
            selected = tree.selection()
            if not selected:
                set_status("삭제할 명령을 목록에서 선택하세요.", "error")
                return
            name = selected[0]
            if not messagebox.askyesno("명령 삭제", f"'{name}' 명령을 삭제할까요?", parent=root):
                return
            try:
                removed = self.delete_fn(name)
            except Exception as e:
                set_status(f"삭제하지 못했습니다: {e}", "error")
                return
            refresh_list()
            set_status(f"'{name}' 명령을 삭제했습니다." if removed else f"'{name}'은 이미 없는 명령입니다.", "ok")

        delete_btn.config(command=do_delete)

        # ── 음성 탭 ─────────────────────────────────────────
        tab_voice = ttk.Frame(notebook, padding=18)
        notebook.add(tab_voice, text="음성")

        voice_var = tk.BooleanVar(value=bool(self.get_voice()))

        def on_voice_toggle():
            self.set_voice(voice_var.get())
            voice_note.config(text="음성 명령을 사용합니다." if voice_var.get() else "음성 명령을 사용하지 않습니다.")

        ttk.Checkbutton(tab_voice, text="음성 명령 사용 (웨이크워드 · 손등 3초 유지)",
                        variable=voice_var, command=on_voice_toggle).pack(anchor="w")
        voice_note = ttk.Label(tab_voice, font=("Malgun Gothic", 9), foreground="#777777",
                               text="음성 명령을 사용합니다." if voice_var.get() else "음성 명령을 사용하지 않습니다.")
        voice_note.pack(anchor="w", pady=(6, 0))
        ttk.Label(tab_voice, font=("Malgun Gothic", 9), foreground="#777777",
                  text="끄면 웨이크워드 감지(GPU 사용)와 손등 3초 음성 트리거가 모두 멈춥니다.").pack(anchor="w", pady=(2, 0))

        # ── 일반 탭 (지금은 개발 모드만. 캡처 폴더·자동 실행 등은 필요해질 때 추가) ──
        if self.get_dev is not None and self.set_dev is not None:
            tab_general = ttk.Frame(notebook, padding=18)
            notebook.add(tab_general, text="일반")

            dev_var = tk.BooleanVar(value=bool(self.get_dev()))

            def dev_text(on):
                return ("개발 모드: 카메라 미리보기에 랜드마크 점·선과 함께 FPS, 모드, 판정 수치 등 지표가 표시됩니다."
                        if on else "일반 모드: 카메라 미리보기에 랜드마크 점과 연결선만 표시됩니다.")

            def on_dev_toggle():
                self.set_dev(dev_var.get())
                dev_note.config(text=dev_text(dev_var.get()))

            ttk.Checkbutton(tab_general, text="개발 모드 (미리보기에 지표 표시)",
                            variable=dev_var, command=on_dev_toggle).pack(anchor="w")
            dev_note = ttk.Label(tab_general, font=("Malgun Gothic", 9), foreground="#777777",
                                 text=dev_text(dev_var.get()), wraplength=640, justify="left")
            dev_note.pack(anchor="w", pady=(6, 0))
            ttk.Label(tab_general, font=("Malgun Gothic", 9), foreground="#777777", wraplength=640,
                      text="오인식 원인을 찾거나 임계값을 조정할 때 켭니다. 카메라 미리보기를 켜 둔 상태라면 바로 반영됩니다."
                      ).pack(anchor="w", pady=(2, 0))

        # ── 결과 반영 · 앞으로 가져오기 · 종료 ──────────────
        def poll():
            while True:
                try:
                    ok, name, result = self._results.get_nowait()
                except queue.Empty:
                    break
                save_btn.state(["!disabled"])
                if ok:
                    set_status(f"저장됨 → {name} : {_format_command(result)}", "ok")
                    text_var.set("")
                    refresh_list()
                else:
                    set_status(f"저장하지 못했습니다: {result}", "error")
            if self._raise_flag.is_set():
                self._raise_flag.clear()
                root.deiconify()
                root.lift()
                root.focus_force()
            root.after(150, poll)

        # 창이 닫혀 있는 동안 끝난 저장의 결과가 남아 있으면 다음에 열 때 엉뚱하게 보이므로 버림
        while not self._results.empty():
            try:
                self._results.get_nowait()
            except queue.Empty:
                break

        refresh_list()
        text_entry.focus_set()
        poll()
        root.mainloop()
