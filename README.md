# ha-shared

Sdílené části dvou instancí Home Assistantu — **HA Home** (192.168.1.10) a **HA Office** (Tailscale 100.98.189.65).
Změna se udělá jednou v tomto repozitáři a skript ji nasadí na obě instance.

## Co se sdílí

| Cesta v repozitáři | Co to je | Kam se nasazuje |
|---|---|---|
| `shared/theme/fns-mushroom.yaml` | motiv `fns_mushroom` — globální paleta (light/dark), cirkadiánní podbarvení, vrstvy počasí, sluneční záře | Home `/homeassistant/themes/fns-mushroom/fns-mushroom.yaml`, Office `/homeassistant/themes/fns_mushroom/fns_mushroom.yaml` |
| `shared/uix/foundries.shared.yaml` | UIX foundries `level_tile`, `mini_graph`, `threshold_tile` | slučuje se do `/homeassistant/uix/foundries.yaml` obou instancí |
| `shared/cards/sun_line.json` | karta sluneční linky v hlavičce Přehledu (svítání/soumrak, fáze Měsíce, srážkové sloupce, popup) | hlavička výchozího dashboardu obou instancí |
| `instances/<instance>/foundries.local.yaml` | foundries jen pro danou instanci (`alert_row`, `climate`, `room_heading`…) | slučuje se se sdílenými do `foundries.yaml` |

Soubor `foundries.yaml` na instanci je **generovaný** — needituj ho přes SSH ani v editoru,
změna se ztratí při příštím `push`. Edituj `shared/` nebo `instances/`.

## Přístupy

Skript čte hesla a tokeny z `~/.config/ha-sync.json`, který v repozitáři není.
Založ ho podle `secrets.example.json` (práva 600).

## Použití

```bash
python3 ha_sync.py status all       # co se liší proti živým instancím
python3 ha_sync.py diff office      # konkrétní rozdíl v tématu a foundries
python3 ha_sync.py pull home        # živý stav Home -> repozitář (po ruční úpravě na instanci)
python3 ha_sync.py push office      # repozitář -> Office
python3 ha_sync.py push all         # repozitář -> obě instance
```

`push` nahraje motiv a sloučené foundries přes SFTP, uloží kartu slunce do dashboardu
přes websocket a zavolá `uix/reload_foundry_files` + `frontend.reload_themes`.
Prohlížeč pak stačí načíst znovu, restart Core není potřeba.

## Obvyklý postup změny

1. `python3 ha_sync.py pull home` — sesbírá aktuální stav referenční instance.
2. Úprava souboru v `shared/`.
3. `python3 ha_sync.py push all`.
4. `git commit && git push`.

Karta slunce se v dashboardu hledá podle názvu popupu „Slunce a měsíc"; pokud ji někdo
přejmenuje, `push` ji přeskočí a napíše to do výstupu.
