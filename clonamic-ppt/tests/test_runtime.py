import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "skills/clonamic-ppt/scripts/doctor.py"


def load_doctor():
    spec = importlib.util.spec_from_file_location("clonamic_ppt_doctor", DOCTOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RuntimeReadinessTest(unittest.TestCase):
    def test_missing_runtime_is_reported_without_installing(self):
        doctor = load_doctor()
        with tempfile.TemporaryDirectory() as temporary:
            result = doctor.check_runtime(Path(temporary))
        self.assertFalse(result["ready"])
        self.assertFalse(result["checks"]["pptxgenjs"])
        self.assertIn("npm ci", result["recovery"])

    def test_repository_runtime_is_ready_after_declared_setup(self):
        result = load_doctor().check_runtime(ROOT)
        self.assertTrue(result["ready"], result)


if __name__ == "__main__":
    unittest.main()
