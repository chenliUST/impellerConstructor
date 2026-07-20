from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_6_step_audit import (  # noqa: E402
    StepReconstructionAuditService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a synchronous V1.1.6 STEP reconstruction evidence audit."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    payload = source.read_bytes()
    service = StepReconstructionAuditService(args.root, run_async=False)
    handle = service.begin_upload(source.name)
    shutil.copyfile(source, handle.temporary_path)
    result = service.finish_upload(
        handle,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    print(result)


if __name__ == "__main__":
    main()
