# LMS 영상 자동화 기술 노트

> 작성일: 2026-05-18  
> 최종수정: 2026-05-18

---

## CDN 구조 확인

| 항목 | 값 |
|------|----|
| CDN 서비스 | NCP Global Edge |
| Edge 도메인 | `fkz4vab0536.edge.naverncp.com` (lect-media, 운영중) |
| 원본(오리진) | `lect-media.kr.object.ncloudstorage.com` |
| CDN KEY | `rKufq0NOfCmrfF8e8KAGxg__` (퍼지 경로용) |

### 파일 접근 URL 구조
```
https://fkz4vab0536.edge.naverncp.com/{year}/{semester}/{code6}/{professorID}/{code}/{week}/{filename}.mp4
```

### 퍼지 경로 구조 (ncp-purge 도구)
```
/hls/{CDN_KEY}/{year}/{semester}/{code6}/{professorID}/{code}/{week}/*
```

---

## ffprobe URL 직접 검수

CDN 파일이 공개 접근 가능(인증 없음) 확인됨 → ffprobe URL로 바로 검수 가능.

```bash
ffprobe -v quiet -print_format json -show_streams -show_format \
  "https://fkz4vab0536.edge.naverncp.com/2026/10/BA1003/1630027/BA100301/1/BA100301_1_1.mp4"
```

### URL 검수 시 생략 항목
- **DTS 역전 검사 생략**: 네트워크 부하 (300패킷 스캔) → URL에선 skip
- **Faststart**: Range 요청으로 앞 200KB 읽어서 moov/mdat 위치 확인

---

## 다운로드 구현

```python
import urllib.request

def download_url(url, save_path):
    def progress(block, block_size, total):
        pct = min(int(block * block_size * 100 / total), 100)
        # UI에 진행률 전달
    urllib.request.urlretrieve(url, save_path, reporthook=progress)
```

저장 위치: `D:\project\vfr_v2\입력영상\{filename}`

---

## 업로드 구현 (미구현 - 계획)

NCP Object Storage = S3 호환 API → boto3 사용 가능

```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='https://kr.object.ncloudstorage.com',
    aws_access_key_id='NCP_ACCESS_KEY',
    aws_secret_access_key='NCP_SECRET_KEY',
)

# 원본 URL에서 경로 추출 후 동일 경로에 업로드
# https://fkz4vab0536.edge.naverncp.com/2026/10/BA1003/.../BA100301_1_1.mp4
# → 버킷: lect-media
# → 키: 2026/10/BA1003/.../BA100301_1_1.mp4

s3.upload_file(
    local_path,
    'lect-media',
    object_key,
    ExtraArgs={'ContentType': 'video/mp4'}
)
```

### URL → Object Storage 경로 변환
```python
def url_to_object_key(url):
    # https://fkz4vab0536.edge.naverncp.com/2026/10/...
    # → 2026/10/...
    from urllib.parse import urlparse
    return urlparse(url).path.lstrip('/')
```

---

## 퍼지 연동 (미구현 - 계획)

