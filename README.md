# FNS HA Tweaks

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/matata86)

[![Open repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=matata86&repository=fns-ha-tweaks&category=integration)
[![Open server controls](https://my.home-assistant.io/badges/server_controls.svg)](https://my.home-assistant.io/redirect/server_controls/)

A shared look for several Home Assistant instances, packaged as one HACS integration (domain `fns_shared`). Install it, add one line to `configuration.yaml`, restart. New versions are then offered as updates directly in HACS.

## What it ships

On every Home Assistant start the integration deploys the files it carries into your config directory:

| What | Where it goes |
|---|---|
| Theme `fns_mushroom` — global palette for light and dark mode, circadian background tint, weather layers and a sun glow | `themes/fns-mushroom/fns-mushroom.yaml`; themes are reloaded only when the file changed |
| UIX foundries `level_tile`, `mini_graph`, `printer`, `threshold_tile` | `uix/fns_shared.yaml`, registered in the UIX integration's `foundry_files` option |
| Sun line card (dawn and dusk, sunrise and sunset, moon phase and moon band, precipitation bars, popup) | header of the default dashboard — inserted the first time by the `fns_shared.deploy_sun_card` service, then updated automatically on start |
| Visual editor for `custom:uix-forge` cards | frontend module `/fns_shared/fns_forge_editor.js`, loaded automatically |
| Cursor-following precipitation tooltip for the sun line card | frontend module `/fns_shared/fns_sun_line.js`, loaded automatically |

Your own foundries stay where they are (`uix/foundries.yaml`). The integration never touches that file; it only adds a second file next to it.

## Installation

1. HACS → three dots → **Custom repositories** → `matata86/fns-ha-tweaks`, category **Integration** (or use the "Open repository in HACS" button above).
2. **Download**.
3. Add this line to `configuration.yaml`:

   ```yaml
   fns_shared:
   ```

   There are no options; the integration has no config flow.
4. Restart Home Assistant (Developer tools → YAML → Restart, or the "Open server controls" button above).

Then pick the theme in your user profile (**Theme → fns_mushroom**). The foundries are available right away.

## Sun line card

The default dashboard is stored in Home Assistant's storage, not in a file, so the card is not added on its own. Call the service once:

**Developer tools → Actions → `fns_shared.deploy_sun_card`**

```yaml
action: fns_shared.deploy_sun_card
```

The service replaces an existing sun card, or inserts it into the header of the first view (or at the end of the first view's cards if there is no header). It requires the default dashboard to be in storage mode.

From then on every new version updates the card on startup by itself, but only if it is already on the dashboard and differs from the shipped one. Only that one card is rewritten; the rest of the dashboard stays as it is.

## uix-forge card editor

UIX does not ship an editor for `custom:uix-forge` cards, so Home Assistant only offers YAML. This integration adds one: the card editor shows a dropdown of foundries and below it a form whose fields are generated from the billets of the selected foundry — entity picker, icon picker, a list of Home Assistant colours and number fields, depending on the billet name and default value. An empty field means the default value from the foundry definition.

## Updating

A new version shows up in HACS like any other integration. **After downloading it, restart Home Assistant Core** — the files are deployed at startup, so the theme, foundries and sun card are refreshed on the next start.

## Requirements

- [UIX](https://uix.lf.technology) — foundries and theme styles
- [Mushroom](https://github.com/piitaya/lovelace-mushroom) and [browser_mod](https://github.com/thomasloven/hass-browser_mod) — sun line card and its popup
- [mini-graph-card](https://github.com/kalkih/mini-graph-card) — for the `mini_graph` foundry
- Lunar Phase (HACS) — moonrise, moonset and illumination for the sun line card; without it the moon band is simply not drawn

Some visual extras read optional entities and are skipped when they do not exist: `sensor.light_color` (circadian tint; falls back to sun elevation), a `weather.*` entity (weather tint and layers), `sensor.pocasi_predpoved_2h` (precipitation forecast for the sun line), `input_select.pocasi_vrstva` (manual weather layer selection), `sensor.moon_faze` (waxing/waning direction of the moon phase in the popup) and `binary_sensor.advent`.

---

## Support

Did this help you? A coffee for the author is always appreciated ☕

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/matata86)

**https://ko-fi.com/matata86**
