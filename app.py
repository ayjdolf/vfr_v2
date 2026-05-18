# -*- coding: utf-8 -*-
import webview
import os, sys, threading, time, queue, json
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
from checker import check_file, save_excel, save_txt_report, convert_file, get_bin, REPORT_FILENAME, EXCEL_OK

LOG_FILENAME  = "LMS영상검수_로그.jsonl"   # 결과 JSON 백업 (Excel 실패해도 항상 기록)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "검수보고서")   # Excel + TXT 저장 폴더
os.makedirs(REPORT_DIR, exist_ok=True)
_window    = None   # webview 창


class API:
    def __init__(self):
        self._watching   = False
        self._seen       = set()
        self._results    = []   # 전체 누적 (수동 + 자동)
        self._work_q     = queue.Queue()
        self._excel_lock = threading.Lock()   # Excel 동시 쓰기 방지

    # ── 결과 저장 (Lock 보호 + JSONL 백업) ────────────────────
    def _save_result(self, result, report_path, sheet_name):
        # 1) JSONL 백업 (항상 먼저, 잠금 불필요)
        log_path = os.path.join(REPORT_DIR, LOG_FILENAME)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception:
            pass

        # 2) Excel: 해당 시트 + 통합 시트에 동시 저장 (Lock으로 순차 처리)
        with self._excel_lock:
            save_excel(report_path, [result], sheet_name)
            save_excel(report_path, [result], "통합")

    # ── 폴더 선택 다이얼로그 ──────────────────────────────────
    def select_folder(self):
        dirs = _window.create_file_dialog(webview.FOLDER_DIALOG)
        return dirs[0] if dirs else None

    # ── 기본 경로 반환 ─────────────────────────────────────────
    def get_defaults(self):
        return {
            "input":       os.path.join(BASE_DIR, "입력영상"),
            "output":      os.path.join(BASE_DIR, "출력영상"),
            "watch":       os.environ.get("LMS_WATCH_PATH", r"\\ds112.kcu.ac\kcubackup\UPLOADLIST\2026\10"),
            "report_dir":  REPORT_DIR,
            "report_file": os.path.join(REPORT_DIR, REPORT_FILENAME),
            "excel_ok":    EXCEL_OK,
        }

    # ── URL 단건 검수 ──────────────────────────────────────────
    def check_url(self, url):
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return {"error": "http:// 또는 https:// 로 시작하는 URL을 입력하세요."}

        report_path = os.path.join(REPORT_DIR, REPORT_FILENAME)

        def run():
            _window.evaluate_js(
                f"Bridge.onAnalyzing({json.dumps(url.split('/')[-1])}, 'url')")
            result = check_file(url)
            self._results.append(result)
            self._save_result(result, report_path, "URL검수")
            _window.evaluate_js(
                f"Bridge.onResult({json.dumps(result)}, 'url')")
            _window.evaluate_js("Bridge.onScanDone()")

        threading.Thread(target=run, daemon=True).start()
        return {"status": "ok"}

    # ── 수동 스캔 ──────────────────────────────────────────────
    def scan_folder(self, input_dir):
        if not os.path.isdir(input_dir):
            return {"error": "폴더를 찾을 수 없습니다"}
        mp4s = [f for f in os.listdir(input_dir) if f.lower().endswith(".mp4")]
        if not mp4s:
            return {"error": "MP4 파일이 없습니다", "count": 0}

        report_path = os.path.join(REPORT_DIR, REPORT_FILENAME)

        def run():
            for fname in mp4s:
                fpath = os.path.join(input_dir, fname)
                _window.evaluate_js(
                    f"Bridge.onAnalyzing({json.dumps(fname)}, 'manual')")
                result = check_file(fpath)
                self._results.append(result)
                self._save_result(result, report_path, "수동검수")
                _window.evaluate_js(
                    f"Bridge.onResult({json.dumps(result)}, 'manual')")
            _window.evaluate_js("Bridge.onScanDone()")

        threading.Thread(target=run, daemon=True).start()
        return {"status": "ok", "count": len(mp4s)}

    # ── 변환 ──────────────────────────────────────────────────
    def convert_files(self, filepaths, output_dir):
        if not filepaths:
            return {"error": "선택된 파일 없음"}
        os.makedirs(output_dir, exist_ok=True)

        def run():
            total = len(filepaths)
            for i, fpath in enumerate(filepaths):
                fname = os.path.basename(fpath)
                _window.evaluate_js(
                    f"Bridge.onConverting({json.dumps(fname)}, {i+1}, {total})")
                convert_file(fpath, output_dir)
            _window.evaluate_js(
                f"Bridge.onConvertDone({total}, {json.dumps(output_dir)})")

        threading.Thread(target=run, daemon=True).start()
        return {"status": "ok", "count": len(filepaths)}

    # ── 자동 감시 시작 ─────────────────────────────────────────
    def start_watch(self, watch_dir, report_dir):
        if self._watching:
            return {"error": "이미 감시 중"}
        self._watching = True
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(REPORT_DIR, REPORT_FILENAME)

        def watcher():
            while self._watching:
                try:
                    if os.path.isdir(watch_dir):
                        for fname in os.listdir(watch_dir):
                            if not fname.lower().endswith(".mp4"):
                                continue
                            fpath = os.path.join(watch_dir, fname)
                            if fpath in self._seen:
                                continue
                            try:
                                s1 = os.path.getsize(fpath)
                                time.sleep(2)
                                s2 = os.path.getsize(fpath)
                                if s1 != s2:
                                    continue
                            except Exception:
                                continue
                            self._seen.add(fpath)
                            self._work_q.put(fpath)
                except Exception:
                    pass
                time.sleep(5)

        # 로컬 임시 복사 폴더
        tmp_dir = os.path.join(BASE_DIR, "_tmp_watch")
        os.makedirs(tmp_dir, exist_ok=True)

        def worker():
            while self._watching:
                try:
                    fpath = self._work_q.get(timeout=1)
                except queue.Empty:
                    continue
                fname = os.path.basename(fpath)
                _window.evaluate_js(
                    f"Bridge.onAnalyzing({json.dumps(fname)}, 'watch')")

                # 로컬로 복사 후 분석 (원본이 클라우드로 이동해도 안전)
                tmp_path = os.path.join(tmp_dir, fname)
                try:
                    import shutil
                    shutil.copy2(fpath, tmp_path)
                    analyze_path = tmp_path
                except Exception:
                    # 복사 실패(이미 사라진 경우) → 원본으로 시도
                    analyze_path = fpath

                result = check_file(analyze_path)
                result["filename"] = fname          # 원본 파일명 유지
                result["filepath"] = fpath          # 원본 경로 기록

                # 임시 파일 삭제
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

                self._results.append(result)
                self._save_result(result, report_path, "자동감시")
                _window.evaluate_js(
                    f"Bridge.onResult({json.dumps(result)}, 'watch')")
                _window.evaluate_js(
                    f"Bridge.onStats({json.dumps(self._stats())})")

        threading.Thread(target=watcher, daemon=True).start()
        threading.Thread(target=worker,  daemon=True).start()
        return {"status": "started"}

    # ── 자동 감시 중지 ─────────────────────────────────────────
    def stop_watch(self):
        self._watching = False
        return {"status": "stopped"}

    # ── 전체 결과 Excel 저장 ───────────────────────────────────
    def save_all_results(self):
        if not self._results:
            return {"status": "empty"}
        report_path = os.path.join(REPORT_DIR, REPORT_FILENAME)
        with self._excel_lock:
            ok = save_excel(report_path, self._results, "통합")
        return {"status": "ok" if ok else "fail",
                "count": len(self._results), "path": report_path}

    # ── 현황판 초기화 ──────────────────────────────────────────
    def clear_results(self):
        self._results.clear()
        self._seen.clear()
        return {"status": "ok"}

    # ── TXT 보고서 내보내기 ────────────────────────────────────
    def export_txt_report(self, results):
        from datetime import datetime
        default_name = f"검수보고서_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        paths = _window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory=REPORT_DIR,
            save_filename=default_name
        )
        if not paths:
            return {"status": "cancelled"}
        path = paths if isinstance(paths, str) else paths[0]
        ok = save_txt_report(path, results)
        return {"status": "ok", "path": path} if ok else {"error": "저장 실패"}

    # ── Excel 보고서 열기 ──────────────────────────────────────
    def open_report(self, path):
        if os.path.exists(path):
            if sys.platform == "darwin":
                import subprocess; subprocess.Popen(["open", path])
            elif sys.platform == "win32":
                os.startfile(path)
            else:
                import subprocess; subprocess.Popen(["xdg-open", path])
            return {"status": "ok"}
        return {"error": "파일 없음"}

    # ── 통계 반환 ──────────────────────────────────────────────
    def get_stats(self):
        return self._stats()

    def _stats(self):
        total    = len(self._results)
        problems = sum(1 for r in self._results if r["issues"])
        return {
            "total":    total,
            "ok":       total - problems,
            "problems": problems,
            "watching": self._watching,
        }


if __name__ == "__main__":
    api = API()
    _window = webview.create_window(
        title="LMS 영상 재생 검수 시스템",
        url=os.path.join(BASE_DIR, "index.html"),
        js_api=api,
        width=1200,
        height=750,
        min_size=(1000, 650),
    )
    webview.start()
