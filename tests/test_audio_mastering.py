import subprocess
import tempfile
import unittest
from pathlib import Path

from haizflow.pipeline.slide_composer import _binary, get_video_duration, mix_master_audio


def _tone(path: Path, freq: int, seconds: float, volume: float = 0.5) -> None:
    subprocess.run(
        [_binary("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={seconds}", "-af", f"volume={volume}", str(path)],
        check=True,
    )


class AudioMasteringTests(unittest.TestCase):
    def test_voice_only_master(self):
        with tempfile.TemporaryDirectory() as tmp:
            voice = Path(tmp) / "voice.wav"
            _tone(voice, 220, 3)
            out = mix_master_audio(voice, Path(tmp) / "out.m4a", bgm_path=None)
            self.assertTrue(out.is_file())
            self.assertAlmostEqual(get_video_duration(str(out)), 3.0, delta=0.6)

    def test_voice_with_ducked_bgm(self):
        with tempfile.TemporaryDirectory() as tmp:
            voice = Path(tmp) / "voice.wav"
            bgm = Path(tmp) / "bgm.wav"
            _tone(voice, 220, 4)
            _tone(bgm, 440, 1)
            out = mix_master_audio(voice, Path(tmp) / "out.m4a", bgm_path=bgm, bgm_volume=0.1)
            self.assertTrue(out.is_file())
            self.assertAlmostEqual(get_video_duration(str(out)), 4.0, delta=0.6)

    def test_master_voice_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            voice = Path(tmp) / "voice.wav"
            _tone(voice, 220, 2)
            out = mix_master_audio(voice, Path(tmp) / "out.m4a", master_voice=False)
            self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
