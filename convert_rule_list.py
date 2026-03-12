#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


def convert_line(line: str) -> str | None:
    item = line.strip()
    if not item or item.startswith("#"):
        return None

    if item.startswith("+."):
        return f"DOMAIN-SUFFIX,{item[2:]}"

    return f"DOMAIN,{item}"


def build_output(lines: list[str]) -> list[str]:
    output: list[str] = []
    for raw_line in lines:
        converted = convert_line(raw_line)
        if converted is not None:
            output.append(converted)
    return output


def load_input_lines(input_value: str) -> list[str]:
    parsed = urlparse(input_value)
    if parsed.scheme in {"http", "https"}:
        with urlopen(input_value) as response:
            content = response.read().decode("utf-8")
        return content.splitlines()

    return Path(input_value).read_text(encoding="utf-8").splitlines()


def infer_output_name(input_name: str, source_label: str | None) -> str:
    if source_label:
        parsed = urlparse(source_label)
        candidate = Path(parsed.path).name
        if candidate:
            return candidate
    return f"{Path(input_name).stem}_rules.list"


def load_config(config_path: str) -> tuple[str | None, list[str]]:
    content = Path(config_path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(content) or {}
        rules = data.get("rules", {})
        name = rules.get("name")
        urls = rules.get("url", [])
        if not isinstance(urls, list):
            raise ValueError("'rules.url' must be a list")
        return name, [str(item) for item in urls]
    except ModuleNotFoundError:
        name: str | None = None
        urls: list[str] = []
        in_rules = False
        in_url = False

        for raw_line in content.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "rules:":
                in_rules = True
                in_url = False
                continue
            if not in_rules:
                continue
            if stripped.startswith("name:"):
                name = stripped.split(":", 1)[1].strip().strip("\"'")
                in_url = False
                continue
            if stripped.startswith("url:"):
                in_url = True
                continue
            if in_url and stripped.startswith("-"):
                urls.append(stripped[1:].strip().strip("\"'"))

        return name, urls


def ensure_unique_asset_names(inputs: list[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for input_value in inputs:
        name = infer_output_name(input_value, input_value)
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        names = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate asset names detected: {names}")


def write_output(
    input_value: str,
    output_name: str | None = None,
    release_name: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    inferred_name = output_name or infer_output_name(input_value, input_value)
    output_path = (output_dir / inferred_name) if output_dir else Path(inferred_name)

    parsed_input = urlparse(input_value)
    if parsed_input.scheme not in {"http", "https"}:
        input_path = Path(input_value)
        if output_path.resolve() == input_path.resolve():
            output_path = input_path.with_name(f"{input_path.stem}_rules.list")

    converted_lines = build_output(load_input_lines(input_value))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = [f"# Generated at: {generated_at}"]
    if release_name:
        header.append(f"# Release: {release_name}")
    header.extend(
        [
            f"# Source: {input_value}",
            "",
        ]
    )
    output_path.write_text(
        "\n".join(header + converted_lines) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_release_metadata(
    release_name: str,
    config_path: str,
    sources: list[str],
    asset_paths: list[Path],
    output_dir: Path,
) -> Path:
    metadata_path = output_dir / "release-metadata.json"
    payload = {
        "release_name": release_name,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config_path": config_path,
        "sources": sources,
        "asset_paths": [str(path) for path in asset_paths],
    }
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a domain list into Classical rules."
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input_path",
        help="Source list file.",
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config_path",
        help="Load release name and multiple sources from a YAML config file.",
    )
    parser.add_argument(
        "-d",
        "--dist-dir",
        dest="dist_dir",
        default="dist",
        help="Base directory for generated release assets in config mode.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        help="Output list file. If omitted, infer from the input file name.",
    )
    args = parser.parse_args()

    if not args.input_path and not args.config_path:
        parser.print_help()
        raise SystemExit(0)

    if args.input_path and args.config_path:
        parser.error("--input and --config cannot be used together")

    if args.config_path:
        release_name, inputs = load_config(args.config_path)
        if not inputs:
            parser.error("config does not contain any sources in rules.url")
        if not release_name:
            parser.error("config does not contain rules.name")
        if args.output:
            parser.error("output cannot be used with --config")
        ensure_unique_asset_names(inputs)
        release_dir = Path(args.dist_dir) / release_name
        release_dir.mkdir(parents=True, exist_ok=True)
        asset_paths = [
            write_output(
                input_value,
                release_name=release_name,
                output_dir=release_dir,
            )
            for input_value in inputs
        ]
        metadata_path = write_release_metadata(
            release_name=release_name,
            config_path=args.config_path,
            sources=inputs,
            asset_paths=asset_paths,
            output_dir=release_dir,
        )
        print(metadata_path)
        return

    write_output(args.input_path, output_name=args.output)


if __name__ == "__main__":
    main()
