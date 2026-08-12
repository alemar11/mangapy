from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET = Path(__file__).resolve().parent / "resolve_release_version.py"
RELEASE_VERSION_WORKFLOW = PROJECT_ROOT / "workflows" / "release-version.yml"
RELEASE_WORKFLOW = PROJECT_ROOT / "workflows" / "release.yml"


def load_resolver() -> ModuleType:
    module_name = "g_versioning_release_resolver_asset"
    spec = importlib.util.spec_from_file_location(module_name, ASSET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {ASSET}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseResolverAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver = load_resolver()

    def resolve(
        self,
        *,
        operation: str,
        tags: list[str],
        ref_name: str = "main",
        confirmed_tag: str | None = None,
    ) -> dict[str, object]:
        return self.resolver.resolve(
            ref_name=ref_name,
            default_branch="main",
            operation=operation,
            raw_tags=tags,
            confirmed_tag=confirmed_tag,
        )

    def test_asset_reports_clean_semver_version(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ASSET), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(self.resolver.RESOLVER_VERSION, "0.2.1")
        self.assertEqual(completed.stdout.strip(), "0.2.1")
        self.assertEqual(completed.stderr, "")

    def test_final_tag_classification_requires_canonical_stable_form(self) -> None:
        self.assertTrue(self.resolver.is_final_tag("v1.2.3"))
        self.assertFalse(self.resolver.is_final_tag("v1.2.3-rc.1"))
        self.assertFalse(self.resolver.is_final_tag("1.2.3"))
        self.assertFalse(self.resolver.is_final_tag("v1.2.3-beta"))

    def test_asset_help_is_available_without_workflow_arguments(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ASSET), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--version", completed.stdout)
        self.assertIn("--confirmed-tag", completed.stdout)

    def test_default_branch_uses_highest_stable_baseline(self) -> None:
        result = self.resolve(
            operation="patch",
            tags=["v1.0.0", "v2.0.0-rc.1", "v3.0.0-rc.2"],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["tag"], "v1.0.1-rc.1")
        self.assertFalse(result["is_final"])

    def test_same_line_must_continue_from_release_branch(self) -> None:
        result = self.resolve(
            operation="patch",
            tags=["v1.0.0", "v1.0.1-rc.1"],
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "blocked-release-in-progress")
        self.assertEqual(result["release_branch"], "release/v1.0.1")

    def test_final_does_not_require_a_candidate(self) -> None:
        result = self.resolve(
            operation="final",
            tags=["v1.0.0"],
            ref_name="release/v2.0.0",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["tag"], "v2.0.0")
        self.assertTrue(result["is_final"])

    def test_noncanonical_confirmation_is_never_normalized(self) -> None:
        for confirmed_tag in (
            "1.0.1-rc.1",
            "v1.0.1-beta",
            "v1.0.1-rc01",
            "v1.0.1-rc.01",
            "v1.0.1+build.1",
        ):
            with self.subTest(confirmed_tag=confirmed_tag):
                result = self.resolve(
                    operation="patch",
                    tags=["v1.0.0"],
                    confirmed_tag=confirmed_tag,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "blocked-noncanonical")

    def test_existing_final_can_only_reconcile_its_pr(self) -> None:
        result = self.resolve(
            operation="final",
            tags=["v1.0.0", "v2.0.0"],
            ref_name="release/v2.0.0",
            confirmed_tag="v2.0.0",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "reconcile-existing-final")
        self.assertEqual(result["tag_state"], "existing-final")
        self.assertTrue(result["is_final"])

    def test_publish_gate_accepts_final_and_rejects_rc(self) -> None:
        final = self.resolve(
            operation="final",
            tags=["v4.0.1", "v4.0.2"],
            ref_name="release/v4.0.2",
            confirmed_tag="v4.0.2",
        )
        rc = self.resolve(
            operation="final",
            tags=["v4.0.1", "v4.0.2-rc.1"],
            ref_name="release/v4.0.2-rc.1",
            confirmed_tag="v4.0.2-rc.1",
        )
        self.assertTrue(final["application_ready"])
        self.assertTrue(final["is_final"])
        self.assertFalse(rc["application_ready"])
        self.assertFalse(rc["is_final"])

    def test_direct_publish_dispatch_requires_an_existing_final_tag(self) -> None:
        release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        release_version = RELEASE_VERSION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_call:", release)
        self.assertIn("workflow_dispatch:", release)
        self.assertNotIn("push:\n    tags:", release)
        self.assertIn("description: Exact existing final tag to recover", release)
        self.assertIn("EXPECTED_SOURCE_SHA: ${{ inputs.source_sha }}", release)
        self.assertIn("CONFIRMED_TAG: ${{ steps.tag.outputs.tag }}", release)
        self.assertIn('--confirmed-tag "$CONFIRMED_TAG"', release)
        self.assertIn("ref: ${{ needs.resolve.outputs.tag }}", release)
        self.assertIn("needs.resolve.outputs.tag_state == 'existing-final'", release)
        self.assertIn("uses: ./.github/workflows/release.yml", release_version)
        self.assertIn("tag: ${{ needs.resolve.outputs.tag }}", release_version)
        self.assertIn("source_sha: ${{ needs.final.outputs.source_sha }}", release_version)
        self.assertNotIn("gh workflow run release.yml", release_version)

    def test_single_release_version_ui_contains_all_operation_choices(self) -> None:
        workflow = RELEASE_VERSION_WORKFLOW.read_text(encoding="utf-8")
        dispatch = workflow.split("\npermissions: {}", 1)[0]
        for option in (
            '"[patch] Default branch → vX.Y.(Z+1)-rc.1"',
            '"[minor] Default branch → vX.(Y+1).0-rc.1"',
            '"[major] Default branch → v(X+1).0.0-rc.1"',
            '"[candidate] release/vX.Y.Z → vX.Y.Z-rc.N"',
            '"[final] release/vX.Y.Z → vX.Y.Z"',
        ):
            self.assertIn(option, dispatch)
        self.assertNotIn("confirmed_tag", dispatch)

    def test_obsolete_release_version_workflows_are_removed(self) -> None:
        workflows = RELEASE_VERSION_WORKFLOW.parent
        self.assertFalse((workflows / "release-version-dry-run.yml").exists())
        self.assertFalse((workflows / "release-version-apply.yml").exists())
        self.assertFalse((workflows / "release-version-approval-test.yml").exists())

    def test_approval_gates_revalidation_and_mutation(self) -> None:
        workflow = RELEASE_VERSION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Approve proposed tag ${{ needs.plan.outputs.tag }}", workflow)
        self.assertIn("needs.plan.outputs.status == 'proposal-ready'", workflow)
        self.assertIn("name: release-approval", workflow)
        self.assertIn("deployment: false", workflow)
        self.assertIn("needs: [plan, approval]", workflow)
        self.assertIn("CONFIRMED_TAG: ${{ needs.plan.outputs.tag }}", workflow)
        self.assertIn("--application-mode", workflow)
        self.assertIn("Remote state will be revalidated before any tag", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("--method POST", workflow)

    def test_asset_has_no_project_or_network_dependency(self) -> None:
        source = ASSET.read_text(encoding="utf-8")
        self.assertNotIn("package.json", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)

    def test_release_version_workflow_preserves_resolver_and_safety_contract(self) -> None:
        workflow = RELEASE_VERSION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Release version", workflow)
        self.assertIn("resolver API 0.2.1", workflow)
        self.assertIn(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            workflow,
        )
        self.assertIn('EXPECTED_RESOLVER_VERSION: "0.2.1"', workflow)
        self.assertIn("is_final: ${{ steps.resolve.outputs.is_final }}", workflow)
        self.assertIn("needs.resolve.outputs.is_final == 'true'", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertIn("No application source or package metadata", workflow)

    def test_plan_summary_points_to_the_approval_gate(self) -> None:
        source = ASSET.read_text(encoding="utf-8")
        self.assertIn("approve it through the protected environment", source)
        self.assertNotIn("Release version (apply)", source)


if __name__ == "__main__":
    unittest.main()
