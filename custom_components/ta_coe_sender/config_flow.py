"""Config Flow und Options Flow für TA CoE Sender."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ENTITY_ID, CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DECIMALS,
    CONF_INTERVAL,
    CONF_KIND,
    CONF_MAPPINGS,
    CONF_NODE,
    CONF_OUTPUT,
    CONF_UNIT,
    CONF_VERSION,
    DEFAULT_INTERVAL,
    DEFAULT_NODE,
    DOMAIN,
    KIND_ANALOG,
    KIND_DIGITAL,
    UNITS,
)
from .protocol import COE_V1, COE_V2, DEFAULT_PORTS, max_output


def _number(minimum: int, maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )


def _select(options: list[dict[str, str]]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


VERSION_OPTIONS = [
    {"value": COE_V1, "label": f"CoE V1 (UDP-Port {DEFAULT_PORTS[COE_V1]})"},
    {"value": COE_V2, "label": f"CoE V2 (UDP-Port {DEFAULT_PORTS[COE_V2]})"},
]
KIND_OPTIONS = [
    {"value": KIND_ANALOG, "label": "Analog (Zahlenwert)"},
    {"value": KIND_DIGITAL, "label": "Digital (Ein/Aus)"},
]
UNIT_OPTIONS = [{"value": key, "label": u["label"]} for key, u in UNITS.items()]


class CoESenderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung: Ziel-C.M.I. und eigener CAN-Knoten."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            node = int(user_input[CONF_NODE])
            if not host:
                errors[CONF_HOST] = "host_required"
            else:
                await self.async_set_unique_id(f"{host.lower()}_{node}")
                self._abort_if_unique_id_configured()
                data: dict[str, Any] = {
                    CONF_HOST: host,
                    CONF_VERSION: user_input[CONF_VERSION],
                    CONF_NODE: node,
                }
                if user_input.get(CONF_PORT):
                    data[CONF_PORT] = int(user_input[CONF_PORT])
                return self.async_create_entry(
                    title=f"C.M.I. {host} (Knoten {node})",
                    data=data,
                    options={CONF_MAPPINGS: [], CONF_INTERVAL: DEFAULT_INTERVAL},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_VERSION, default=COE_V1): _select(VERSION_OPTIONS),
                vol.Required(CONF_NODE, default=DEFAULT_NODE): _number(1, 62),
                vol.Optional(CONF_PORT): _number(1, 65535),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CoESenderOptionsFlow()


def _mapping_label(mapping: dict[str, Any]) -> str:
    if mapping[CONF_KIND] == KIND_DIGITAL:
        target = f"digital {mapping[CONF_OUTPUT]}"
    else:
        unit = UNITS.get(mapping.get(CONF_UNIT, ""), {}).get("label", "?")
        target = f"analog {mapping[CONF_OUTPUT]} ({unit})"
    return f"{mapping[CONF_ENTITY_ID]} → {target}"


class CoESenderOptionsFlow(OptionsFlow):
    """Werte zuordnen, entfernen und Sendeintervall ändern."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_mapping", "remove_mapping", "settings"],
        )

    async def async_step_add_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        mappings = list(self.config_entry.options.get(CONF_MAPPINGS, []))
        version = self.config_entry.data[CONF_VERSION]

        if user_input is not None:
            kind = user_input[CONF_KIND]
            output = int(user_input[CONF_OUTPUT])
            digital = kind == KIND_DIGITAL
            unit = user_input.get(CONF_UNIT)
            decimals = user_input.get(CONF_DECIMALS)

            if output > max_output(version, digital):
                errors[CONF_OUTPUT] = "output_out_of_range"
            elif any(
                m[CONF_KIND] == kind and int(m[CONF_OUTPUT]) == output for m in mappings
            ):
                errors[CONF_OUTPUT] = "duplicate_output"
            elif not digital and not unit:
                errors[CONF_UNIT] = "unit_required"
            else:
                mapping: dict[str, Any] = {
                    CONF_ENTITY_ID: user_input[CONF_ENTITY_ID],
                    CONF_KIND: kind,
                    CONF_OUTPUT: output,
                }
                if not digital:
                    if decimals in (None, ""):
                        decimals = UNITS[unit]["decimals"]
                    if decimals is None:
                        errors[CONF_DECIMALS] = "decimals_required"
                    else:
                        mapping[CONF_UNIT] = unit
                        mapping[CONF_DECIMALS] = int(decimals)
                if not errors:
                    mappings.append(mapping)
                    return self.async_create_entry(
                        data={**self.config_entry.options, CONF_MAPPINGS: mappings}
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
                vol.Required(CONF_KIND, default=KIND_ANALOG): _select(KIND_OPTIONS),
                vol.Required(CONF_OUTPUT, default=1): _number(1, 64),
                vol.Optional(CONF_UNIT): _select(UNIT_OPTIONS),
                vol.Optional(CONF_DECIMALS): _number(0, 4),
            }
        )
        return self.async_show_form(
            step_id="add_mapping",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_remove_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        mappings = list(self.config_entry.options.get(CONF_MAPPINGS, []))
        if not mappings:
            return self.async_abort(reason="no_mappings")

        if user_input is not None:
            remove = {int(i) for i in user_input["remove"]}
            kept = [m for i, m in enumerate(mappings) if i not in remove]
            return self.async_create_entry(
                data={**self.config_entry.options, CONF_MAPPINGS: kept}
            )

        options = [
            {"value": str(i), "label": _mapping_label(m)}
            for i, m in enumerate(mappings)
        ]
        schema = vol.Schema(
            {
                vol.Required("remove"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_mapping", data_schema=schema)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_INTERVAL: int(user_input[CONF_INTERVAL]),
                }
            )
        current = self.config_entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL)
        schema = vol.Schema(
            {vol.Required(CONF_INTERVAL, default=current): _number(5, 3600)}
        )
        return self.async_show_form(step_id="settings", data_schema=schema)
