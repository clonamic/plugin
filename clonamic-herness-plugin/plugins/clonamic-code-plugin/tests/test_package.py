import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
EXPECTED_SKILLS = {
    "clonamic-code-router",
    "clonamic-modular-design",
    "clonamic-supercoder",
    "clonamic-ultracode",
}


def evaluate_route(contract, context):
    stages = []
    if any(context.get(key, False) for key in contract["modular_design"]["any"]):
        stages.append("modular-design")
    if all(context.get(key, False) for key in contract["supercoder"]["all"]):
        stages.append("supercoder")

    ultra_gates_pass = all(context.get(key, False) for key in contract["ultracode"]["all"])
    if ultra_gates_pass:
        if context.get(contract["ultracode"]["capability"], False):
            stages.append("ultracode")
            ultra_status = "active"
        else:
            ultra_status = contract["ultracode"]["capability_failure"]
    else:
        ultra_status = "not_eligible"

    return {
        "stages": stages or [contract["default"]],
        "ultracode": ultra_status,
    }


class DevelopmentPackageTest(unittest.TestCase):
    def test_root_manifest_is_minimal_mit_package(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(
            "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            manifest["$schema"],
        )
        self.assertEqual(
            {"$schema", "name", "version", "description", "license", "author", "keywords"},
            set(manifest),
        )
        self.assertEqual("clonamic-code-plugin", manifest["name"])
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual("MIT", manifest["license"])
        self.assertEqual({"name": "Clonamic"}, manifest["author"])
        self.assertFalse((ROOT / "mcp.json").exists())
        self.assertFalse((ROOT / ".mcp.json").exists())
        self.assertFalse((ROOT / "bin").exists())
        self.assertFalse((ROOT / "commands").exists())

    def test_exactly_four_direct_skills_are_complete(self):
        actual = {path.parent.name for path in SKILLS.glob("*/SKILL.md")}
        self.assertEqual(EXPECTED_SKILLS, actual)
        self.assertEqual(4, len(list(SKILLS.rglob("SKILL.md"))))
        for name in EXPECTED_SKILLS:
            folder = SKILLS / name
            text = (folder / "SKILL.md").read_text(encoding="utf-8")
            self.assertRegex(text, rf"(?m)^name: {re.escape(name)}$")
            self.assertRegex(text, r"(?m)^description: .+$")
            self.assertTrue((folder / "agents" / "openai.yaml").is_file())
            self.assertNotIn("TODO", text)

    def test_package_has_no_external_runtime_or_forbidden_branding(self):
        forbidden = (
            "super" + "powers",
            "clu" + "xion",
            "cl" + "x-",
            "cod" + "ex exec",
            "clau" + "de",
            "gr" + "ok",
            "her" + "mes",
            "mcp" + "Servers",
        )
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or "tests" in path.parts
                or path.name == "THIRD_PARTY_NOTICES.md"
            ):
                continue
            text = path.read_text(encoding="utf-8").casefold()
            for token in forbidden:
                self.assertNotIn(token.casefold(), text, f"{token} in {path.relative_to(ROOT)}")

    def test_ownership_contract_excludes_core_responsibilities(self):
        contract = json.loads(
            (SKILLS / "clonamic-code-router" / "references" / "ownership-contract.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {
                "authorization",
                "completion_verdict",
                "user_report",
                "external_executor_selection",
                "installation",
            },
            set(contract["does_not_own"]),
        )
        self.assertEqual(["approved_scope"], contract["consumes"])

    def test_routing_matrix_matches_activation_contract(self):
        contract = json.loads(
            (SKILLS / "clonamic-code-router" / "references" / "activation-contract.json").read_text(
                encoding="utf-8"
            )
        )
        cases = json.loads((ROOT / "tests" / "fixtures" / "routing-cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertEqual(case["expected"], evaluate_route(contract, case["input"]))

    def test_failure_semantics_are_declared_once_per_specialist(self):
        expected = {
            "clonamic-modular-design": {"blocked_missing_evidence", "invalid_contract"},
            "clonamic-supercoder": {
                "capability_missing",
                "stale_file",
                "ambiguous_match",
                "syntax_rejected",
                "verification_failed",
            },
            "clonamic-ultracode": {"no_consensus", "aborted", "unavailable"},
        }
        for skill, statuses in expected.items():
            contract_path = next((SKILLS / skill / "references").glob("*.json"))
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(statuses, set(contract["failure_statuses"]), skill)


if __name__ == "__main__":
    unittest.main()
