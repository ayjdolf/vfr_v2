# LMS 영상 검수 도구 (vfr_v2)

pywebview 기반 HTML UI로 LMS 영상을 검수하고, 실시간 폴더 감시 및 Excel/TXT 보고서를 지원.

## 실행 방법

```bash
pip install pywebview openpyxl python-dotenv
cp .env.example .env   # .env에 LMS_WATCH_PATH 설정
```

| 실행 파일 | 설명 |
|----------|------|
| `LMS영상검수_통합도구.bat` | 수동 검수 + 자동 감시 + 변환 (전체 기능) |
| `LMS영상검수_자동감시(경량).bat` | 자동 감시 전용 tkinter 경량 버전 |

## 환경 변수 (.env)

| 변수 | 설명 |
|------|------|
| `LMS_WATCH_PATH` | 감시할 LMS 영상 폴더 경로 |

- Windows: `\\ds112.kcu.ac\kcubackup\UPLOADLIST\2026\10`
- Mac (SMB 마운트): `/Volumes/kcubackup/UPLOADLIST/2026/10`

## 검수 항목 및 기준값

정보기술처 공식 권장값 기준 (2026.3.25. 가이드)

| 항목 | 기준 | 문제 시 |
|------|------|--------|
| 코덱 | H.264 | 코덱 비권장 표시 |
| 해상도 | 1280×720 이상 | 해상도 미달 표시 |
| 프레임레이트 | CFR 30fps | VFR/불일치 표시 |
| 비트레이트 | 1000kbps 이상 | 비트레이트 부족 표시 |
| 오디오 | 48000Hz 스테레오 | 샘플레이트/채널 오류 표시 |
| Faststart | moov atom 파일 앞 | faststart 없음 표시 |
| 타임스탬프 | DTS 정상, time_base 정상 | 오류 표시 |

## 보고서

```
검수보고서/
├── LMS영상검수보고서.xlsx   ← 수동검수 / 자동감시 / 통합 시트
├── LMS영상검수_로그.jsonl   ← JSONL 자동 백업
└── 검수보고서_YYYYMMDD_HHMMSS.txt  ← TXT 보고서 (선택 파일 내보내기)
```

## 폴더 구조

```
vfr_v2/
├── app.py                      # 메인 진입점 (pywebview GUI)
├── checker.py                  # 검수 핵심 로직 (단일 소스)
├── index.html                  # 웹뷰 UI
├── lms_watch.py                # 자동 감시 전용 (tkinter 경량)
├── LMS영상검수_통합도구.bat     # 전체 기능 실행
├── LMS영상검수_자동감시(경량).bat # 경량 감시 실행
├── .env / .env.example         # 환경 변수
├── 입력영상/                   # 검수할 MP4
├── 출력영상/                   # 변환 결과
└── 검수보고서/                  # Excel + TXT 보고서 저장
```

## 의존성

```
pywebview
openpyxl
python-dotenv
```

ffmpeg / ffprobe는 시스템 PATH 또는 동일 폴더에 위치 필요
- Windows: 폴더에 ffmpeg.exe, ffprobe.exe 복사
- Mac: `brew install ffmpeg`

> **참고**: `libfdk_aac`는 표준 ffmpeg 빌드에 포함되지 않아 변환 시 `aac` 인코더를 사용합니다.
> 128kbps에서 품질 차이 없음. 정보기술처 빠른설정(F6) 기준 AAC/LC와 동일.

## 변환 설정값 (convert_file)

정보기술처 공식 매개변수(F8) 기준으로 적용 (2026.3.25. 가이드)

| 항목 | 값 |
|------|---|
| 입력 플래그 | `-fflags +genpts+igndts` |
| 타임스탬프 | `-avoid_negative_ts make_zero -start_at_zero` |
| 비디오 코덱 | `libx264 / 1000kbps` |
| 프로파일 | `high / level 4.1` |
| 픽셀 포맷 | `yuv420p` |
| 프레임레이트 | `CFR 30fps (fps=30, setpts=PTS-STARTPTS, setsar=1)` |
| GOP | `g=60, keyint_min=60, sc_threshold=0` |
| 프리셋 | `medium / bf=2` |
| 오디오 코덱 | `aac / 128kbps` |
| 오디오 | `48000Hz / 스테레오(2ch) / aresample=async=1` |
| 먹싱 버퍼 | `-max_muxing_queue_size 1024` |
| Faststart | `-movflags +faststart` |

## Mac 이식 시 참고

- `.env`에서 `LMS_WATCH_PATH`를 SMB 마운트 경로로 변경
- `subprocess.CREATE_NO_WINDOW` → 크로스플랫폼 처리 완료 (`_NO_WINDOW` 조건부 적용)
- `os.startfile` → 크로스플랫폼 처리 완료
- ffmpeg: `brew install ffmpeg`
