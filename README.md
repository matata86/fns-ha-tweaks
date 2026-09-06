# FNS HA Tweaks

Sdílený vzhled pro víc instancí Home Assistantu v jedné HACS integraci. Nainstaluješ, přidáš jeden řádek do `configuration.yaml`, restartuješ — a je to. Další verze se pak nabízí k aktualizaci přímo v HACS.

## Co integrace přinese

| Co | Kam si to sama nasadí |
|---|---|
| Motiv `fns_mushroom` — globální paleta pro light i dark, cirkadiánní podbarvení, vrstvy počasí a sluneční záře | `themes/fns-mushroom/fns-mushroom.yaml`, pak načte témata |
| UIX foundries `level_tile`, `mini_graph`, `threshold_tile` | `uix/fns_shared.yaml` a zaregistruje ho v integraci UIX |
| Karta sluneční linky (svítání a soumrak, fáze Měsíce, srážkové sloupce, popup) | při startu se sama aktualizuje, pokud už v dashboardu je; poprvé ji tam vloží služba `fns_shared.deploy_sun_card` |

Vlastní foundries instance zůstávají tam, kde byly (`uix/foundries.yaml`); integrace do nich nesahá, jen přidá druhý soubor vedle nich.

## Instalace

1. HACS → tři tečky → **Custom repositories** → `matata86/fns-ha-tweaks`, kategorie **Integration**.
2. **Download**.
3. Do `configuration.yaml` přidat řádek:

   ```yaml
   fns_shared:
   ```
4. Restart Home Assistantu.

Motiv se pak vybere v profilu uživatele (**Motiv → fns_mushroom**), foundries jsou hned k dispozici.

Kartu slunce vloží poprvé služba **Vývojářské nástroje → Akce → `fns_shared.deploy_sun_card`**. Od té chvíle ji každá nová verze integrace při startu aktualizuje sama — přepíše se jen ta jedna karta, zbytek dashboardu zůstává.

## Aktualizace

Nová verze se objeví v HACS jako u kterékoli jiné integrace. Po stažení a restartu se motiv i foundries přepíšou samy.

## Požadavky

- [UIX](https://uix.lf.technology) — kvůli foundries a stylům motivu
- Mushroom, browser_mod — karty a popup sluneční linky
