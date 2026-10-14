import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.bundle import BundleIntegrityError, freeze_bundle, load_bundle
from execcon_v2.inputs import (
    ForbiddenEvaluationField,
    assert_treatment_purity,
    build_convergence_input,
)
from execcon_v2.mcp import McpToolError, call_text, command_stdout, decode_read_bytes
from execcon_v2.paths import PathBoundaryError, safe_candidate_path
from execcon_v2.platform_probe import collect_platform_snapshot
from execcon_v2.safe_json import SensitiveDataError, write_public_json
from execcon_v2.settings import SettingsError, load_settings


class ProtocolInvariantTests(unittest.TestCase):
    def complete_identity(self):
        return {
            "task_id": "task-a",
            "cohort": 1,
            "harness": 2,
            "resource_mode": "accumulative",
            "model": "gpt-5.6-luna",
            "model_settings_sha256": "a" * 64,
            "spec_sha256": "b" * 64,
            "pool_sha256": "c" * 64,
            "prompt_sha256": "d" * 64,
            "tool_schema_sha256": "e" * 64,
            "code_sha256": "f" * 64,
            "output_protocol_sha256": "1" * 64,
            "producer_id": "cand-0:numerics_stats",
            "session_id_hash": "2" * 64,
        }

    def candidate(self):
        return {
            "candidate_id": "cand-0",
            "specialist": "numerics_stats",
            "claim": "The computed value is 12.0.",
            "evidence": {
                "calls": [{"tool": "run_command", "exit_code": 0, "result": "ok"}],
                "artifacts": [{"path": "results.json", "sha256": "a" * 64}],
                "snapshot_id": "session-a",
            },
        }

    def test_hidden_grade_fields_are_rejected_from_convergence_input(self):
        candidate = self.candidate()
        candidate["evidence"]["pass_rate"] = 1.0

        with self.assertRaises(ForbiddenEvaluationField):
            build_convergence_input("spec", [candidate], evidence_visible=True)

    def test_masking_changes_only_admitted_evidence_values(self):
        candidate = self.candidate()
        masked = build_convergence_input("spec", [candidate], evidence_visible=False)
        visible = build_convergence_input("spec", [candidate], evidence_visible=True)

        assert_treatment_purity(masked, visible)
        self.assertEqual(masked["candidates"][0]["claim"], visible["candidates"][0]["claim"])
        self.assertEqual(masked["candidates"][0]["evidence"]["calls"], "MASKED")
        self.assertEqual(visible["candidates"][0]["evidence"]["calls"][0]["exit_code"], 0)

    def test_non_evidence_difference_fails_treatment_purity(self):
        candidate = self.candidate()
        masked = build_convergence_input("spec", [candidate], evidence_visible=False)
        visible = build_convergence_input("spec", [candidate], evidence_visible=True)
        visible["candidates"][0]["claim"] = "changed"

        with self.assertRaises(AssertionError):
            assert_treatment_purity(masked, visible)

    def test_bundle_is_content_addressed_and_detects_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "results.json").write_text('{"value": 12}', encoding="utf-8")
            bundle_dir = freeze_bundle(root / "bundles", self.complete_identity(), source)
            loaded = load_bundle(bundle_dir)
            self.assertEqual(loaded["bundle_hash"], bundle_dir.name)

            (bundle_dir / "files" / "results.json").write_text("mutated", encoding="utf-8")
            with self.assertRaises(BundleIntegrityError):
                load_bundle(bundle_dir)

    def test_bundle_requires_complete_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "results.json").write_text("{}", encoding="utf-8")

            with self.assertRaises(BundleIntegrityError):
                freeze_bundle(root / "bundles", {"task_id": "task-a"}, source)

    def test_bundle_rejects_credentials_anywhere_in_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "results.json").write_text("{}", encoding="utf-8")
            metadata = self.complete_identity()
            metadata["request"] = {"headers": {"Authorization": "Bearer secret"}}

            with self.assertRaises(BundleIntegrityError):
                freeze_bundle(root / "bundles", metadata, source)

    def test_unknown_evidence_fields_are_rejected(self):
        candidate = self.candidate()
        candidate["evidence"]["tool_returns"] = ["secret evidence"]
        with self.assertRaises(ValueError):
            build_convergence_input("spec", [candidate], evidence_visible=False)

    def test_bundle_identity_rejects_empty_values_and_invalid_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            (source / "results.json").write_text("{}", encoding="utf-8")
            metadata = self.complete_identity()
            metadata["resource_mode"] = ""
            with self.assertRaises(BundleIntegrityError):
                freeze_bundle(root / "bundles", metadata, source)
            metadata = self.complete_identity()
            metadata["spec_sha256"] = "not-a-hash"
            with self.assertRaises(BundleIntegrityError):
                freeze_bundle(root / "bundles", metadata, source)

    @unittest.skipIf(os.name == "nt", "Windows symlink creation may require elevated privileges")
    def test_bundle_rejects_symbolic_links(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            source.mkdir()
            outside = root / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            (source / "leak.txt").symlink_to(outside)
            with self.assertRaises(BundleIntegrityError):
                freeze_bundle(root / "bundles", self.complete_identity(), source)

    def test_read_bytes_decoder_preserves_exact_bytes(self):
        payload = {"result": {"content": [{"type": "text", "text": '{"content_b64":"YWJjXG4="}'}]}}
        self.assertEqual(decode_read_bytes(payload), b"abc\\n")

    def test_mcp_errors_and_missing_exit_codes_are_rejected(self):
        class FakeMcp:
            def __init__(self, response):
                self.response = response

            def call_tool(self, name, arguments):
                return self.response

        with self.assertRaises(McpToolError):
            call_text(FakeMcp({"error": {"message": "boom"}}), "x", {})
        response = {"result": {"content": [{"type": "text", "text": '{"stdout":"ok"}'}]}}
        with self.assertRaises(McpToolError):
            command_stdout(FakeMcp(response), "pwd")

    def test_candidate_path_cannot_escape_private_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            self.assertEqual(safe_candidate_path(root, "output/results.json"), root / "output/results.json")
            with self.assertRaises(PathBoundaryError):
                safe_candidate_path(root, "../other/results.json")
            with self.assertRaises(PathBoundaryError):
                safe_candidate_path(root, str(root.parent / "secret.txt"))

    def test_platform_snapshot_preserves_service_task_ids_and_stage_errors(self):
        class FakeClient:
            def health(self):
                return {"ok": True, "capabilities": {"cohort_harness_selection": 1}}

            def benchmarks(self):
                return {"revision": "test"}

            def task_ids(self, dataset, benchmark, version, split="test"):
                if version == "full":
                    return [f"task-{i}" for i in range(68)]
                return [f"stage-{version}-task"]

            def resources(self, dataset, benchmark, version, **kwargs):
                at_stage = kwargs.get("at_stage")
                if at_stage == 4:
                    raise RuntimeError("missing agents bundle")
                count = {1: 2, 2: 5, 3: 8, 5: 16, 6: 24}.get(at_stage, 24)
                return {"mode": "accumulative", "count": count, "names": [f"agent-{i}" for i in range(count)]}

        snapshot = collect_platform_snapshot(FakeClient(), "evovling_agents", "ale", stages=[1, 2, 3, 4, 5, 6])
        self.assertEqual(snapshot["task_sets"]["full"]["count"], 68)
        self.assertEqual(len(snapshot["task_sets"]["full"]["task_ids"]), 68)
        self.assertEqual(snapshot["resources"]["h3"]["count"], 8)
        self.assertEqual(snapshot["resources"]["h4"]["status"], "error")
        self.assertIn("missing agents bundle", snapshot["resources"]["h4"]["error"])

    def test_public_json_rejects_sensitive_keys(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "snapshot.json"
            with self.assertRaises(SensitiveDataError):
                write_public_json(output, {"headers": {"Authorization": "Bearer secret"}})
            self.assertFalse(output.exists())

    def test_public_json_allows_boolean_capability_flags_and_token_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "snapshot.json"
            write_public_json(output, {"requires_api_key": True, "token_count": 123})
            self.assertTrue(output.exists())

    def test_public_json_rejects_credentials_hidden_in_values(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "snapshot.json"
            with self.assertRaises(SensitiveDataError):
                write_public_json(output, {"error": "request used Bearer abcdefghijklmnop"})
            self.assertFalse(output.exists())

    def test_no_model_settings_require_only_evaluation_credential(self):
        old = dict(os.environ)
        try:
            os.environ.pop("DMXAPI_API_KEY", None)
            os.environ["EVAL_SERVICE_API_KEY"] = "eval-only"
            settings = load_settings(require_model_key=False)
            self.assertEqual(settings.eval_service_api_key, "eval-only")
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_settings_require_environment_credentials(self):
        old = dict(os.environ)
        try:
            os.environ.pop("DMXAPI_API_KEY", None)
            os.environ.pop("EVAL_SERVICE_API_KEY", None)
            with self.assertRaises(SettingsError):
                load_settings()
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_settings_repr_and_manifest_do_not_expose_credentials(self):
        old = dict(os.environ)
        try:
            os.environ["DMXAPI_API_KEY"] = "secret-dmx"
            os.environ["EVAL_SERVICE_API_KEY"] = "secret-eval"
            settings = load_settings()
            text = repr(settings) + json.dumps(settings.public_manifest())
            self.assertNotIn("secret-dmx", text)
            self.assertNotIn("secret-eval", text)
            self.assertEqual(settings.model, "gpt-5.6-luna")
        finally:
            os.environ.clear()
            os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
