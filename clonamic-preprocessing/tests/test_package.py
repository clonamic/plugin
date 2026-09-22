import importlib.util
import json
import multiprocessing
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MANIFEST_FIELDS = {"$schema", "name", "version", "description", "license", "author", "keywords"}


def load_runtime(root):
    path = Path(root) / "skills" / "clonamic-preprocessing" / "scripts" / "preprocessing.py"
    if not path.is_file():
        raise AssertionError("skill-relative preprocessing runtime is missing")
    spec = importlib.util.spec_from_file_location(f"clonamic_preprocessing_{os.getpid()}_{id(path)}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def claim_worker(root, queue_path, worker_id, start, output):
    runtime = load_runtime(root)
    start.wait(5)
    try:
        output.put(runtime.claim_next(queue_path, worker_id=worker_id))
    except Exception as exc:
        output.put({"error": type(exc).__name__, "message": str(exc)})


class PreprocessingPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "package"
        shutil.copytree(ROOT, self.root)
        self.runtime = load_runtime(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def queue_path(self):
        return self.root / "state" / "queue.json"

    def test_closed_manifest_and_two_bounded_skills(self):
        manifest = json.loads((self.root / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(SCHEMA, manifest["$schema"])
        self.assertEqual(MANIFEST_FIELDS, set(manifest))
        self.assertEqual("clonamic-preprocessing", manifest["name"])
        self.assertEqual("MIT", manifest["license"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        skills = list((self.root / "skills").glob("*/SKILL.md"))
        self.assertEqual(
            ["clonamic-grill-me", "clonamic-preprocessing"],
            [path.parent.name for path in skills],
        )
        self.assertTrue(
            (self.root / "skills/clonamic-preprocessing/agents/openai.yaml").is_file()
        )
        self.assertFalse((self.root / "scripts").exists())

    def test_normalization_is_stable_and_preserves_paragraphs(self):
        self.assertEqual(
            "Hello world\n\nnext line",
            self.runtime.normalize_text("  Hello   world \r\n\r\n  next\tline  "),
        )
        self.assertEqual("ABC", self.runtime.normalize_text("ＡＢＣ"))

    def test_queue_preserves_original_payload_and_keeps_a_normalized_view(self):
        queue = self.queue_path()
        original = '```python\nif ready:\n    print("a  b")\n```\n\uff21ＢＣ'
        item = self.runtime.enqueue(queue, original, item_id="code")
        self.assertEqual(original, item["text"])
        self.assertEqual(
            '```python\nif ready:\nprint("a b")\n```\nABC',
            item["normalized_text"],
        )
        claimed = self.runtime.claim_next(queue, worker_id="worker")
        self.assertEqual(original, claimed["text"])
        self.assertEqual(item["normalized_text"], claimed["normalized_text"])

    def test_normalization_result_never_replaces_literal_execution_text(self):
        queue = self.queue_path()
        original = 'target:\n\t@printf "x  y\\n"\npath: "C:\\\\Temp"'
        result = self.runtime.clarification_contract(original, [])
        self.assertEqual(original, result["original_text"])
        self.assertNotEqual(original, result["normalized_text"])
        self.runtime.enqueue(queue, original, item_id="literal")
        self.assertEqual(
            original,
            self.runtime.claim_next(queue, worker_id="worker")["text"],
        )

    def test_legacy_queue_item_gains_comparison_text_without_rewriting_payload(self):
        queue = self.queue_path()
        original = 'if ready:\n    print("a  b")'
        queue.parent.mkdir(parents=True, exist_ok=True)
        queue.write_text(
            json.dumps(
                {
                    "version": 1,
                    "next_sequence": 1,
                    "items": [
                        {
                            "id": "legacy",
                            "text": original,
                            "priority": 10,
                            "sequence": 0,
                            "state": "pending",
                            "attempts": 0,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        claimed = self.runtime.claim_next(queue, worker_id="worker")
        self.assertEqual(original, claimed["text"])
        self.assertEqual(self.runtime.normalize_text(original), claimed["normalized_text"])
        self.runtime.record(queue, "legacy", claimed["claim_id"], "done", {"ok": True})
        stored = self.runtime.queue_state(queue)["items"][0]
        self.assertEqual(original, stored["text"])
        self.assertEqual("done", stored["state"])

    def test_clarification_uses_only_caller_supplied_missing_fields(self):
        ready = self.runtime.clarification_contract("Ship the release", [])
        self.assertFalse(ready["required"])
        self.assertTrue(ready["ready_for_queue"])
        blocked = self.runtime.clarification_contract("Ship it", ["target", "output"])
        self.assertTrue(blocked["required"])
        self.assertEqual(["target", "output"], [row["field"] for row in blocked["questions"]])

    def test_claim_is_priority_fifo_and_record_requires_claim_token(self):
        queue = self.queue_path()
        self.runtime.enqueue(queue, "later", priority=20, item_id="later")
        self.runtime.enqueue(queue, "first", priority=10, item_id="first")
        self.runtime.enqueue(queue, "same priority", priority=10, item_id="same")
        first = self.runtime.claim_next(queue, worker_id="worker-a")
        self.assertEqual("first", first["id"])
        with self.assertRaises(ValueError):
            self.runtime.record(queue, "first", "wrong-token", "done", {})
        self.runtime.record(queue, "first", first["claim_id"], "done", {"value": 1})
        self.assertEqual("same", self.runtime.claim_next(queue, worker_id="worker-a")["id"])

    def test_loop_auto_requires_explicit_enablement(self):
        calls = []
        queue = self.queue_path()
        self.runtime.enqueue(queue, "one", item_id="one")
        result = self.runtime.run_loop_auto(queue, lambda item: calls.append(item["id"]), enabled=False)
        self.assertEqual("disabled", result["status"])
        self.assertEqual([], calls)
        self.assertEqual("one", self.runtime.claim_next(queue, worker_id="caller")["id"])

    def test_loop_auto_drains_bounded_queue_with_caller_executor(self):
        queue = self.queue_path()
        self.runtime.enqueue(queue, "one", item_id="one")
        self.runtime.enqueue(queue, "two", item_id="two")
        result = self.runtime.run_loop_auto(
            queue,
            lambda item: {"handled": item["id"]},
            enabled=True,
            max_steps=4,
            worker_id="loop",
        )
        self.assertEqual("drained", result["status"])
        self.assertEqual(["one", "two"], result["processed"])
        self.assertIsNone(self.runtime.claim_next(queue, worker_id="caller"))

    def test_atomic_claim_has_no_cross_process_duplicates(self):
        queue = self.queue_path()
        for index in range(8):
            self.runtime.enqueue(queue, f"item {index}", item_id=f"item-{index}")
        context = multiprocessing.get_context("spawn")
        start = context.Event()
        output = context.Queue()
        processes = [
            context.Process(
                target=claim_worker,
                args=(str(self.root), str(queue), f"worker-{index}", start, output),
            )
            for index in range(8)
        ]
        for process in processes:
            process.start()
        start.set()
        claims = [output.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(10)
            self.assertEqual(0, process.exitcode)
        self.assertTrue(all("error" not in claim for claim in claims))
        self.assertEqual(8, len({claim["id"] for claim in claims}))
        self.assertEqual(8, len({claim["claim_id"] for claim in claims}))

    def test_lock_wait_is_bounded(self):
        queue = self.queue_path()
        self.runtime.enqueue(queue, "one", item_id="one")
        lock_path = Path(f"{queue}.lock")
        lock_path.write_text("held", encoding="utf-8")
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            self.runtime.claim_next(
                queue,
                worker_id="blocked",
                lock_timeout=0.05,
                lock_stale_after=60,
            )
        self.assertLess(time.monotonic() - started, 0.5)

    def test_stale_active_item_is_reclaimed_without_old_claim_winning(self):
        queue = self.queue_path()
        self.runtime.enqueue(queue, "one", item_id="one")
        first = self.runtime.claim_next(queue, worker_id="crashed", active_stale_after=60)
        second = self.runtime.claim_next(queue, worker_id="recovery", active_stale_after=0)
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(first["claim_id"], second["claim_id"])
        self.assertEqual(2, second["attempts"])
        with self.assertRaises(ValueError):
            self.runtime.record(queue, "one", first["claim_id"], "done", {})
        self.runtime.record(queue, "one", second["claim_id"], "done", {"recovered": True})
        item = self.runtime.queue_state(queue)["items"][0]
        self.assertEqual("done", item["state"])
        self.assertEqual({"recovered": True}, item["result"])

    def test_production_surface_excludes_removed_responsibilities(self):
        forbidden = (
            "brow" + "ser",
            "mo" + "del",
            "con" + "fig",
            "gu" + "ard",
            "com" + "press",
            "app" + "roval",
            "comp" + "letion",
            "rep" + "ort",
            "led" + "ger",
        )
        for path in self.root.rglob("*"):
            if not path.is_file() or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8").casefold()
            for token in forbidden:
                self.assertNotIn(token, text, f"{token} in {path.relative_to(self.root)}")


if __name__ == "__main__":
    unittest.main()
