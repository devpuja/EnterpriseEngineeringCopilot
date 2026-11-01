import argparse
import asyncio
from pathlib import Path

from app.evaluation.models import EvaluationDataset
from app.evaluation.runner import run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline deterministic evaluation; no model calls.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dataset = EvaluationDataset.model_validate_json(args.dataset.read_text(encoding="utf-8"))
    run = asyncio.run(run_evaluation(dataset))
    serialized = run.model_dump_json(indent=2)
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized)
    return 1 if run.failed or run.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
