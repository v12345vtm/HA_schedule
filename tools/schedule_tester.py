# Bestand: tools/schedule_tester.py
# Versie: 0.0.3
"""Tester voor het climate_schedule datamodel. Draait zonder Home Assistant.

Gebruik (vanuit de repo-root):
  python tools/schedule_tester.py                          # seed.json valideren + weekoverzicht
  python tools/schedule_tester.py pad/naar/mijn.json       # eigen JSON testen
  python tools/schedule_tester.py --at monday 09:30 climate.keuken
  python tools/schedule_tester.py --max-temp 25            # waarschuwen boven max_temp van je thermostaat
  python tools/schedule_tester.py --selftest               # ingebouwde controles
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPONENT = HERE.parent / "custom_components" / "climate_schedule"
sys.path.insert(0, str(COMPONENT))
import resolver as r  # noqa: E402

DEFAULT_FILE = COMPONENT / "seed.json"


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def climates_in(data: dict) -> list[str]:
    found = set(data.get("defaults", {}))
    for udata in data.get("users", {}).values():
        for climates in udata.get("presets", {}).values():
            found.update(climates.keys())
    return sorted(found)


def print_week(data: dict, climate: str, max_temp: float | None) -> None:
    print(f"\n=== {climate} ===")
    for idx, day in enumerate(r.WEEKDAYS):
        print(f"\n{day}")
        for seg in r.timeline(data, climate, idx):
            temp = seg["temp"]
            label = "-" if temp is None else f"{temp:g}°C"
            who = ", ".join(seg["gebruikers"]) or "-"
            flag = ""
            if max_temp is not None and temp is not None and temp > max_temp:
                flag = f"  !! boven max_temp {max_temp:g}"
            print(f"  {seg['start']}-{seg['end']}  {label:>8}  {seg['bron']:<8} {who}{flag}")


def selftest() -> int:
    data = {
        "schema_version": 2,
        "defaults": {"climate.keuken": {"monday": 18}},
        "users": {
            "eric": {
                "presets": {
                    "voormiddag": {"climate.keuken": [{"start": "08:00", "end": "12:00", "temp": 25}]},
                    "nacht": {"climate.keuken": [{"start": "22:00", "end": "02:00", "temp": 17}]},
                },
                "schedule": {"monday": "voormiddag", "sunday": "nacht"},
            },
            "gudrun": {
                "presets": {
                    "ochtend": {"climate.keuken": [{"start": "09:00", "end": "11:00", "temp": 26}]},
                },
                "schedule": {"monday": "ochtend"},
            },
        },
    }
    k = "climate.keuken"
    checks = [
        ("conflict 09:30, hoogste wint", r.effective(data, k, 0, 9 * 60 + 30), (26.0, ["gudrun"], "slot")),
        ("alleen eric 08:30", r.effective(data, k, 0, 8 * 60 + 30), (25.0, ["eric"], "slot")),
        ("middernacht-slot van zondag, 01:00 maandag", r.effective(data, k, 0, 60), (17.0, ["eric"], "slot")),
        ("niemand actief, default", r.effective(data, k, 0, 12 * 60), (18.0, [], "default")),
        ("geen slot en geen default", r.effective(data, k, 1, 9 * 60), (None, [], "geen")),
    ]
    failed = 0
    for name, got, expected in checks:
        ok = got == expected
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {got}" + ("" if ok else f" (verwacht {expected})"))

    errors = r.validate(data)
    ok = errors == []
    failed += not ok
    print(f"{'OK  ' if ok else 'FAIL'} validatie geldig: {errors}")

    bad = {"users": {"x": {"presets": {"p": {k: [{"start": "25:00", "end": "10:00", "temp": 20}]}},
                           "schedule": {"monday": "bestaatniet"}}}}
    ok = len(r.validate(bad)) >= 2
    failed += not ok
    print(f"{'OK  ' if ok else 'FAIL'} validatie vangt fouten: {r.validate(bad)}")

    print("\nALLE CHECKS OK" if failed == 0 else f"\n{failed} CHECK(S) MISLUKT")
    return 0 if failed == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Tester voor climate_schedule JSON")
    ap.add_argument("file", nargs="?", default=str(DEFAULT_FILE), help="JSON-datamodel")
    ap.add_argument("--at", nargs=3, metavar=("DAG", "TIJD", "CLIMATE"),
                    help="Toon het effectieve setpoint, bv: --at monday 09:30 climate.keuken")
    ap.add_argument("--max-temp", type=float, help="Waarschuw voor temperaturen boven dit getal")
    ap.add_argument("--selftest", action="store_true", help="Draai ingebouwde controles")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    data = load(args.file)
    errors = r.validate(data)
    if errors:
        print("FOUT in datamodel:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"Datamodel OK: {args.file}")

    if args.at:
        day, tijd, climate = args.at
        try:
            if day.lower() not in r.WEEKDAYS:
                raise r.ScheduleError(f"Onbekende dag '{day}', gebruik monday..sunday")
            r.valid_time(tijd)
        except r.ScheduleError as err:
            print(f"FOUT: {err}")
            return 1
        temp, users, bron = r.effective(data, climate, r.WEEKDAYS.index(day.lower()), r.to_minutes(tijd))
        label = "geen" if temp is None else f"{temp:g}°C"
        print(f"{climate} op {day.lower()} {tijd}: {label} (bron: {bron}, gebruikers: {users or '-'})")
        return 0

    for climate in climates_in(data):
        print_week(data, climate, args.max_temp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
