"""The inputs at a glance: a report of everything the measurement reads now.

Made by the *Test inputs* button on the grid connection device: the grid
meter (source, how often it sent a value during the test, per phase power,
current, voltage and power factor, the load against the fuse), the power
flows HomeBatteryAssist derives from it, and every sensor it reads (PV
sources, excluded devices, heating/cooling, batteries) with its value now.
Shown as a persistent notification (Markdown).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "title": "HomeBatteryAssist: test of the inputs",
        "grid": "Grid connection",
        "source": "Source",
        "sensors": "sensors",
        "direct": "read directly",
        "connection": "Connection",
        "updates": "Values in {s} s",
        "per_s": "{n} ({r} per second)",
        "last": "Last value",
        "none": "none",
        "phase": "Phase",
        "power": "Power",
        "current": "Current",
        "voltage": "Voltage",
        "pf": "Power factor",
        "load": "Load",
        "flows": "Power flows now",
        "grid_w": "Grid (+ import / - export)",
        "pv_w": "PV",
        "excluded_w": "Excluded devices",
        "battery_w": "Batteries (+ charging)",
        "heating_w": "Heating/cooling (part of the house)",
        "house_w": "House consumption",
        "unknown_flow": "Unknown: a grid measurement has no value.",
        "missing": "Without a valid value",
        "inputs": "Sensors read",
        "kind": "Kind",
        "name": "Name",
        "value": "Value",
        "k_grid": "Grid",
        "k_pv": "PV source",
        "k_pv_possible": "PV source (possible power)",
        "k_excluded": "Excluded device",
        "k_heating": "Heating/cooling",
        "k_battery": "Battery",
        "k_current": "Current",
        "k_voltage": "Voltage",
        "ok": "All inputs have a value.",
        "calc": "* Not measured: power / voltage.",
    },
    "nl": {
        "title": "HomeBatteryAssist: test van de invoer",
        "grid": "Netaansluiting",
        "source": "Bron",
        "sensors": "sensoren",
        "direct": "rechtstreeks uitgelezen",
        "connection": "Aansluiting",
        "updates": "Waarden in {s} s",
        "per_s": "{n} ({r} per seconde)",
        "last": "Laatste waarde",
        "none": "geen",
        "phase": "Fase",
        "power": "Vermogen",
        "current": "Stroom",
        "voltage": "Spanning",
        "pf": "Arbeidsfactor",
        "load": "Belasting",
        "flows": "Energiestromen nu",
        "grid_w": "Net (+ afname / - teruglevering)",
        "pv_w": "PV",
        "excluded_w": "Uitgesloten apparaten",
        "battery_w": "Batterijen (+ laden)",
        "heating_w": "Verwarming/koeling (deel van het huis)",
        "house_w": "Huisverbruik",
        "unknown_flow": "Onbekend: een netmeting heeft geen waarde.",
        "missing": "Zonder geldige waarde",
        "inputs": "Uitgelezen sensoren",
        "kind": "Soort",
        "name": "Naam",
        "value": "Waarde",
        "k_grid": "Net",
        "k_pv": "PV-bron",
        "k_pv_possible": "PV-bron (mogelijk vermogen)",
        "k_excluded": "Uitgesloten apparaat",
        "k_heating": "Verwarming/koeling",
        "k_battery": "Batterij",
        "k_current": "Stroom",
        "k_voltage": "Spanning",
        "ok": "Alle invoer heeft een waarde.",
        "calc": "* Niet gemeten: vermogen / spanning.",
    },
}


def _texts(hass: HomeAssistant) -> dict[str, str]:
    lang = (hass.config.language or "en").split("-")[0].lower()
    return TEXTS.get(lang, TEXTS["en"])


def _num(value: float | None, digits: int = 0, unit: str = "") -> str:
    if value is None:
        return "-"
    text = f"{value:.{digits}f}"
    return f"{text} {unit}".strip()


def _state(hass: HomeAssistant, entity_id: str) -> tuple[str, str]:
    """(name, value with unit) of an entity now."""
    state = hass.states.get(entity_id)
    if state is None:
        return entity_id, "-"
    name = state.attributes.get("friendly_name") or entity_id
    unit = state.attributes.get("unit_of_measurement") or ""
    return f"{name} (`{entity_id}`)", f"{state.state} {unit}".strip()


def input_report(
    hass: HomeAssistant,
    measurements: Any,  # MeasurementInput
    source_name: str,
    seconds: float,
    updates: int,
    last: datetime | None,
    battery_states: list[Any],
) -> tuple[str, str]:
    """(title, Markdown message) of the inputs now and during the test."""
    t = _texts(hass)
    m = measurements
    lines: list[str] = [f"### {t['grid']}", ""]
    direct = m.direct
    source = (
        f"{source_name}, {t['direct']}"  # no address: every user sees it
        if direct is not None
        else t["sensors"]
    )
    rate = updates / seconds if seconds else 0.0
    lines += [
        f"- {t['source']}: {source}",
        f"- {t['connection']}: {m.phases} x {m.max_current} A",
        f"- {t['updates'].format(s=f'{seconds:.0f}')}: "
        + t["per_s"].format(n=updates, r=f"{rate:.1f}"),
        f"- {t['last']}: "
        + (dt_util.as_local(last).strftime("%H:%M:%S") if last else t["none"]),
        "",
    ]
    flow = m.flow
    if flow is not None:
        lines += [
            f"| {t['phase']} | {t['power']} | {t['current']} | {t['voltage']} "
            f"| {t['pf']} | {t['load']} |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for i in range(m.phases):
            amps = flow.phase_amps(i)
            volts = flow.phase_v[i] if i < len(flow.phase_v) else None
            pf = flow.phase_pf[i] if i < len(flow.phase_pf) else None
            measured = i < len(flow.phase_a)
            load = abs(amps) / m.max_current * 100 if m.max_current else None
            lines.append(
                f"| L{i + 1} | {_num(flow.phase_w[i], 0, 'W')} "
                f"| {_num(amps, 1, 'A')}{'' if measured else ' *'} "
                f"| {_num(volts, 0, 'V')} | {_num(pf, 2)} | {_num(load, 0, '%')} |"
            )
        if any(i >= len(flow.phase_a) for i in range(m.phases)):
            lines += ["", t["calc"]]
        lines += ["", f"#### {t['flows']}", ""]
        lines += [f"| | {t['power']} |", "|---|---:|"]
        for key in (
            "grid_w",
            "pv_w",
            "excluded_w",
            "battery_w",
            "heating_w",
            "house_w",
        ):
            lines.append(f"| {t[key]} | {_num(getattr(flow, key), 0, 'W')} |")
    else:
        lines.append(t["unknown_flow"])
    lines.append("")

    rows: list[tuple[str, str]] = []
    for imp, ret in m.grid_phases:
        rows.append((t["k_grid"], imp))
        if ret:
            rows.append((t["k_grid"], ret))
    rows += [(t["k_current"], s) for s in m.current_sensors if s]
    rows += [(t["k_voltage"], s) for s in m.voltage_sensors if s]
    rows += [(t["k_pv"], s) for s in m.pv_sensors if s]
    rows += [(t["k_pv_possible"], s) for _, s in getattr(m, "pv_possible", [])]
    rows += [(t["k_excluded"], s) for s in m.excluded_sensors if s]
    rows += [(t["k_heating"], s) for s in m.heating_sensors if s]
    for state in battery_states:
        config = state.config
        if config.virtual:
            continue
        rows += [
            (t["k_battery"], s) for s in (config.soc_sensor, config.power_sensor) if s
        ]
    if rows:
        lines += [
            f"#### {t['inputs']}",
            "",
            f"| {t['kind']} | {t['name']} | {t['value']} |",
            "|---|---|---:|",
        ]
        for kind, entity_id in rows:
            name, value = _state(hass, entity_id)
            lines.append(f"| {kind} | {name} | {value} |")
        lines.append("")
    if m.missing:
        lines.append(f"**{t['missing']}:** " + ", ".join(f"`{e}`" for e in m.missing))
    else:
        lines.append(t["ok"])
    return t["title"], "\n".join(lines)
