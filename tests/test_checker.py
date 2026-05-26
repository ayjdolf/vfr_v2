# -*- coding: utf-8 -*-
"""
checker.py 핵심 로직 단위 테스트
실행: pytest tests/test_checker.py -v
"""
import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from checker import (
    parse_rate, is_url, load_settings, save_settings,
    DEFAULT_SETTINGS, _check_video_stream, _check_audio_stream,
    _check_bitrate,
)


# ── parse_rate ────────────────────────────────────────────────
class TestParseRate:
    def test_integer_fps(self):
        assert parse_rate("30/1") == 30.0

    def test_fractional_fps(self):
        assert abs(parse_rate("30000/1001") - 29.97) < 0.01

    def test_invalid_returns_zero(self):
        assert parse_rate("invalid") == 0.0

    def test_zero_denominator(self):
        assert parse_rate("0/0") == 0.0


# ── is_url ────────────────────────────────────────────────────
class TestIsUrl:
    def test_http(self):
        assert is_url("http://example.com/video.mp4") is True

    def test_https(self):
        assert is_url("https://fkz4vab0536.edge.naverncp.com/2026/10/BA1003/1630027/BA100301/1/BA100301_1_1.mp4") is True

    def test_local_path(self):
        assert is_url(r"D:\project\vfr_v2\입력영상\test.mp4") is False

    def test_none_value(self):
        assert is_url(None) is False


# ── settings ──────────────────────────────────────────────────
class TestSettings:
    def test_load_returns_all_keys(self):
        s = load_settings()
        for key in DEFAULT_SETTINGS:
            assert key in s, f"settings에 '{key}' 키 없음"

    def test_default_fps(self):
        s = load_settings()
        assert s["fps"] == 30

    def test_default_min_resolution(self):
        s = load_settings()
        assert s["min_width"] == 1280
        assert s["min_height"] == 720

    def test_default_codec(self):
        s = load_settings()
        assert s["codec"] == "h264"

    def test_default_audio_sr(self):
        s = load_settings()
        assert s["audio_sr"] == 48000


# ── _check_video_stream ───────────────────────────────────────
class TestCheckVideoStream:
    def _result(self):
        return {"codec": "", "width": 0, "height": 0, "fps": 0.0,
                "vfr": False, "dts_error": False, "issues": []}

    def test_normal_cfr_30fps(self):
        st = {"codec_name": "h264", "width": 1920, "height": 1080,
              "r_frame_rate": "30/1", "avg_frame_rate": "30/1", "time_base": "1/90"}
        r = self._result()
        _check_video_stream(st, DEFAULT_SETTINGS, r)
        assert r["vfr"] is False
        assert "VFR" not in " ".join(r["issues"])

    def test_vfr_detected(self):
        st = {"codec_name": "h264", "width": 1920, "height": 1080,
              "r_frame_rate": "60/1", "avg_frame_rate": "25/1", "time_base": "1/90"}
        r = self._result()
        _check_video_stream(st, DEFAULT_SETTINGS, r)
        assert r["vfr"] is True
        assert any("VFR" in i for i in r["issues"])

    def test_resolution_below_minimum(self):
        st = {"codec_name": "h264", "width": 640, "height": 480,
              "r_frame_rate": "30/1", "avg_frame_rate": "30/1", "time_base": "1/90"}
        r = self._result()
        _check_video_stream(st, DEFAULT_SETTINGS, r)
        assert any("해상도 미달" in i for i in r["issues"])

    def test_hevc_codec_warning(self):
        st = {"codec_name": "hevc", "width": 1920, "height": 1080,
              "r_frame_rate": "30/1", "avg_frame_rate": "30/1", "time_base": "1/90"}
        r = self._result()
        _check_video_stream(st, DEFAULT_SETTINGS, r)
        assert any("H.265" in i for i in r["issues"])

    def test_time_base_90000_not_error(self):
        """1/90000은 정상 인코더에서도 사용 → 단독으로 오류 판정 안 함"""
        st = {"codec_name": "h264", "width": 1920, "height": 1080,
              "r_frame_rate": "30/1", "avg_frame_rate": "30/1", "time_base": "1/90000"}
        r = self._result()
        _check_video_stream(st, DEFAULT_SETTINGS, r)
        assert r["dts_error"] is False
        assert not any("time_base" in i for i in r["issues"])


# ── _check_audio_stream ───────────────────────────────────────
class TestCheckAudioStream:
    def _result(self):
        return {"audio_ok": True, "issues": []}

    def test_normal_audio(self):
        st = {"sample_rate": "48000", "channels": 2}
        r = self._result()
        _check_audio_stream(st, DEFAULT_SETTINGS, r)
        assert r["audio_ok"] is True
        assert r["issues"] == []

    def test_wrong_sample_rate(self):
        st = {"sample_rate": "44100", "channels": 2}
        r = self._result()
        _check_audio_stream(st, DEFAULT_SETTINGS, r)
        assert r["audio_ok"] is False
        assert any("샘플레이트" in i for i in r["issues"])

    def test_mono_channel(self):
        st = {"sample_rate": "48000", "channels": 1}
        r = self._result()
        _check_audio_stream(st, DEFAULT_SETTINGS, r)
        assert r["audio_ok"] is False
        assert any("모노" in i for i in r["issues"])


# ── _check_bitrate ────────────────────────────────────────────
class TestCheckBitrate:
    def test_sufficient_bitrate(self):
        r = {"bitrate": 2000, "issues": []}
        _check_bitrate(r, DEFAULT_SETTINGS)
        assert r["issues"] == []

    def test_insufficient_bitrate(self):
        r = {"bitrate": 500, "issues": []}
        _check_bitrate(r, DEFAULT_SETTINGS)
        assert any("비트레이트 부족" in i for i in r["issues"])

    def test_zero_bitrate_skipped(self):
        """비트레이트 0은 알 수 없음으로 처리 — 이슈 추가 안 함"""
        r = {"bitrate": 0, "issues": []}
        _check_bitrate(r, DEFAULT_SETTINGS)
        assert r["issues"] == []
