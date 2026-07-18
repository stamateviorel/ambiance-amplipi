"""Siren: the silent selftest (WAV validation) and the dry loop's on/off + per-loop
re-assert callback. No audio."""
import os
import tempfile
import time
import unittest
import wave

from ambiance.alarm import Siren


def _make_wav(path, seconds=0.05, rate=8000):
    w = wave.open(path, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(b"\x00\x00" * int(rate * seconds))
    w.close()


class TestSirenSelftest(unittest.TestCase):
    def test_valid_wav_ok(self):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            _make_wav(path)
            r = Siren(path, dry=True).selftest()
            self.assertTrue(r["ok"])
            self.assertEqual(r["rate"], 8000)
            self.assertGreater(r["dur"], 0)
        finally:
            os.unlink(path)

    def test_missing_file_fails(self):
        r = Siren("/nonexistent/alarm.wav", dry=True).selftest()
        self.assertFalse(r["ok"])
        self.assertIn("missing", r["reason"])

    def test_garbage_file_fails(self):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.write(fd, b"this is not a wav")
        os.close(fd)
        try:
            r = Siren(path, dry=True).selftest()
            self.assertFalse(r["ok"])
        finally:
            os.unlink(path)


class TestSirenLoop(unittest.TestCase):
    def test_on_off_and_reassert_callback(self):
        hits = []
        s = Siren("x.wav", dry=True, on_loop=lambda: hits.append(1))
        self.assertFalse(s.active)
        s.on()
        self.assertTrue(s.active)
        end = time.time() + 2
        while not hits and time.time() < end:
            time.sleep(0.02)
        self.assertTrue(hits)          # the watchdog belt fired at least once
        s.off()
        self.assertFalse(s.active)

    def test_double_on_is_single_loop(self):
        s = Siren("x.wav", dry=True)
        s.on()
        s.on()                         # idempotent — no second loop thread
        self.assertTrue(s.active)
        s.off()
        self.assertFalse(s.active)


if __name__ == "__main__":
    unittest.main()
