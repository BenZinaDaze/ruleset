#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


CST = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class ReleaseConfig:
    name: str
    urls: list[str]


def format_timestamp() -> str:
    return datetime.now(CST).isoformat(sep=" ", timespec="seconds")


def is_http_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


def convert_line(line: str) -> str | None:
    item = line.strip()
    if not item or item.startswith("#"):
        return None

    if item.startswith("+."):
        return f"DOMAIN-SUFFIX,{item[2:]}"

    return f"DOMAIN,{item}"


def build_output(lines: list[str]) -> list[str]:
    return [
        converted
        for raw_line in lines
        if (converted := convert_line(raw_line)) is not None
    ]


def read_remote_lines(source: str) -> list[str]:
    with urlopen(source) as response:
        content = response.read().decode("utf-8")
    return content.splitlines()


def read_local_lines(source: str) -> list[str]:
    return Path(source).read_text(encoding="utf-8").splitlines()


def load_input_lines(input_value: str) -> list[str]:
    if is_http_url(input_value):
        return read_remote_lines(input_value)
    return read_local_lines(input_value)


def infer_output_name(input_name: str, source_label: str | None = None) -> str:
    if source_label:
        parsed = urlparse(source_label)
        candidate = Path(parsed.path).name
        if candidate:
            return candidate
    return f"{Path(input_name).stem}_rules.list"


def load_yaml_config(config_path: str) -> ReleaseConfig:
    content = Path(config_path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(content) or {}
        rules = data.get("rules", {})
        name = rules.get("name")
        urls = rules.get("url", [])
        if not isinstance(urls, list):
            raise ValueError("'rules.url' must be a list")
        if not name:
            raise ValueError("config does not contain rules.name")
        return ReleaseConfig(name=str(name), urls=[str(item) for item in urls])
    except ModuleNotFoundError:
        return load_fallback_config(content)


def load_fallback_config(content: str) -> ReleaseConfig:
    release_name: str | None = None
    urls: list[str] = []
    in_rules_section = False
    in_url_section = False

    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "rules:":
            in_rules_section = True
            in_url_section = False
            continue
        if not in_rules_section:
            continue
        if stripped.startswith("name:"):
            release_name = stripped.split(":", 1)[1].strip().strip("\"'")
            in_url_section = False
            continue
        if stripped.startswith("url:"):
            in_url_section = True
            continue
        if in_url_section and stripped.startswith("-"):
            urls.append(stripped[1:].strip().strip("\"'"))

    if not release_name:
        raise ValueError("config does not contain rules.name")
    return ReleaseConfig(name=release_name, urls=urls)


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


def resolve_output_path(
    input_value: str,
    output_name: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    inferred_name = output_name or infer_output_name(input_value, input_value)
    output_path = (output_dir / inferred_name) if output_dir else Path(inferred_name)

    if is_http_url(input_value):
        return output_path

    input_path = Path(input_value)
    if output_path.resolve() == input_path.resolve():
        return input_path.with_name(f"{input_path.stem}_rules.list")
    return output_path


def build_header_lines(source: str, release_name: str | None = None) -> list[str]:
    header = [f"# Generated at: {format_timestamp()}"]
    if release_name:
        header.append(f"# Release: {release_name}")
    header.extend(
        [
            f"# Source: {source}",
            "",
        ]
    )
    return header


def write_output(
    input_value: str,
    output_name: str | None = None,
    release_name: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    output_path = resolve_output_path(input_value, output_name, output_dir)
    converted_lines = build_output(load_input_lines(input_value))
    output_path.write_text(
        "\n".join(build_header_lines(input_value, release_name) + converted_lines) + "\n",
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
        "generated_at": format_timestamp(),
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
        config = load_yaml_config(args.config_path)
        if not config.urls:
            parser.error("config does not contain any sources in rules.url")
        if args.output:
            parser.error("output cannot be used with --config")
        ensure_unique_asset_names(config.urls)
        release_dir = Path(args.dist_dir) / config.name
        release_dir.mkdir(parents=True, exist_ok=True)
        asset_paths = [
            write_output(
                input_value,
                release_name=config.name,
                output_dir=release_dir,
            )
            for input_value in config.urls
        ]
        metadata_path = write_release_metadata(
            release_name=config.name,
            config_path=args.config_path,
            sources=config.urls,
            asset_paths=asset_paths,
            output_dir=release_dir,
        )
        print(metadata_path)
        return

    write_output(args.input_path, output_name=args.output)


if __name__ == "__main__":
    main()
