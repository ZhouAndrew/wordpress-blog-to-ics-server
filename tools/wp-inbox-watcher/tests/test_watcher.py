import json
import logging
import os
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wp_inbox_watcher as w


class FakeWordPress:
    def __init__(self):
        self.posts = {}
        self.uploads = []
        self.next_id = 200
        self.fail_once = False

    def post_for_day(self, when):
        self.posts.setdefault(when.date().isoformat(), {"id": len(self.posts) + 1, "content": ""})
        return self.posts[when.date().isoformat()]["id"]

    def upload(self, path, post_id, mime):
        self.uploads.append((path.name, post_id, mime))
        self.next_id += 1
        return self.next_id, f"https://example.test/uploads/{path.name}"

    def get_content(self, post_id):
        return next(v["content"] for v in self.posts.values() if v["id"] == post_id)

    def set_content(self, post_id, content):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated transient failure")
        next(v for v in self.posts.values() if v["id"] == post_id)["content"] = content


class WpiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "inbox"
        self.root.mkdir()
        w.verify_inbox(self.root)
        self.q = queue.Queue()
        self.logger = w.make_logger(self.root / "work", self.q)
        self.backend = FakeWordPress()
        self.processor = w.InboxProcessor(self.root, self.backend, self.logger)

    def test_title_match_and_escape(self):
        when = w.local_time(1792128000)
        correct = w.post_title(when)
        self.assertTrue(w.is_same_day_title(correct, when))
        self.assertFalse(w.is_same_day_title(correct.replace(str(when.day), str(when.day) + "9"), when))
        block = w.gutenberg_block("pdf", 31, "https://x.test/a?a=1&b=2", 'a"&<.pdf', "1234abcdef",
                                   when, "a.pdf")
        self.assertIn("<!-- wp:file", block)
        self.assertIn("&amp;", block)
        self.assertIn("displayPreview", block)
        self.assertIn("wpi-1234abcdef", block)

    def test_ignored_and_stable_change_detection(self):
        (self.root / "key.txt").write_text("x\ny\n")
        (self.root / "work" / "debug2.log").write_text("do not monitor")
        (self.root / "trash" / "archive.txt").write_text("do not monitor")
        (self.root / "a.txt").write_text("Hello")
        monitor = w.PollWatcher(self.root, self.processor, self.logger, quiet=0.01)
        monitor.scan()
        time.sleep(0.02)
        monitor.scan()
        self.assertEqual(self.processor.queue.get_nowait(), "new:a.txt")
        self.assertTrue(self.processor.queue.empty())
        # A later new item will be observed and queued after becoming stable.
        (self.root / "new.txt").write_text("file 1")
        monitor.scan()
        time.sleep(0.02)
        monitor.scan()
        self.assertEqual(self.processor.queue.get_nowait(), "new:new.txt")

    def test_file_move_post_and_trash(self):
        file = self.root / "test.png"
        file.write_bytes(b"fake png")
        w.InboxProcessor.accept(self.processor, file)
        self.assertFalse(file.exists())
        records = list((self.root / "work/jobs").glob("*.json"))
        self.assertEqual(len(records), 1)
        job = json.loads(records[0].read_text())
        self.assertEqual(job["status"], "done")
        self.assertTrue((self.root / "trash" / job["id"] / job["payload"]).exists())
        self.assertEqual(len(self.backend.uploads), 1)
        self.assertEqual(self.backend.uploads[0][0], "test.png")
        self.assertIn("wp:image", next(iter(self.backend.posts.values()))["content"])
        self.assertTrue((self.root / "work/debug.log").is_file())

    def test_folder_files_ordered_and_categorized(self):
        folder = self.root / "Notes"
        folder.mkdir()
        (folder / "sub").mkdir()
        (folder / "first.pdf").write_bytes(b"%PDF")
        (folder / "sub" / "second.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
        self.processor.accept(folder)
        self.assertEqual(len(self.backend.uploads), 2)
        content = "\n".join(post["content"] for post in self.backend.posts.values())
        self.assertIn("Notes/first.pdf", content)
        self.assertIn("Notes/sub/second.ics", content)
        self.assertIn("wp:file", content)
        self.assertFalse(folder.exists())
        self.assertEqual(len(list((self.root / "trash").iterdir())), 1)

    def test_resume_after_content_update_error_without_duplicate_upload(self):
        file = self.root / "file.txt"
        file.write_text("abc")
        self.backend.fail_once = True
        with self.assertRaises(RuntimeError):
            self.processor.accept(file)
        receipt = next((self.root / "work/jobs").glob("*.json"))
        job = json.loads(receipt.read_text())
        self.assertEqual(len(job["uploaded"]), 1)
        self.assertEqual(len(job["done"]), 0)
        self.assertTrue((self.root / "work/inflight" / job["id"] / job["payload"]).exists())
        self.processor.process(job["id"])
        self.assertEqual(len(self.backend.uploads), 1)
        self.assertEqual(len(next(iter(self.backend.posts.values()))["content"].split("wpi-")) > 1, True)
        self.assertEqual(json.loads(receipt.read_text())["status"], "done")

    def test_readback_detects_duplicate_marker(self):
        file = self.root / "again.mp3"
        file.write_bytes(b"a")
        self.processor.accept(file)
        receipt = next((self.root / "work/jobs").glob("*.json"))
        job = json.loads(receipt.read_text())
        self.assertEqual(len(self.backend.uploads), 1)
        self.processor.process(job["id"])
        self.assertEqual(len(self.backend.uploads), 1)

    def test_wp_cli_post_update_uses_file_not_argv(self):
        class CapturingBackend(w.WpCliBackend):
            def __init__(self):
                self.log = logging.getLogger("test-cli")
                self.calls = []

            def call(self, *args):
                self.calls.append(args)
                self.assert_file = Path(args[3]).read_text("utf-8")
                self.php = Path(args[1]).read_text("utf-8")
                return "123"

        backend = CapturingBackend()
        big = "ABCDE" * 300000
        backend.set_content(123, big)
        self.assertEqual(backend.assert_file, big)
        self.assertEqual(backend.calls[0][0], "eval-file")
        self.assertNotIn(big[:300], " ".join(backend.calls[0]))
        self.assertIn("wp_update_post", backend.php)

    def test_restore_crash_after_archive_before_manifest_done(self):
        file = self.root / "short.txt"
        file.write_text("data")
        self.processor.accept(file)
        receipt = next((self.root / "work/jobs").glob("*.json"))
        job = json.loads(receipt.read_text("utf-8"))
        job["status"] = "processing"
        w.write_json(receipt, job)
        self.processor.process(job["id"])
        self.assertEqual(json.loads(receipt.read_text())["status"], "done")
        self.assertEqual(len(self.backend.uploads), 1)

    def test_key_permissions_rest_validation(self):
        log = self.logger
        with self.assertRaises(ValueError):
            w.RestBackend("http://public.example", "u", "p", log)
        backend = w.RestBackend("https://example.test", "u", "p", log)
        self.assertEqual(backend.base, "https://example.test/wp-json/wp/v2")
        with patch.object(w, "find_wp_executables", return_value=[]), patch.object(w, "ask_text", side_effect=["admin", "app pass"]), patch.object(w.RestBackend, "validate"):
            args = w.build_parser().parse_args([str(self.root), "--rest-url", "https://example.test"])
            w.configured_backend(args, self.root, None, log)
        key = self.root / "key.txt"
        self.assertEqual(key.read_text(), "admin\napp pass\n")
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
