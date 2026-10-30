"""Build the Lambda zip: dependencies for linux/arm64, the package, and the ONNX models.

    uv run python scripts/build_lambda.py            # writes build/lambda.zip

Needs network once, to download linux wheels from PyPI. No Docker: every dependency has a
prebuilt manylinux aarch64 wheel. The embedding models come from the local fastembed cache, so
run `python -m rail_aws_rag.build_index` first (it downloads them on first use). The zip must stay
under Lambda's 250 MB unzipped limit; the script fails below a 10 MB margin.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "build"
LIMIT = 262_144_000  # Lambda's unzipped size limit in bytes
MARGIN = 10_000_000
PYTHON_VERSION = "3.12"
PLATFORM = "aarch64-manylinux_2_28"  # Lambda python3.12 runs Amazon Linux 2023 (glibc 2.34)
MODELS = ("models--Qdrant--bge-small-en-v1.5-onnx-Q", "models--Qdrant--bm25")
FASTEMBED_CACHE = Path.home() / ".cache" / "fastembed"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # same inputs, same zip bytes

# Dead weight inside installed packages: tests, bytecode, type stubs and onnxruntime's offline
# tooling, none of which the Lambda imports.
PRUNE_DIRS = ("__pycache__", "tests", "test")
PRUNE_UNDER = (
    "onnxruntime/transformers",
    "onnxruntime/tools",
    "onnxruntime/quantization",
    "onnxruntime/datasets",
    "numpy/_core/tests",
    "numpy/f2py",
)
PRUNE_SUFFIXES = (".pyc", ".pyi", ".pyx", ".h")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def install_dependencies(target: Path) -> None:
    requirements = BUILD / "lambda-requirements.txt"
    run(
        [
            "uv",
            "pip",
            "compile",
            str(REPO / "pyproject.toml"),
            "--python-platform",
            PLATFORM,
            "--python-version",
            PYTHON_VERSION,
            "--no-header",
            "--quiet",
            "-o",
            str(requirements),
        ]  # fmt: skip
    )
    run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(target),
            "--requirement",
            str(requirements),
            "--python-platform",
            PLATFORM,
            "--python-version",
            PYTHON_VERSION,
            "--only-binary",
            ":all:",
            "--no-deps",
            "--quiet",
        ]  # fmt: skip
    )


def copy_models(target: Path) -> None:
    """HF-cache layout without the blobs: snapshots are dereferenced into real files."""
    for name in MODELS:
        source = FASTEMBED_CACHE / name
        if not (source / "snapshots").is_dir():
            sys.exit(f"{name} is not in {FASTEMBED_CACHE}: run rail_aws_rag.build_index first")
        for sub in ("snapshots", "refs"):
            shutil.copytree(source / sub, target / name / sub, symlinks=False)


def prune(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        rel = path.relative_to(root).as_posix()
        if path.is_dir() and (path.name in PRUNE_DIRS or rel in PRUNE_UNDER):
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file() and path.suffix in PRUNE_SUFFIXES:
            path.unlink()


def make_zip(root: Path, out: Path) -> int:
    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), FIXED_TIME)
            info.external_attr = (0o755 if path.stat().st_mode & 0o111 else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            data = path.read_bytes()
            total += len(data)
            z.writestr(info, data, compresslevel=9)
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=BUILD / "lambda.zip")
    args = ap.parse_args(argv)

    package = BUILD / "lambda"
    shutil.rmtree(package, ignore_errors=True)
    package.mkdir(parents=True)

    install_dependencies(package)
    shutil.copytree(REPO / "src" / "rail_aws_rag", package / "rail_aws_rag")
    copy_models(package / "models")
    prune(package)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    unzipped = make_zip(package, args.out)
    zipped = args.out.stat().st_size
    print(f"{args.out}: {zipped / 1e6:.1f} MB zipped, {unzipped / 1e6:.1f} MB unzipped")
    print(f"limit {LIMIT / 1e6:.0f} MB, margin {(LIMIT - unzipped) / 1e6:.1f} MB")
    if unzipped > LIMIT - MARGIN:
        sys.exit("too close to Lambda's unzipped size limit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
