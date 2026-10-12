#!/usr/bin/env python3
"""Resolve this checkout and remember the user's crawl output folder."""

import argparse
import json
from pathlib import Path


def output_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Output folder must be an absolute path or start with ~/")
    if path.exists() and not path.is_dir():
        raise ValueError(f"Output folder is not a directory: {path}")
    return path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", help="Save the folder explicitly chosen by the user")
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parents[3]
    if not (repo_dir / "docker-compose.yaml").is_file():
        raise SystemExit(f"Firecrawl Compose file not found in {repo_dir}")

    config_file = Path.home() / ".config/firecrawl/skill.json"
    if args.output_dir is not None:
        output_dir = output_path(args.output_dir)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            json.dumps({"output_dir": str(output_dir)}, indent=2) + "\n",
            encoding="utf-8",
        )
    elif config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
        output_dir = output_path(config["output_dir"])
    else:
        output_dir = None

    print(json.dumps({
        "repo_dir": str(repo_dir),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "config_file": str(config_file),
    }))


if __name__ == "__main__":
    main()
