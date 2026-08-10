#!/usr/bin/env python3
"""Resolve guarded release-version proposals without mutating repository state."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


RESOLVER_VERSION = "0.2.0"
TAG_PATTERN = re.compile(
    r"^(?P<prefix>v?)(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-rc\.(?P<rc>[1-9][0-9]*))?$"
)
CANONICAL_TAG_PATTERN = re.compile(
    r"^v(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-rc\.(?P<rc>[1-9][0-9]*))?$"
)
RELEASE_BRANCH_PATTERN = re.compile(
    r"^release/v(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)$"
)
MANUAL_OPERATION_PATTERN = re.compile(
    r"^\[(patch|minor|major|candidate|final)\](?:\s|$)"
)
DEFAULT_OPERATIONS = {"patch", "minor", "major"}
RELEASE_OPERATIONS = {"candidate", "final"}


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    rc: int | None = None

    @property
    def base(self) -> tuple[int, int, int]:
        return self.major, self.minor, self.patch

    @property
    def stable(self) -> bool:
        return self.rc is None

    @property
    def tag(self) -> str:
        base = f"v{self.major}.{self.minor}.{self.patch}"
        return base if self.stable else f"{base}-rc.{self.rc}"

    def precedence_key(self) -> tuple[int, int, int, int, int]:
        return (*self.base, 1 if self.stable else 0, self.rc or 0)


@dataclass(frozen=True)
class ParsedTag:
    raw: str
    version: Version
    canonical: bool


def parse_tag(raw: str) -> ParsedTag | None:
    value = raw.strip()
    match = TAG_PATTERN.fullmatch(value)
    if match is None:
        return None
    version = Version(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        rc=int(match.group("rc")) if match.group("rc") else None,
    )
    return ParsedTag(raw=value, version=version, canonical=value.startswith("v"))


def is_final_tag(raw: str) -> bool:
    parsed = parse_tag(raw)
    return parsed is not None and parsed.canonical and parsed.version.stable


def parse_tags(raw_tags: Iterable[str]) -> tuple[list[ParsedTag], int]:
    parsed: list[ParsedTag] = []
    ignored = 0
    for raw in raw_tags:
        tag = parse_tag(raw)
        if tag is None:
            ignored += 1
        else:
            parsed.append(tag)
    return parsed, ignored


def base_tag(base: tuple[int, int, int], rc: int | None = None) -> str:
    return Version(*base, rc=rc).tag


def tags_for_base(
    tags: Iterable[ParsedTag], base: tuple[int, int, int]
) -> list[ParsedTag]:
    return [tag for tag in tags if tag.version.base == base]


def final_for_base(
    tags: Iterable[ParsedTag], base: tuple[int, int, int]
) -> ParsedTag | None:
    finals = [tag for tag in tags_for_base(tags, base) if tag.version.stable]
    return max(finals, key=lambda tag: (tag.canonical, tag.raw), default=None)


def next_rc_for_base(tags: Iterable[ParsedTag], base: tuple[int, int, int]) -> int:
    numbers = [
        tag.version.rc
        for tag in tags_for_base(tags, base)
        if tag.version.rc is not None
    ]
    return max(numbers, default=0) + 1


def latest_tag(tags: Iterable[ParsedTag]) -> ParsedTag:
    return max(
        tags,
        key=lambda tag: (tag.version.precedence_key(), tag.canonical, tag.raw),
    )


def latest_stable_tag(tags: Iterable[ParsedTag]) -> ParsedTag | None:
    stable_tags = [tag for tag in tags if tag.version.stable]
    return max(
        stable_tags,
        key=lambda tag: (tag.version.precedence_key(), tag.canonical, tag.raw),
        default=None,
    )


def display(tag: ParsedTag) -> str:
    return tag.version.tag if tag.canonical else tag.raw


def normalize_operation(requested_operation: str) -> str:
    match = MANUAL_OPERATION_PATTERN.match(requested_operation.strip())
    return match.group(1) if match is not None else requested_operation.strip()


def infer_operation(
    *,
    ref_name: str,
    default_branch: str,
    raw_tags: Iterable[str],
    confirmed_tag: str,
) -> str:
    tags, _ = parse_tags(raw_tags)
    proposals: dict[str, str]

    if ref_name == default_branch:
        current = latest_stable_tag(tags)
        if current is None:
            return "auto"
        major, minor, patch = current.version.base
        bases = {
            "patch": (major, minor, patch + 1),
            "minor": (major, minor + 1, 0),
            "major": (major + 1, 0, 0),
        }
        proposals = {
            operation: base_tag(base, next_rc_for_base(tags, base))
            for operation, base in bases.items()
        }
    else:
        match = RELEASE_BRANCH_PATTERN.fullmatch(ref_name)
        if match is None:
            return "auto"
        base = (
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
        )
        proposals = {
            "candidate": base_tag(base, next_rc_for_base(tags, base)),
            "final": base_tag(base),
        }

    matches = [
        operation
        for operation, proposal in proposals.items()
        if proposal == confirmed_tag
    ]
    return matches[0] if len(matches) == 1 else "auto"


def blocked(
    *,
    status: str,
    reason: str,
    confirmed_tag: str | None,
    context: str = "",
    tag: str = "",
    kind: str = "",
    release_branch: str = "",
    latest: str = "",
    ignored: int = 0,
) -> dict[str, object]:
    return {
        "ok": False,
        "mode": "apply" if confirmed_tag is not None else "plan",
        "context": context,
        "tag": tag,
        "kind": kind,
        "release_branch": release_branch,
        "latest_tag": latest,
        "ignored_tag_count": ignored,
        "is_final": is_final_tag(tag),
        "status": status,
        "reason": reason,
        "tag_state": "unknown",
        "application_ready": False,
    }


def resolve(
    *,
    ref_name: str,
    default_branch: str,
    operation: str,
    raw_tags: Iterable[str],
    confirmed_tag: str | None,
) -> dict[str, object]:
    tags, ignored = parse_tags(raw_tags)
    latest = display(latest_tag(tags)) if tags else ""

    if (
        confirmed_tag is not None
        and CANONICAL_TAG_PATTERN.fullmatch(confirmed_tag) is None
    ):
        return blocked(
            status="blocked-noncanonical",
            reason="the exact tag must match vX.Y.Z or vX.Y.Z-rc.N",
            confirmed_tag=confirmed_tag,
            latest=latest,
            ignored=ignored,
        )

    if ref_name == default_branch:
        context = "default"
        stable_baseline = latest_stable_tag(tags)
        if operation == "auto":
            if stable_baseline is None:
                return blocked(
                    status="blocked-missing-baseline",
                    reason=(
                        "no stable SemVer baseline exists; initialize it explicitly "
                        "before using this Action"
                    ),
                    confirmed_tag=confirmed_tag,
                    context=context,
                    ignored=ignored,
                )
            return blocked(
                status="blocked-confirmation-mismatch",
                reason=(
                    "the confirmed tag does not match the current patch, minor, "
                    "or major proposal"
                ),
                confirmed_tag=confirmed_tag,
                context=context,
                latest=latest,
                ignored=ignored,
            )
        if operation not in DEFAULT_OPERATIONS:
            return blocked(
                status="blocked-context-operation",
                reason="the default branch accepts only patch, minor, or major",
                confirmed_tag=confirmed_tag,
                context=context,
                latest=latest,
                ignored=ignored,
            )
        if stable_baseline is None:
            return blocked(
                status="blocked-missing-baseline",
                reason=(
                    "no stable SemVer baseline exists; initialize it explicitly "
                    "before using this Action"
                ),
                confirmed_tag=confirmed_tag,
                context=context,
                ignored=ignored,
            )

        current = stable_baseline
        major, minor, patch = current.version.base
        bases = {
            "patch": (major, minor, patch + 1),
            "minor": (major, minor + 1, 0),
            "major": (major + 1, 0, 0),
        }
        base = bases[operation]
        branch = f"release/{base_tag(base)}"
        existing = tags_for_base(tags, base)
        final = final_for_base(tags, base)
        proposal = base_tag(base, next_rc_for_base(tags, base))

        if final is not None:
            return blocked(
                status="blocked-finalized",
                reason=f"{final.version.tag} already finalizes the proposed release line",
                confirmed_tag=confirmed_tag,
                context=context,
                kind="candidate",
                release_branch=branch,
                latest=latest,
                ignored=ignored,
            )
        if existing:
            return blocked(
                status="blocked-release-in-progress",
                reason=(
                    f"continue this release line from {branch}; do not create "
                    f"another candidate for it from {default_branch}"
                ),
                confirmed_tag=confirmed_tag,
                context=context,
                tag=proposal,
                kind="candidate",
                release_branch=branch,
                latest=latest,
                ignored=ignored,
            )
    else:
        match = RELEASE_BRANCH_PATTERN.fullmatch(ref_name)
        if match is None:
            return blocked(
                status="blocked-ref",
                reason=f"select {default_branch} or an exact release/vX.Y.Z branch",
                confirmed_tag=confirmed_tag,
                latest=latest,
                ignored=ignored,
            )
        context = "release"
        if operation == "auto":
            return blocked(
                status="blocked-confirmation-mismatch",
                reason=(
                    "the confirmed tag does not match the next candidate or final "
                    "proposal for this release branch"
                ),
                confirmed_tag=confirmed_tag,
                context=context,
                release_branch=ref_name,
                latest=latest,
                ignored=ignored,
            )
        if operation not in RELEASE_OPERATIONS:
            return blocked(
                status="blocked-context-operation",
                reason="a release branch accepts only candidate or final",
                confirmed_tag=confirmed_tag,
                context=context,
                release_branch=ref_name,
                latest=latest,
                ignored=ignored,
            )

        base = (
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
        )
        branch = ref_name
        line_tag = base_tag(base)
        final = final_for_base(tags, base)
        proposal = (
            line_tag
            if operation == "final"
            else base_tag(base, next_rc_for_base(tags, base))
        )

        if final is not None:
            has_exact_final = any(
                tag.raw == line_tag and tag.version.stable for tag in tags
            )
            if (
                confirmed_tag is not None
                and operation == "final"
                and confirmed_tag == line_tag
                and has_exact_final
            ):
                return {
                    "ok": True,
                    "mode": "apply",
                    "context": context,
                    "tag": line_tag,
                    "kind": "final",
                    "release_branch": branch,
                    "latest_tag": latest,
                    "ignored_tag_count": ignored,
                    "is_final": True,
                    "status": "reconcile-existing-final",
                    "reason": (
                        "the final tag already exists; verify its commit and "
                        "reconcile only the PR"
                    ),
                    "tag_state": "existing-final",
                    "application_ready": True,
                }
            return blocked(
                status="blocked-finalized",
                reason=f"{final.version.tag} already finalizes this release line",
                confirmed_tag=confirmed_tag,
                context=context,
                tag=line_tag if operation == "final" else "",
                kind="final" if operation == "final" else "candidate",
                release_branch=branch,
                latest=latest,
                ignored=ignored,
            )

    kind = "final" if operation == "final" else "candidate"
    if confirmed_tag is not None and confirmed_tag != proposal:
        return blocked(
            status="blocked-confirmation-mismatch",
            reason="the confirmed tag does not match the current exact proposal",
            confirmed_tag=confirmed_tag,
            context=context,
            tag=proposal,
            kind=kind,
            release_branch=branch,
            latest=latest,
            ignored=ignored,
        )

    return {
        "ok": True,
        "mode": "apply" if confirmed_tag is not None else "plan",
        "context": context,
        "tag": proposal,
        "kind": kind,
        "release_branch": branch,
        "latest_tag": latest,
        "ignored_tag_count": ignored,
        "is_final": is_final_tag(proposal),
        "status": "application-ready" if confirmed_tag is not None else "proposal-ready",
        "reason": "",
        "tag_state": "absent",
        "application_ready": confirmed_tag is not None,
    }


def markdown_value(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|").replace("`", "\\`")


def write_outputs(path: Path, result: dict[str, object]) -> None:
    output_keys = (
        "application_ready",
        "context",
        "default_branch",
        "is_final",
        "kind",
        "release_branch",
        "resolver_version",
        "status",
        "tag",
        "tag_snapshot",
        "tag_state",
    )
    with path.open("a", encoding="utf-8") as output:
        for key in output_keys:
            value = result.get(key, "")
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            output.write(f"{key}={rendered}\n")


def write_summary(
    path: Path,
    *,
    result: dict[str, object],
    operation: str,
    ref_name: str,
    target_sha: str,
) -> None:
    rows = (
        ("Mode", result["mode"]),
        ("Selected ref", ref_name),
        ("Selected commit", target_sha),
        ("Operation", operation),
        ("Resolver version", result["resolver_version"]),
        ("Latest SemVer tag", result["latest_tag"] or "none"),
        ("Legacy SemVer tags", result["legacy_tag_count"]),
        ("Ignored non-SemVer tags", result["ignored_tag_count"]),
        ("Resolved tag", result["tag"] or "blocked"),
        ("Final tag", result["is_final"]),
        ("Release branch", result["release_branch"] or "n/a"),
        ("Status", result["status"]),
    )
    lines = ["## Release version resolution", "", "| Field | Value |", "| --- | --- |"]
    lines.extend(f"| {label} | `{markdown_value(value)}` |" for label, value in rows)
    lines.extend(
        [
            "",
            "This workflow checks out only `.github/scripts/resolve_release_version.py` "
            "from the verified default-branch commit. It does not check out application "
            "source, read package metadata, edit files, or create commits.",
        ]
    )
    if result["legacy_tag_count"]:
        lines.extend(
            [
                "",
                "Legacy SemVer tags without `v` were used only as read-only version "
                "context. Every new proposal remains canonical.",
            ]
        )
    if result["reason"]:
        lines.extend(["", f"**Blocked:** {markdown_value(result['reason'])}"])
    elif result["mode"] == "plan":
        lines.extend(
            [
                "",
                "Run **Release version (apply)** from the same ref and enter the exact "
                "resolved tag to confirm it.",
            ]
        )
    elif result["tag_state"] == "existing-final":
        lines.extend(
            [
                "",
                "The tag will not be recreated or moved; only final PR reconciliation "
                "may continue.",
            ]
        )
    else:
        lines.extend(["", "The exact confirmation matches the current proposal."])

    with path.open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=RESOLVER_VERSION)
    parser.add_argument("--application-mode", action="store_true")
    parser.add_argument("--confirmed-tag", default="")
    parser.add_argument("--default-branch", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--github-step-summary", type=Path, required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--ref-name", required=True)
    parser.add_argument("--tag-snapshot", required=True)
    parser.add_argument("--tags-file", type=Path, required=True)
    parser.add_argument("--target-sha", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    raw_tags = [
        line
        for line in args.tags_file.read_text(encoding="utf-8").splitlines()
        if line
    ]
    parsed_tags, ignored = parse_tags(raw_tags)
    operation = normalize_operation(args.operation)
    confirmed_tag = args.confirmed_tag if args.application_mode else None
    if args.application_mode and operation == "auto":
        operation = infer_operation(
            ref_name=args.ref_name,
            default_branch=args.default_branch,
            raw_tags=raw_tags,
            confirmed_tag=confirmed_tag or "",
        )

    result = resolve(
        ref_name=args.ref_name,
        default_branch=args.default_branch,
        operation=operation,
        raw_tags=raw_tags,
        confirmed_tag=confirmed_tag,
    )
    result["default_branch"] = args.default_branch
    result["resolver_version"] = RESOLVER_VERSION
    result["tag_snapshot"] = args.tag_snapshot
    result["legacy_tag_count"] = sum(not tag.canonical for tag in parsed_tags)
    result["ignored_tag_count"] = ignored

    write_outputs(args.github_output, result)
    write_summary(
        args.github_step_summary,
        result=result,
        operation=operation,
        ref_name=args.ref_name,
        target_sha=args.target_sha,
    )
    print(
        f"status={result['status']} tag={result['tag'] or 'blocked'} "
        f"is_final={str(result['is_final']).lower()}"
    )
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