업로드 완료 후 해당 경로 자동 퍼지.  
NCP CDN API 또는 ncp-purge 도구(`D:\project\ncp-purge\`) 활용.

```
퍼지 대상 경로:
/hls/{CDN_KEY}/{year}/{semester}/{code6}/{professorID}/{code}/{week}/*
```

---

## 전체 흐름 코드 스케치

```python
def full_pipeline(cdn_url):
    # 1. 검수
    result = check_file(cdn_url)
    if not result['issues']:
        return '정상 - 처리 불필요'

    # 2. 다운로드
    local_path = download(cdn_url)

    # 3. 변환
    fixed_path = convert_file(local_path, output_dir)

    # 4. 업로드 (동일 경로 덮어쓰기)
    object_key = url_to_object_key(cdn_url)
    s3_upload(fixed_path, 'lect-media', object_key)

    # 5. 퍼지
    purge_path = build_purge_path(cdn_url)
    ncp_purge(purge_path)
```

---

## 필요 라이브러리

```
boto3          # NCP Object Storage 업로드
urllib.request # 다운로드 (표준 라이브러리, 추가 설치 불필요)
```

---

## 참고

- NCP Object Storage 엔드포인트: `https://kr.object.ncloudstorage.com`
- NCP Access Key 발급: NCP 콘솔 → 마이페이지 → 계정관리 → 인증키 관리
- boto3 설치: `pip install boto3`

---

## 현재 탭 구조 및 Excel 중복 문제

### 탭 구조 (현재)
```
[📋 수동 검수] [🔗 URL 검수] [👁 자동 감시] [📊 보고서]
```

### Excel 저장 구조 (현재)
| 탭 | 저장 시트 |
|----|---------|
| 수동 검수 | "수동검수" + "통합" |
| URL 검수 | "URL검수" + "통합" |
| 자동 감시 | "자동감시" + "통합" |

### 중복 기록 발생 시나리오
```
1. URL 검수 탭에서 CDN URL 검수
   → "URL검수" 시트 저장 + "통합" 시트 저장 (1회)

2. URL 검수 결과에서 [다운로드] 클릭 → 입력영상/ 폴더에 저장

3. 수동 검수 탭 → 스캔 → 동일 파일 재검수
   → "수동검수" 시트 저장 + "통합" 시트 저장 (2회 = 중복!)
```

**결과**: 보고서 통합 시트에 동일 파일 2건 집계 → 문제 비율 왜곡

---

## UI 통합 개편 방향 (검토 중)

### 목표 탭 구조
```
[📋 통합 검수] [👁 자동 감시] [📊 보고서]
```

### 통합 검수 탭 UI 레이아웃
```
┌──────────────────────────────────────────────────────┐
│ CDN URL  [https://...mp4__________________] [검수]    │
├──────────────────────────────────────────────────────┤
│ 입력폴더  [D:\...\입력영상________________] [선택]    │
│ 출력폴더  [D:\...\출력영상________________] [선택]    │
├──────────────────────────────────────────────────────┤
│ [스캔 시작]  [선택파일 변환]  [전체선택] ...          │
└──────────────────────────────────────────────────────┘

결과 테이블 (URL + 로컬 파일 통합)
┌──────────┬──────────────────┬────┬──────┬─────────────────────┐
│ 감지시각  │ 파일명           │ .. │ 판정 │ 액션                │
├──────────┼──────────────────┼────┼──────┼─────────────────────┤
│ 15:34:03 │ BA100301_1_1.mp4 │ .. │ 문제 │ [⬇ 다운로드&변환]   │ ← URL
│ 15:36:00 │ DO103001_2_3.mp4 │ .. │ 문제 │ [☑ 선택] [변환]     │ ← 로컬
└──────────┴──────────────────┴────┴──────┴─────────────────────┘
```

### 핵심 변경점
| 항목 | 현재 | 변경 후 |
|------|------|---------|
| URL 검수 | 별도 탭 | 통합 검수 탭 상단 입력줄 |
| URL 파일 변환 | 수동 탭으로 이동 필요 | 결과 행에서 [다운로드&변환] 바로 처리 |
| Excel 저장 | URL/수동 각각 + 통합 (중복) | 통합 시트 하나만 |
| 소스 구분 | 탭 분리 | 결과 테이블 "소스" 컬럼 (URL/로컬) |

> ⚠️ 기존 수동 검수 탭 사용자 흐름에 영향 있음 → 별도 검토 후 단계적 적용

---

## 다운로드 → 변환 자동 연결 (구현 계획)

현재: URL 검수 → 다운로드 → **수동으로** 수동검수 탭으로 이동 → 변환  
목표: URL 검수 결과 행 → **[다운로드&변환] 버튼 한 번**으로 처리

```python
def download_and_convert(url, output_dir):
    # 1. 다운로드
    fname = url.split("/")[-1]
    local_path = os.path.join(INPUT_DIR, fname)
    urllib.request.urlretrieve(url, local_path, reporthook=progress_cb)

    # 2. 변환
    fix_path = convert_file(local_path, output_dir)  # → 출력영상/{fname}_fix.mp4

    return fix_path
```

진행 상태 표시 순서:
1. `다운로드 중... XX%`
2. `변환 중...`
3. `완료 → 출력영상/{fname}_fix.mp4`
