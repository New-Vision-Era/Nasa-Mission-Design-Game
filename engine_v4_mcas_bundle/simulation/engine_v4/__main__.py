"""Command line: python -m simulation.engine_v4 examples/example_mission.json [--full] [--recommend]"""
from __future__ import annotations

import json
import sys

from .api import handle_recommend_request, handle_run_request


def main(argv: list[str]) -> int:
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2
    with open(paths[0], "r", encoding="utf-8") as fh:
        body = json.load(fh)
    if "--recommend" in argv:
        status, result = handle_recommend_request(body)
        print(json.dumps(result, indent=2))
        return 0 if status == 200 else 1
    status, result = handle_run_request(body)
    if status != 200 or "--full" in argv:
        print(json.dumps(result, indent=2))
        return 0 if status == 200 else 1
    print(f"Scenario     : {result['scenario']['name']}")
    print(f"Feasibility  : {result['feasibility']['status']}")
    print(f"Outcome      : {result['mission']['outcome']}")
    score = result["score"]
    print(f"Score        : {score['total']} / 100  (completeness {score['completeness'] * 100:.0f}%)")
    print("\nConstraints")
    for c in result["constraints"]:
        print(f"  [{c['status']:<13}] {c['severity']:<4} {c['title']}: {c['message']}")
    print("\nScore breakdown")
    for cat in score["categories"]:
        pts = "not evaluated" if cat["points"] is None else f"{cat['points']:.1f} / {cat['weight']:g}"
        print(f"  {cat['title']}: {pts}")
        for reason in cat["reasons"]:
            print(f"      - {reason}")
    print("\nMission")
    for stage in result["mission"]["stages"]:
        print(f"  {stage['title']}: {stage['message']}")
    for event in result["mission"]["events"]:
        if not event["effect"]["applies"]:
            continue
        print(f"  event (period {event['period']}): {event['title']} - {event['explanation']}")
    print("\nDebrief")
    for item in result["explanations"]:
        print(f"  ({item['kind']}) {item['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
