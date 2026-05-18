"""
LMS 영상 폴더 감시 도구
- 지정 폴더를 주기적으로 감시 → 새 MP4 자동 분석
- 분석 결과를 GUI 현황판에 표시
- Excel 보고서에 누적 기록
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import threading
import queue
import time

try:
    import openpyxl
    EXCEL_OK = True
except ImportError:
    EXCEL_OK = False

# checker.py에서 핵심 로직 import (단일 소스 유지)
from checker import check_file, get_bin, save_excel, REPORT_FILENAME, EXCEL_OK

# ── 경로 기본값 ────────────────────────────────────────────────
WATCH_DIR_DEFAULT  = os.environ.get("LMS_WATCH_PATH", r"\\ds112.kcu.ac\kcubackup\UPLOADLIST\2026\10")
REPORT_DIR_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "검수보고서")
SCAN_INTERVAL      = 5   # 폴더 감시 주기 (초)

# ── 상태 전역 변수 ─────────────────────────────────────────────
watching    = False
seen_files  = set()   # 이미 처리한 파일 경로
result_list = []      # 누적 분석 결과
work_queue  = queue.Queue()


# ※ check_file, get_bin, save_excel, REPORT_FILENAME → checker.py에서 import


# ── 폴더 감시 스레드 ───────────────────────────────────────────
def watch_thread(watch_dir, interval):
    global watching, seen_files
    while watching:
        try:
            if os.path.isdir(watch_dir):
                for fname in os.listdir(watch_dir):
                    if not fname.lower().endswith(".mp4"):
                        continue
                    fpath = os.path.join(watch_dir, fname)
                    if fpath in seen_files:
                        continue
                    # 파일이 완전히 복사될 때까지 대기 (크기 안정화 확인)
                    try:
                        size1 = os.path.getsize(fpath)
                        time.sleep(2)
                        size2 = os.path.getsize(fpath)
                        if size1 != size2:
                            continue  # 아직 복사 중
                    except Exception:
                        continue
                    seen_files.add(fpath)
                    work_queue.put(fpath)
        except Exception as e:
            pass
        time.sleep(interval)


# ── 분석 워커 스레드 ───────────────────────────────────────────
def analysis_worker(report_path):
    while True:
        fpath = work_queue.get()
        if fpath is None:
            break
        # GUI 업데이트: 분석 중 표시
        root.after(0, lambda f=fpath: add_row_analyzing(f))

        result = check_file(fpath)
        result_list.append(result)

        # GUI 업데이트: 결과 반영
        root.after(0, lambda r=result: update_row(r))

        # Excel 저장 (자동감시 시트 + 통합 시트)
        save_excel(report_path, [result], "자동감시")
        save_excel(report_path, [result], "통합")

        # 상태바 업데이트
        root.after(0, update_status)


# ── GUI 업데이트 함수 ──────────────────────────────────────────
pending_rows = {}   # fpath → iid

def add_row_analyzing(fpath):
    fname = os.path.basename(fpath)
    iid = tree.insert("", "end",
        values=(fname, "분석 중...", "-", "-", "-", "-", "-", "-", "-", "-"),
        tags=("analyzing",))
    pending_rows[fpath] = iid
    status_var.set(f"분석 중: {fname}")


def update_row(r):
    iid = pending_rows.pop(r["filepath"], None)
    if iid is None:
        return

    codec_txt = r.get("codec", "-") or "-"
    res_txt   = f"{r.get('width',0)}×{r.get('height',0)}" if r.get("width") else "-"
    fps_txt   = f"{r.get('fps',0):.2f}" if r.get("fps") else "-"
    bit_txt   = f"{r.get('bitrate',0)}kbps" if r.get("bitrate") else "-"
    vfr_txt   = "✅ CFR" if not r["vfr"] else "❌ VFR"
    fs_txt    = "✅ 있음" if r["faststart"] else "❌ 없음"
    aud_txt   = "✅ 정상" if r["audio_ok"] else "❌ 문제"
    dts_txt   = "✅ 정상" if not r["dts_error"] else "❌ 오류"
    issue_txt = " / ".join(r["issues"]) if r["issues"] else "없음"
    tag       = "problem" if r["issues"] else "ok"

    tree.item(iid, values=(r["filename"], codec_txt, res_txt, fps_txt, bit_txt,
                           vfr_txt, fs_txt, aud_txt, dts_txt, issue_txt),
              tags=(tag,))
    tree.see(iid)


def update_status():
    total   = len(result_list)
    problem = sum(1 for r in result_list if r["issues"])
    ok      = total - problem
    state_txt = "감시 중 🟢" if watching else "중지됨 🔴"
    status_var.set(
        f"{state_txt}  |  누적: {total}개  정상: {ok}개  문제: {problem}개  "
        f"|  폴더: {watch_dir_var.get()}"
    )


# ── 시작/중지 ─────────────────────────────────────────────────
def toggle_watch():
    global watching

    if watching:
        # 중지
        watching = False
        btn_toggle.config(text="▶ 감시 시작", bg="#4a90d9")
        update_status()
    else:
        # 시작
        watch_dir  = watch_dir_var.get().strip()
        report_dir = report_dir_var.get().strip()

        if not watch_dir:
            messagebox.showwarning("경고", "감시 폴더 경로를 입력해주세요.")
            return
        if not os.path.isdir(watch_dir):
            if not messagebox.askyesno("경고",
                    f"폴더에 접근할 수 없습니다:\n{watch_dir}\n\n그래도 시작하시겠습니까?"):
                return
        if not os.path.isdir(report_dir):
            try:
                os.makedirs(report_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("오류", f"보고서 폴더 생성 실패:\n{e}")
                return

        report_path = os.path.join(report_dir, REPORT_FILENAME)
        watching = True
        btn_toggle.config(text="⏹ 감시 중지", bg="#e74c3c")

        threading.Thread(target=watch_thread,
                         args=(watch_dir, SCAN_INTERVAL),
                         daemon=True).start()
        threading.Thread(target=analysis_worker,
                         args=(report_path,),
                         daemon=True).start()
        update_status()


def select_watch_dir():
    d = filedialog.askdirectory(title="감시 폴더 선택")
    if d:
        watch_dir_var.set(d)

def select_report_dir():
    d = filedialog.askdirectory(title="보고서 저장 폴더 선택")
    if d:
        report_dir_var.set(d)

def open_report():
    import sys
    report_path = os.path.join(report_dir_var.get().strip(), REPORT_FILENAME)
    if os.path.exists(report_path):
        if sys.platform == "darwin":
            import subprocess; subprocess.Popen(["open", report_path])
        elif sys.platform == "win32":
            os.startfile(report_path)
        else:
            import subprocess; subprocess.Popen(["xdg-open", report_path])
    else:
        messagebox.showinfo("알림", "아직 저장된 보고서가 없습니다.\n파일이 감지되면 자동으로 생성됩니다.")

def clear_table():
    if not messagebox.askyesno("확인", "현황판을 초기화하시겠습니까?\n(Excel 보고서 내용은 유지됩니다)"):
        return
    for row in tree.get_children():
        tree.delete(row)
    result_list.clear()
    seen_files.clear()
    update_status()


# ── UI ───────────────────────────────────────────────────────
root = tk.Tk()
root.title("LMS 영상 재생 검수")
root.geometry("1100x650")
root.resizable(True, True)

# 상단 경로 설정 영역
frame_top = tk.LabelFrame(root, text="설정", padx=10, pady=6)
frame_top.pack(fill="x", padx=10, pady=(8, 4))

watch_dir_var  = tk.StringVar(value=WATCH_DIR_DEFAULT)
report_dir_var = tk.StringVar(value=REPORT_DIR_DEFAULT)

tk.Label(frame_top, text="감시 폴더:", width=10, anchor="w").grid(row=0, column=0, sticky="w")
tk.Entry(frame_top, textvariable=watch_dir_var, width=70).grid(row=0, column=1, sticky="ew", padx=4)
tk.Button(frame_top, text="선택", command=select_watch_dir, width=6).grid(row=0, column=2)

tk.Label(frame_top, text="보고서 폴더:", width=10, anchor="w").grid(row=1, column=0, sticky="w", pady=4)
tk.Entry(frame_top, textvariable=report_dir_var, width=70).grid(row=1, column=1, sticky="ew", padx=4)
tk.Button(frame_top, text="선택", command=select_report_dir, width=6).grid(row=1, column=2)

frame_top.columnconfigure(1, weight=1)

if not EXCEL_OK:
    tk.Label(frame_top, text="⚠ openpyxl 미설치 — Excel 저장 비활성화 (pip install openpyxl)",
             fg="#c0392b").grid(row=2, column=0, columnspan=3, sticky="w", pady=2)

# 버튼 영역
frame_btn = tk.Frame(root, padx=10, pady=4)
frame_btn.pack(fill="x")

btn_toggle = tk.Button(frame_btn, text="▶ 감시 시작", command=toggle_watch,
                       width=14, bg="#4a90d9", fg="white", font=("맑은 고딕", 10, "bold"))
btn_open   = tk.Button(frame_btn, text="📊 보고서 열기", command=open_report,
                       width=14, bg="#e67e22", fg="white", font=("맑은 고딕", 10, "bold"))
btn_clear  = tk.Button(frame_btn, text="🗑 현황판 초기화", command=clear_table,
                       width=14, bg="#7f8c8d", fg="white", font=("맑은 고딕", 10, "bold"))

btn_toggle.pack(side="left", padx=4)
btn_open.pack(side="left", padx=4)
btn_clear.pack(side="left", padx=4)
tk.Label(frame_btn,
         text=f"* {SCAN_INTERVAL}초마다 감시 폴더를 확인합니다",
         fg="gray").pack(side="left", padx=10)

# 현황판 테이블
frame_tree = tk.Frame(root, padx=10)
frame_tree.pack(fill="both", expand=True)

cols = ("파일명", "코덱", "해상도", "FPS", "비트레이트", "프레임레이트", "Faststart", "오디오", "타임스탬프", "문제 항목")
tree = ttk.Treeview(frame_tree, columns=cols, show="headings", selectmode="extended")

tree.heading("파일명",      text="파일명")
tree.heading("코덱",        text="코덱")
tree.heading("해상도",      text="해상도")
tree.heading("FPS",        text="FPS")
tree.heading("비트레이트",  text="비트레이트")
tree.heading("프레임레이트", text="프레임레이트")
tree.heading("Faststart",  text="Faststart")
tree.heading("오디오",      text="오디오")
tree.heading("타임스탬프",  text="타임스탬프")
tree.heading("문제 항목",   text="문제 항목")

tree.column("파일명",      width=220)
tree.column("코덱",        width=65,  anchor="center")
tree.column("해상도",      width=100, anchor="center")
tree.column("FPS",        width=55,  anchor="center")
tree.column("비트레이트",  width=85,  anchor="center")
tree.column("프레임레이트", width=95,  anchor="center")
tree.column("Faststart",  width=80,  anchor="center")
tree.column("오디오",      width=75,  anchor="center")
tree.column("타임스탬프",  width=80,  anchor="center")
tree.column("문제 항목",   width=320)

tree.tag_configure("problem",   background="#ffe5e5")
tree.tag_configure("ok",        background="#e8f5e9")
tree.tag_configure("analyzing", background="#fff9c4")

scrollbar = ttk.Scrollbar(frame_tree, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=scrollbar.set)
tree.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

# 상태바
frame_bot = tk.Frame(root, padx=10, pady=6, bg="#2c3e50")
frame_bot.pack(fill="x", side="bottom")

status_var = tk.StringVar(value="중지됨 🔴  |  감시 폴더를 설정하고 [감시 시작]을 누르세요.")
tk.Label(frame_bot, textvariable=status_var, anchor="w",
         fg="white", bg="#2c3e50", font=("맑은 고딕", 9)).pack(fill="x", padx=4)

root.mainloop()
