from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET = Path(__file__).resolve().parent / "resolve_release_version.py"
DRY_RUN_WORKFLOW = PROJECT_ROOT / "workflows" / "release-version-dry-run.yml"
APPLY_WORKFLOW = PROJECT_ROOT / "workflows" / "release-version-apply.yml"
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
        self.assertEqual(self.resolver.RESOLVER_VERSION, "0.2.0")
        self.assertEqual(completed.stdout.strip(), "0.2.0")
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
        apply = APPLY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", release)
        self.assertIn("description: Exact existing final tag to publish", release)
        self.assertIn("confirmed_tag: ${{ inputs.tag || github.ref_name }}", release)
        self.assertIn("ref: ${{ needs.resolve.outputs.tag }}", release)
        self.assertIn("needs.resolve.outputs.tag_state == 'existing-final'", release)
        self.assertIn("gh workflow run release.yml", apply)
        self.assertIn('--repo "$GITHUB_REPOSITORY"', apply)
        self.assertIn('--field tag="$TAG"', apply)

    def test_asset_has_no_project_or_network_dependency(self) -> None:
        source = ASSET.read_text(encoding="utf-8")
        self.assertNotIn("package.json", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)

    def test_reference_embeds_both_complete_workflow_templates(self) -> None:
        dry_run = DRY_RUN_WORKFLOW.read_text(encoding="utf-8")
        apply = APPLY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Release version (dry run)", dry_run)
        self.assertIn("name: Release version (apply)", apply)
        self.assertIn("resolver API 0.2.0", dry_run)
        self.assertIn(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            dry_run,
        )
        self.assertIn('EXPECTED_RESOLVER_VERSION: "0.2.0"', dry_run)
        self.assertIn("is_final: ${{ steps.resolve.outputs.is_final }}", dry_run)
        self.assertIn("needs.resolve.outputs.is_final == 'true'", apply)
        self.assertIn("pull-requests: write", apply)
        self.assertIn("No application source or package metadata", apply)


if __name__ == "__main__":
    unittest.main()
