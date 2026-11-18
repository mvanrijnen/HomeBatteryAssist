"""Battery drivers: what a battery *is* (model) and how it is *read* (reader).

Two building blocks:

- ``BatteryModel`` — a battery type, organised by inheritance as brand → type
  range → type (e.g. ``marstek/__init__.py`` → ``marstek/venus.py`` →
  ``marstek/venus_e_v3.py``). A type knows its specifications: capacity,
  power, usable part, rated cycles, warranty. They are used as starting
  values when a battery is linked and the reader cannot read them.
- ``BatteryReader`` — how batteries are read through another integration's
  entities (``integrations/``, e.g. Omnibattery or Marstek Modbus). A reader
  recognises the batteries of its integration (``profile``), adds live details
  (``telemetry``), says whether it also serves as the battery's meter
  (``is_meter``: the integration gives the battery's own power) and describes
  how a battery *would* be controlled (write
  methods). **HomeBatteryAssist never calls the write methods** while it is
  read-only; ``can_write`` says whether a reader implements them.

One battery type can be read through several integrations (a Marstek Venus E
v3 through Omnibattery or through Marstek Modbus): the model and the reader
are chosen separately.

Readers only use Home Assistant's states and registries; they never open a
connection to the battery that could compete with its own integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ...measure.battery_monitor import BatteryConfig


@dataclass(slots=True)
class BatteryTelemetry:
    """Extra live details of a battery; None = not known."""

    temperature_c: float | None = None
    voltage_v: float | None = None
    cell_min_v: float | None = None
    cell_max_v: float | None = None
    cycles: float | None = None
    charged_today_kwh: float | None = None
    discharged_today_kwh: float | None = None
    efficiency_pct: float | None = None
    extra: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, float]:
        """Known values only."""
        values = {
            "temperature_c": self.temperature_c,
            "voltage_v": self.voltage_v,
            "cell_min_v": self.cell_min_v,
            "cell_max_v": self.cell_max_v,
            "cycles": self.cycles,
            "charged_today_kwh": self.charged_today_kwh,
            "discharged_today_kwh": self.discharged_today_kwh,
            "efficiency_pct": self.efficiency_pct,
            **self.extra,
        }
        return {k: v for k, v in values.items() if v is not None}


@dataclass(frozen=True, slots=True)
class BatteryCommand:
    """What a battery is told to do right now by whoever controls it (its own
    integration, e.g. Omnibattery; later HomeBatteryAssist), and what may hold
    it back."""

    power_w: float  # + charge / - discharge / 0 = stop
    charge_allowed: bool = True
    discharge_allowed: bool = True
    # Charging held back after a full charge until the state of charge has
    # dropped a little (the battery's own hysteresis).
    hysteresis: bool = False


class BatteryModel:
    """A battery type. Subclass per brand, type range and type; set only what
    is known for sure (None = unknown)."""

    brand: str = ""
    range: str = ""  # type range, e.g. "Venus"
    type: str = ""  # e.g. "Venus E v3"
    # Device model names (as integrations report them) that are this type,
    # compared case-insensitively.
    models: tuple[str, ...] = ()
    capacity_kwh: float | None = None
    max_charge_w: float | None = None
    max_discharge_w: float | None = None
    usable_pct: float | None = None  # usable part of the capacity per cycle
    rated_cycles: int | None = None
    warranty_years: int | None = None
    # Phases it is connected to: 1 = one phase (a plug-in battery), so on a
    # 3-phase connection its phase must be chosen; None = unknown.
    phases: int | None = None

    @property
    def name(self) -> str:
        """Brand and type, e.g. "Marstek Venus E v3"."""
        return " ".join(p for p in (self.brand, self.type or self.range) if p)

    def matches(self, model: str | None) -> bool:
        """Whether a device with this model name is this type."""
        if not model:
            return False
        lowered = model.strip().lower()
        return any(lowered == m.lower() for m in self.models)


@dataclass(frozen=True, slots=True)
class BatteryProfile:
    """How a reader's integration exposes a battery in Home Assistant: the
    translation keys of its entities, mapped to the battery subentry fields."""

    platform: str  # integration domain that creates the entities
    label: str
    soc: str  # translation key of the state of charge sensor
    power: str  # translation key of the (AC) power sensor
    power_sign: str
    # Optional translation keys (domain, key) whose state gives a starting value
    capacity: tuple[str, str] | None = None  # kWh
    max_charge: tuple[str, str] | None = None  # W
    max_discharge: tuple[str, str] | None = None  # W
    min_soc: tuple[str, str] | None = None  # %
    max_soc: tuple[str, str] | None = None  # %
    efficiency: tuple[str, str] | None = None  # %
    phase: tuple[str, str] | None = None  # select with options l1/l2/l3
    # Recognition tested on a real installation (else "not tested").
    verified: bool = False


class BatteryReader:
    """Reads batteries through one integration (its entities)."""

    key: str = ""  # the integration domain (platform of its entities)
    name: str = ""
    verified: bool = False  # reading tested on a real installation
    can_write: bool = False  # write methods implemented (never used yet)
    # Serves as the battery's meter: its integration gives the battery's own
    # power (and energy). Without it the battery needs an external meter.
    is_meter: bool = True
    profile: BatteryProfile | None = None  # recognising its batteries

    def telemetry(self, hass: HomeAssistant, config: BatteryConfig) -> BatteryTelemetry:
        """Extra live details of the battery (default: none)."""
        return BatteryTelemetry()

    def command(
        self, hass: HomeAssistant, config: BatteryConfig
    ) -> BatteryCommand | None:
        """The command the battery has now from its controlling integration
        (read only), or None: not readable, or the battery controls itself."""
        return None

    async def async_set_power(
        self, hass: HomeAssistant, config: BatteryConfig, power_w: float
    ) -> None:
        """Charge (+) or discharge (-) at ``power_w``. Not used yet."""
        raise NotImplementedError

    async def async_release(self, hass: HomeAssistant, config: BatteryConfig) -> None:
        """Give control back to the battery / its own integration. Not used yet."""
        raise NotImplementedError


def device_entities(
    hass: HomeAssistant, config: BatteryConfig
) -> dict[tuple[str, str], str]:
    """(domain, translation key) -> entity id, for the battery's device.

    The device is the one of the battery's state of charge sensor.
    """
    registry = er.async_get(hass)
    soc = registry.async_get(config.soc_sensor) if config.soc_sensor else None
    if soc is None or soc.device_id is None:
        return {}
    return {
        (e.domain, e.translation_key or ""): e.entity_id
        for e in er.async_entries_for_device(registry, soc.device_id)
        if not e.disabled_by
    }


def platform_of(hass: HomeAssistant, config: BatteryConfig) -> str | None:
    """The integration that provides the battery's state of charge sensor."""
    entry = (
        er.async_get(hass).async_get(config.soc_sensor) if config.soc_sensor else None
    )
    return entry.platform if entry else None
