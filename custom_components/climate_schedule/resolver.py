# Bestand: custom_components/climate_schedule/resolver.py
# Versie: 0.0.1
"""Pure logica zonder Home Assistant imports, zodat de tester dit los kan draaien.

Datamodel (zie readme.md):
  users[naam].presets[presetnaam][climate] = [ {start, end, temp}, ... ]
  users[naam].schedule[weekdag] = presetnaam | null
  defaults[climate][weekdag] = temp | (ontbreekt = niets sturen)
"""
from __future__ import annotations

import re
from typing import Any

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ScheduleError(ValueError):
    """Fout in het datamodel of in een mutatie."""


# ---------- hulpfuncties ----------

def valid_time(value: Any) -> str:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise ScheduleError(f"Ongeldige tijd '{value}', verwacht HH:MM")
    return value


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hits(start: int, end: int, minute: int) -> tuple[bool, bool]:
    """(actief binnen de eigen dag, actief als restant van de vorige dag)."""
    if start < end:
        return start <= minute < end, False
    if start > end:  # slot loopt over middernacht
        return minute >= start, minute < end
    return False, False  # start == end wordt genegeerd


def _user(data: dict, user: str) -> dict:
    if user not in data["users"]:
        raise ScheduleError(f"Onbekende gebruiker: {user}")
    return data["users"][user]


# ---------- berekeningen ----------

def active_slots(data: dict, climate: str, weekday_idx: int, minute: int) -> list[dict]:
    """Alle slots die op dit moment actief zijn voor deze climate."""
    today = WEEKDAYS[weekday_idx]
    yesterday = WEEKDAYS[(weekday_idx - 1) % 7]
    out: list[dict] = []
    for user, udata in data["users"].items():
        schedule = udata.get("schedule", {})
        presets = udata.get("presets", {})
        for day_key, is_today in ((today, True), (yesterday, False)):
            preset = schedule.get(day_key)
            if preset is None:
                continue
            if preset not in presets:
                raise ScheduleError(f"Preset '{preset}' bestaat niet bij {user}")
            for slot in presets[preset].get(climate, []):
                s, e = to_minutes(slot["start"]), to_minutes(slot["end"])
                hit_today, hit_overnight = _hits(s, e, minute)
                if (hit_today if is_today else hit_overnight):
                    out.append({"user": user, "temp": float(slot["temp"]), "preset": preset})
    return out


def today_presets(data: dict, weekday_idx: int) -> dict[str, str | None]:
    """Welke preset heeft elke gebruiker op deze weekdag."""
    day = WEEKDAYS[weekday_idx]
    return {u: ud.get("schedule", {}).get(day) for u, ud in data["users"].items()}


def resolve(data: dict, climate: str, weekday_idx: int, minute: int):
    """Hoogste temperatuur wint. Geeft (temp, [gebruikers]) of (None, [])."""
    active = active_slots(data, climate, weekday_idx, minute)
    if not active:
        return None, []
    top = max(s["temp"] for s in active)
    return top, sorted({s["user"] for s in active if s["temp"] == top})


def default_temp(data: dict, climate: str, weekday_idx: int):
    return data.get("defaults", {}).get(climate, {}).get(WEEKDAYS[weekday_idx])


def effective(data: dict, climate: str, weekday_idx: int, minute: int):
    """Uiteindelijk setpoint: (temp, [gebruikers], bron) met bron = slot | default | geen."""
    temp, users = resolve(data, climate, weekday_idx, minute)
    if temp is not None:
        return temp, users, "slot"
    default = default_temp(data, climate, weekday_idx)
    if default is None:
        return None, [], "geen"
    return float(default), [], "default"


def timeline(data: dict, climate: str, weekday_idx: int) -> list[dict]:
    """Dagverloop in segmenten. Opeenvolgende minuten met hetzelfde resultaat worden samengevoegd."""
    segments: list[dict] = []
    for minute in range(24 * 60):
        temp, users, source = effective(data, climate, weekday_idx, minute)
        last = segments[-1] if segments else None
        if last and (last["temp"], last["gebruikers"], last["bron"]) == (temp, users, source):
            last["end"] = to_hhmm(minute + 1)
        else:
            segments.append({
                "start": to_hhmm(minute),
                "end": to_hhmm(minute + 1),
                "temp": temp,
                "gebruikers": users,
                "bron": source,
            })
    return segments


