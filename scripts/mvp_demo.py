from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from drone_inspection.mvp_demo import build_demo_summary, format_demo_summary


def main() -> int:
    print(format_demo_summary(build_demo_summary()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
