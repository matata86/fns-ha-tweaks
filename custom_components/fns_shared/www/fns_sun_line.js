/*
 * FNS HA Tweaks — bublina sluneční linky, která sleduje kurzor.
 *
 * Samotná karta je poskládaná z vrstev pozadí, takže jednotlivé hodiny nejsou
 * prvky, na které by šlo najet myší, a CSS o poloze kurzoru neví. Tenhle modul
 * proto poslouchá pohyb myši nad linkou, spočítá si hodinu z vodorovné polohy
 * a ukáže, co je na ni v předpovědi.
 *
 * Klikání karty se nedotýká: posluchač visí na dokumentu a bublina má
 * pointer-events: none.
 */

const ZNACKA = "_moon_rise$";          // podle čeho poznáme kartu sluneční linky
const SENZOR = "sensor.pocasi_predpoved_2h";
const PRESAH = 14;                     // o kolik px nad a pod linku ještě reagovat

let bublina = null;
let posledni = null;

function* prochazej(koren) {
  const zasobnik = [koren];
  while (zasobnik.length) {
    const uzel = zasobnik.pop();
    if (!uzel) continue;
    yield uzel;
    if (uzel.shadowRoot) zasobnik.push(uzel.shadowRoot);
    for (const dite of uzel.children || []) zasobnik.push(dite);
  }
}

function najdiKarty() {
  const nalezene = [];
  for (const uzel of prochazej(document.body)) {
    if (!(uzel.tagName || "").includes("MUSHROOM-TEMPLATE-CARD")) continue;
    const config = uzel._config;
    if (config && JSON.stringify(config).includes(ZNACKA)) nalezene.push(uzel);
  }
  return nalezene;
}

function vytvorBublinu() {
  const prvek = document.createElement("div");
  prvek.style.cssText = [
    "position: fixed",
    "z-index: 9999",
    "pointer-events: none",
    "padding: 6px 10px",
    "border-radius: 10px",
    "font: 12px/1.45 var(--paper-font-body1_-_font-family, system-ui, sans-serif)",
    "white-space: nowrap",
    "color: var(--primary-text-color, #222)",
    "background: var(--card-background-color, #fff)",
    "border: 1px solid var(--divider-color, rgba(120,120,140,.3))",
    "box-shadow: 0 6px 18px rgba(0, 0, 0, .28)",
    "opacity: 0",
    "transition: opacity .12s ease",
  ].join(";");
  document.body.appendChild(prvek);
  return prvek;
}

/** Srážky v dané hodině dne. Datum se schválně ignoruje: linka kreslí 0–24 h, kdežto
 *  předpověď drží příštích 24 h, takže ranní hodiny na lince patří většinou už zítřku.
 *  Ze záznamů se stejnou hodinou se bere ten časově nejbližší. */
function srazkyVHodine(hass, hodina) {
  const zaznamy = hass?.states?.[SENZOR]?.attributes?.srazky_hodiny || [];
  const ted = Date.now();
  let nejlepsi = null;
  for (const zaznam of zaznamy) {
    const t = new Date(zaznam.t);
    if (t.getHours() !== hodina) continue;
    if (!nejlepsi || Math.abs(t - ted) < Math.abs(nejlepsi.t - ted)) {
      nejlepsi = { t, mm: Number(zaznam.mm) || 0, p: Number(zaznam.p) || 0 };
    }
  }
  return nejlepsi;
}

function dvojciferne(cislo) {
  return String(cislo).padStart(2, "0");
}

function popis(hass, hodina, minuta) {
  const srazky = srazkyVHodine(hass, hodina);
  const cas = `${hodina}:${dvojciferne(Math.floor(minuta / 10) * 10)}`;
  if (!srazky) return `${cas} — beze srážek`;
  const zitra = srazky.t.getDate() !== new Date().getDate() ? "zítra " : "";
  const mm = srazky.mm.toFixed(1).replace(".", ",");
  return `${zitra}${cas} — ${mm} mm, ${srazky.p} %`;
}

function ukaz(karta, udalost) {
  const karticka = karta.shadowRoot?.querySelector("ha-card");
  if (!karticka) return false;
  const rozmer = karticka.getBoundingClientRect();
  if (!rozmer.width) return false;
  const nadDolu = udalost.clientY >= rozmer.top - PRESAH && udalost.clientY <= rozmer.bottom + PRESAH;
  const uvnitr = udalost.clientX >= rozmer.left && udalost.clientX <= rozmer.right;
  if (!nadDolu || !uvnitr) return false;

  const podil = (udalost.clientX - rozmer.left) / rozmer.width;
  const minutyDne = Math.max(0, Math.min(1439, Math.round(podil * 1440)));
  const text = popis(karta.hass, Math.floor(minutyDne / 60), minutyDne % 60);

  if (!bublina) bublina = vytvorBublinu();
  if (text !== posledni) {
    bublina.textContent = text;
    posledni = text;
  }
  bublina.style.opacity = "1";
  // bublina se drží nad linkou; u pravého okraje se zarovná dovnitř
  const sirka = bublina.offsetWidth || 140;
  const x = Math.min(Math.max(udalost.clientX - sirka / 2, 8), window.innerWidth - sirka - 8);
  bublina.style.left = `${x}px`;
  bublina.style.top = `${Math.max(8, rozmer.top - bublina.offsetHeight - 10)}px`;
  return true;
}

function skryj() {
  if (bublina) bublina.style.opacity = "0";
}

let karty = [];
let posledniHledani = 0;

document.addEventListener("pointermove", (udalost) => {
  if (udalost.pointerType === "touch") return;      // na dotyku bublina nedává smysl
  const ted = performance.now();
  if (!karty.length || ted - posledniHledani > 3000) {
    karty = najdiKarty();                            // karta se po překreslení pohledu vymění
    posledniHledani = ted;
  }
  for (const karta of karty) {
    if (karta.isConnected && ukaz(karta, udalost)) return;
  }
  skryj();
}, { passive: true });

document.addEventListener("pointerdown", skryj, { passive: true });
window.addEventListener("blur", skryj);

// eslint-disable-next-line no-console
console.info("%c FNS HA Tweaks %c bublina sluneční linky ",
  "background:#4f5bd5;color:#fff;border-radius:4px 0 0 4px;padding:2px 6px",
  "background:#eef;color:#333;border-radius:0 4px 4px 0;padding:2px 6px");
