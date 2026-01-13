import sys
from pathlib import Path
from mangapy import cli

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/dev_run.py <sample-filename.yaml>")
        sys.exit(2)

    samples_dir = REPO_ROOT / "samples"
    sample_name = sys.argv[1]
    yaml_file = samples_dir / sample_name
    if not yaml_file.is_file():
        available = sorted(p.name for p in samples_dir.glob("*.yaml"))
        print(f"Sample not found: {sample_name}")
        if available:
            print("Available samples:")
            for name in available:
                print(f"- {name}")
        sys.exit(2)

    # Local-only helper: run a sample YAML without touching the main CLI entrypoint.
    sys.argv = ["mangapy", "yaml", str(yaml_file)]
    cli.main()


if __name__ == "__main__":
    main()