# ---------- validatie ----------

def validate(data: Any) -> list[str]:
    """Geeft een lijst met fouten terug. Lege lijst = datamodel is geldig."""
    if not isinstance(data, dict):
        return ["Datamodel is geen object"]
    errors: list[str] = []

    for climate, days in data.get("defaults", {}).items():
        for day, temp in days.items():
            if day not in WEEKDAYS:
                errors.append(f"defaults {climate}: onbekende dag '{day}'")
            elif temp is not None and not isinstance(temp, (int, float)):
                errors.append(f"defaults {climate}/{day}: temp moet een getal zijn")

    for user, udata in data.get("users", {}).items():
        presets = udata.get("presets", {})
        for pname, climates in presets.items():
            for climate, slots in climates.items():
                for i, slot in enumerate(slots):
                    where = f"{user}/{pname}/{climate}[{i}]"
                    try:
                        s = to_minutes(valid_time(slot.get("start")))
                        e = to_minutes(valid_time(slot.get("end")))
                    except ScheduleError as err:
                        errors.append(f"{where}: {err}")
                        continue
                    if s == e:
                        errors.append(f"{where}: start en eind mogen niet gelijk zijn")
                    if not isinstance(slot.get("temp"), (int, float)):
                        errors.append(f"{where}: temp moet een getal zijn")

        for day, pname in udata.get("schedule", {}).items():
            if day not in WEEKDAYS:
                errors.append(f"{user}/schedule: onbekende dag '{day}'")
            elif pname is not None and pname not in presets:
                errors.append(f"{user}/schedule/{day}: preset '{pname}' bestaat niet")

    return errors


# ---------- mutaties (gebruikt door services én tester) ----------

def add_user(data: dict, name: str) -> None:
    if not name or not isinstance(name, str):
        raise ScheduleError("Naam van gebruiker is verplicht")
    data["users"].setdefault(name, {"presets": {}, "schedule": {}})


def remove_user(data: dict, name: str) -> None:
    data["users"].pop(name, None)


def set_preset_slot(data: dict, user: str, preset: str, climate: str,
                    start: str, end: str, temp: float) -> None:
    udata = _user(data, user)
    valid_time(start)
    valid_time(end)
    if start == end:
        raise ScheduleError("Start en eind mogen niet gelijk zijn")
    slots = udata["presets"].setdefault(preset, {}).setdefault(climate, [])
    slots.append({"start": start, "end": end, "temp": float(temp)})
    slots.sort(key=lambda s: to_minutes(s["start"]))


def remove_preset_slot(data: dict, user: str, preset: str, climate: str, start: str) -> None:
    udata = _user(data, user)
    slots = udata["presets"].get(preset, {}).get(climate, [])
    slots[:] = [s for s in slots if s["start"] != start]


def delete_preset(data: dict, user: str, preset: str) -> None:
    udata = _user(data, user)
    udata["presets"].pop(preset, None)
    for day, pname in udata["schedule"].items():
        if pname == preset:
            udata["schedule"][day] = None


def set_schedule(data: dict, user: str, weekday: str, preset: str | None) -> None:
    udata = _user(data, user)
    if weekday not in WEEKDAYS:
        raise ScheduleError(f"Onbekende dag '{weekday}'")
    if preset is not None and preset not in udata["presets"]:
        raise ScheduleError(f"Preset '{preset}' bestaat niet bij {user}")
    udata["schedule"][weekday] = preset


def set_default(data: dict, climate: str, weekday: str, temp: float | None) -> None:
    if weekday not in WEEKDAYS:
        raise ScheduleError(f"Onbekende dag '{weekday}'")
    days = data.setdefault("defaults", {}).setdefault(climate, {})
    if temp is None:
        days.pop(weekday, None)
    else:
        days[weekday] = float(temp)
