#!/usr/bin/env python3
"""Resolve this checkout and remember crawl output folders for each Git repository."""

import argparse
import json
import subprocess
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
    parser.add_argument("--project-dir", help="Project directory; defaults to the working directory")
    parser.add_argument("--output-dir", help="Save the folder explicitly chosen by the user")
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parents[3]
    if not (repo_dir / "docker-compose.yaml").is_file():
        raise SystemExit(f"Firecrawl Compose file not found in {repo_dir}")

    directory = Path(args.project_dir).expanduser().resolve() if args.project_dir is not None else Path.cwd()
    project_dir = Path(subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()).resolve()

    config_file = Path.home() / ".config/firecrawl/skill.json"
    config = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {"projects": {}}
    projects = config["projects"]
    if not isinstance(projects, dict):
        raise ValueError("Saved projects must be an object")

    if args.output_dir is not None:
        output_dir = output_path(args.output_dir)
        projects[str(project_dir)] = str(output_dir)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            json.dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )
    elif str(project_dir) in projects:
        output_dir = output_path(projects[str(project_dir)])
    else:
        output_dir = None

    print(json.dumps({
        "repo_dir": str(repo_dir),
        "project_dir": str(project_dir),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "config_file": str(config_file),
    }))


if __name__ == "__main__":
    main()
