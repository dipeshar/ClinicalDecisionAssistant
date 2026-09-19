"""Minimal command-line interface for the T0 skeleton."""

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Show help until the run command is implemented in T16."""
    parser = argparse.ArgumentParser(
        prog="python -m council",
        description=(
            "LLM Council: decision support only; requires human clinical sign-off. "
            "Synthetic data only."
        ),
    )
    parser.parse_args(argv)
    parser.print_help()
    return 0
