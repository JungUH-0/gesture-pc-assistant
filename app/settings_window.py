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
                 on_registered=None, get_dev=None, set_dev=None, pose_api=None,
                 get_whisper=None, set_whisper=None, whisper_active=None):
        # get_whisper/set_whisper: 음성 인식 실행 방식 "auto"|"gpu"|"cpu" 읽기/저장 (없으면 선택 상자를 만들지 않음)
        # whisper_active: () -> 지금 실제로 적용 중인 방식 "gpu"|"cpu" (안내 문구용, 선택)
        self.get_whisper = get_whisper
        self.set_whisper = set_whisper
        self.whisper_active = whisper_active
        self.get_dev = get_dev
        self.set_dev = set_dev
        # names: 목록 또는 목록을 돌려주는 함수. 함수면 포즈를 등록·삭제할 때마다 다시 불러 동작 이름 목록을 갱신한다
        self._names_source = names
        # pose_api: 포즈 탭이 쓰는 함수 모음 (없으면 포즈 탭을 만들지 않음)
        #   "list"    () -> (행 목록, 메타)   행: {name, kind("기본 제공"|"사용자"), command}, 메타: {builtin, count, max}
        #   "capture" (이름, on_status) -> (성공 여부, 안내 문구)   수 초 걸리므로 별도 스레드에서 호출됨
        #   "delete"  (이름) -> 안내 문구      "restore" () -> (성공 여부, 안내 문구)
        self.pose_api = pose_api
        self.register_fn = register_fn
        self.list_fn = list_fn
        self.delete_fn = delete_fn
        self.get_voice = get_voice
        self.set_voice = set_voice
        self.on_registered = on_registered

        self._thread = None
        self._raise_flag = threading.Event()
        self._results = queue.Queue()

    def _get_names(self):
        src = self._names_source
        return list(src() if callable(src) else src)

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

        initial_names = self._get_names()
        name_var = tk.StringVar(value=initial_names[0] if initial_names else "")
        name_box = ttk.Combobox(form, textvariable=name_var, values=initial_names, state="readonly",
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
            if selected and selected[0] in self._get_names():
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
                self._results.put(("reg", ok, name, result))

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

        def refresh_names():
            """포즈를 등록·삭제하면 명령 등록 탭의 동작 이름 목록(pose_이름)도 새로 불러온다"""
            names = self._get_names()
            name_box.config(values=names)
            if name_var.get() not in names:
                name_var.set(names[0] if names else "")

        # ── 포즈 탭 ─────────────────────────────────────────
        refresh_pose_list = None
        if self.pose_api is not None:
            tab_pose = ttk.Frame(notebook, padding=14)
            notebook.add(tab_pose, text="포즈")

            pform = ttk.Frame(tab_pose)
            pform.pack(fill="x")
            pform.columnconfigure(0, weight=1)
            ttk.Label(pform, text="새 포즈 이름", font=FONT).grid(row=0, column=0, sticky="w")
            pose_name_var = tk.StringVar()
            pose_entry = ttk.Entry(pform, textvariable=pose_name_var, font=FONT)
            pose_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(2, 0), ipady=3)
            capture_btn = ttk.Button(pform, text="촬영")
            capture_btn.grid(row=1, column=1, pady=(2, 0))

            pose_status_var = tk.StringVar(
                value="이름을 입력하고 촬영을 누르세요. 상체와 양팔이 카메라에 보이게 앉아 자세를 취하면 됩니다. "
                      "명령은 나중에 '명령 등록' 탭에서 연결할 수 있습니다.")
            pose_status = tk.Label(tab_pose, textvariable=pose_status_var, anchor="w", justify="left", font=FONT,
                                   bg="#F2F2F2", fg="#444444", padx=10, pady=7, wraplength=680)
            pose_status.pack(fill="x", pady=(12, 0))

            pose_count_var = tk.StringVar(value="등록된 포즈")
            ttk.Label(tab_pose, textvariable=pose_count_var, font=FONT_BOLD).pack(anchor="w", pady=(16, 4))

            pframe = ttk.Frame(tab_pose)
            pframe.pack(fill="both", expand=True)
            ptree = ttk.Treeview(pframe, columns=("name", "kind", "cmd"), show="headings", selectmode="browse")
            ptree.heading("name", text="포즈 이름")
            ptree.heading("kind", text="종류")
            ptree.heading("cmd", text="연결된 명령")
            ptree.column("name", width=190, anchor="w")
            ptree.column("kind", width=90, anchor="w")
            ptree.column("cmd", width=360, anchor="w")
            pscroll = ttk.Scrollbar(pframe, orient="vertical", command=ptree.yview)
            ptree.configure(yscrollcommand=pscroll.set)
            ptree.pack(side="left", fill="both", expand=True)
            pscroll.pack(side="right", fill="y")

            pbottom = ttk.Frame(tab_pose)
            pbottom.pack(fill="x", pady=(8, 0))
            pose_delete_btn = ttk.Button(pbottom, text="선택한 포즈 삭제")
            pose_delete_btn.pack(side="right")
            restore_btn = ttk.Button(pbottom, text="기본 자세(ㅡ자) 복원")
            restore_btn.pack(side="right", padx=(0, 8))
            ttk.Label(pbottom, font=("Malgun Gothic", 9), foreground="#777777",
                      text="포즈는 정지 자세만 등록할 수 있습니다. 포즈 모드에서 인식됩니다.").pack(side="left")

            def set_pose_status(text, kind="info"):
                colors = {"info": ("#F2F2F2", "#444444"), "ok": ("#E8F5E9", "#2E5E3A"),
                          "error": ("#FBE9E7", "#B03A2E"), "busy": ("#FFF8E1", "#7A5B00")}
                bg, fg = colors[kind]
                pose_status.config(bg=bg, fg=fg)
                pose_status_var.set(text)

            def refresh_pose_list():
                ptree.delete(*ptree.get_children())
                try:
                    rows, meta = self.pose_api["list"]()
                except Exception as e:
                    set_pose_status(f"포즈 목록을 읽지 못했습니다: {e}", "error")
                    return
                for row in rows:
                    ptree.insert("", "end", iid=row["name"],
                                 values=(row["name"], row["kind"], row["command"]))
                pose_count_var.set(f"등록된 포즈 ({meta['count']} / {meta['max']})")
                restore_btn.state(["!disabled"] if not meta["builtin"] else ["disabled"])
                refresh_names()

            def do_capture(_event=None):
                name = pose_name_var.get().strip()
                if not name:
                    set_pose_status("포즈 이름을 입력하세요.", "error")
                    return
                capture_btn.state(["disabled"])
                set_pose_status("준비 중입니다...", "busy")

                def worker():
                    try:
                        ok, msg = self.pose_api["capture"](
                            name, lambda text: self._results.put(("pose_status", text)))
                    except Exception as e:
                        ok, msg = False, f"촬영 중 오류가 났습니다: {e}"
                    self._results.put(("pose_done", ok, msg))

                threading.Thread(target=worker, daemon=True).start()

            capture_btn.config(command=do_capture)
            pose_entry.bind("<Return>", do_capture)

            def do_pose_delete():
                selected = ptree.selection()
                if not selected:
                    set_pose_status("삭제할 포즈를 목록에서 선택하세요.", "error")
                    return
                name = selected[0]
                builtin = next((r["kind"] == "기본 제공" for r in self.pose_api["list"]()[0] if r["name"] == name), False)
                if builtin:
                    question = (f"'{name}'은 기본 제공 자세입니다.\n삭제하면 이 자세로 화면을 캡처하는 기능이 꺼집니다.\n"
                                "(나중에 '기본 자세 복원'으로 되돌릴 수 있습니다)\n\n삭제할까요?")
                else:
                    question = f"'{name}' 포즈를 삭제할까요?\n연결해 둔 명령도 함께 삭제됩니다."
                if not messagebox.askyesno("포즈 삭제", question, parent=root):
                    return
                try:
                    msg = self.pose_api["delete"](name)
                except Exception as e:
                    set_pose_status(f"삭제하지 못했습니다: {e}", "error")
                    return
                refresh_pose_list()
                refresh_list()   # 연결된 명령이 함께 지워졌을 수 있어 명령 목록도 새로 고침
                set_pose_status(msg, "ok")

            pose_delete_btn.config(command=do_pose_delete)

            def do_restore():
                try:
                    ok, msg = self.pose_api["restore"]()
                except Exception as e:
                    ok, msg = False, str(e)
                refresh_pose_list()
                set_pose_status(msg, "ok" if ok else "error")

            restore_btn.config(command=do_restore)
            refresh_pose_list()

        def on_tab_changed(_event=None):
            refresh_names()   # 다른 탭에서 바뀐 포즈 이름을 명령 등록 탭에 반영
            if refresh_pose_list:
                refresh_pose_list()

        notebook.bind("<<NotebookTabChanged>>", on_tab_changed)

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

        # 음성 인식 실행 방식 (GPU 없는 PC에서는 CPU 방식 선택). 모델은 시작할 때 한 번만 불러오므로 다음 실행부터 적용
        if self.get_whisper is not None and self.set_whisper is not None:
            WHISPER_LABELS = {
                "auto": "자동 (GPU가 있으면 GPU, 없으면 CPU)",
                "gpu":  "GPU (medium, 소음에 강함, NVIDIA GPU 필요)",
                "cpu":  "CPU (small, GPU 없이 동작, 느림)",
            }
            label_to_mode = {v: k for k, v in WHISPER_LABELS.items()}

            ttk.Separator(tab_voice).pack(fill="x", pady=(14, 10))
            ttk.Label(tab_voice, text="음성 인식 실행 방식").pack(anchor="w")
            cur = self.get_whisper()
            whisper_var = tk.StringVar(value=WHISPER_LABELS.get(cur, WHISPER_LABELS["auto"]))
            whisper_box = ttk.Combobox(tab_voice, textvariable=whisper_var, state="readonly",
                                       values=list(WHISPER_LABELS.values()), width=44)
            whisper_box.pack(anchor="w", pady=(4, 0))

            active = self.whisper_active() if self.whisper_active else None
            active_text = f"현재 적용 중: {'GPU' if active == 'gpu' else 'CPU'}" if active else ""
            whisper_note = ttk.Label(tab_voice, font=("Malgun Gothic", 9), foreground="#777777",
                                     text=(active_text + (" · " if active_text else "") + "바꾸면 앱을 다시 실행한 뒤 적용됩니다."))
            whisper_note.pack(anchor="w", pady=(6, 0))

            def on_whisper_change(_event=None):
                mode = label_to_mode.get(whisper_var.get(), "auto")
                self.set_whisper(mode)
                whisper_note.config(text="저장했습니다. 앱을 다시 실행하면 적용됩니다.")

            whisper_box.bind("<<ComboboxSelected>>", on_whisper_change)

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
                    item = self._results.get_nowait()
                except queue.Empty:
                    break
                kind = item[0]
                if kind == "reg":                      # 명령 저장 결과
                    _, ok, name, result = item
                    save_btn.state(["!disabled"])
                    if ok:
                        set_status(f"저장됨 → {name} : {_format_command(result)}", "ok")
                        text_var.set("")
                        refresh_list()
                    else:
                        set_status(f"저장하지 못했습니다: {result}", "error")
                elif kind == "pose_status" and refresh_pose_list:   # 촬영 진행 안내 (카운트다운 등)
                    set_pose_status(item[1], "busy")
                elif kind == "pose_done" and refresh_pose_list:     # 촬영·등록 결과
                    _, ok, msg = item
                    capture_btn.state(["!disabled"])
                    if ok:
                        pose_name_var.set("")
                    refresh_pose_list()
                    set_pose_status(msg, "ok" if ok else "error")
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
