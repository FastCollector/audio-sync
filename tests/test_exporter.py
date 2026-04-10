from unittest.mock import Mock

from app.core.exporter import build_export_command, export_synced


def test_positive_offset_uses_adelay_on_audio_b():
    cmd = build_export_command("in.mp4", "b.wav", "out.mp4", offset_seconds=0.25)

    assert "-af:a:1" in cmd
    assert "adelay=250|250" in cmd


def test_negative_offset_prepends_silence_to_audio_a():
    cmd = build_export_command("in.mp4", "b.wav", "out.mp4", offset_seconds=-0.2)

    assert "-af:a:0" in cmd
    assert "adelay=200|200" in cmd


def test_dual_track_mapping_present_in_args():
    cmd = build_export_command("in.mp4", "b.wav", "out.mp4", offset_seconds=0.0)

    joined = " ".join(cmd)
    assert "-map 0:v" in joined
    assert "-map 0:a" in joined
    assert "-map 1:a" in joined


def test_export_calls_subprocess_with_generated_command(monkeypatch):
    mocked = Mock()
    monkeypatch.setattr("app.core.exporter.subprocess.run", mocked)

    cmd = export_synced("in.mp4", "b.wav", "out.mp4", offset_seconds=0.1)

    mocked.assert_called_once_with(cmd, check=True)
