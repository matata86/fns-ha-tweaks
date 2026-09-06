/*
 * FNS HA Tweaks — grafický editor karet `custom:uix-forge`.
 *
 * UIX ke svým kartám editor nedodává, takže HA nabízí jen YAML. Tenhle modul
 * doplní na třídu karty `getConfigElement()` a vykreslí formulář poskládaný
 * z billetů zvolené foundry (seznam se čte přes websocket `uix/get_foundries`).
 */

const CARD = "uix-forge";
const EDITOR = "fns-forge-editor";

const COLORS = [
  "primary", "accent", "red", "pink", "purple", "deep-purple", "indigo", "blue",
  "light-blue", "cyan", "teal", "green", "light-green", "lime", "yellow", "amber",
  "orange", "deep-orange", "brown", "grey", "blue-grey", "black", "white", "disabled",
];

const isNumeric = (value) =>
  typeof value === "number" ||
  (typeof value === "string" && value.trim() !== "" && !isNaN(Number(value)));

/** Odhadne typ pole podle názvu billetu a jeho výchozí hodnoty. */
function selectorFor(name, fallback) {
  const key = name.toLowerCase();
  if (key === "entity" || key.endsWith("_entity")) return { entity: {} };
  if (key === "icon" || key.endsWith("_icon")) return { icon: {} };
  if (typeof fallback === "boolean") return { boolean: {} };
  if (key.includes("color")) {
    return { select: { options: COLORS, mode: "dropdown", custom_value: true } };
  }
  if (isNumeric(fallback)) return { number: { mode: "box", step: "any" } };
  return { text: {} };
}

class FnsForgeEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._foundries = null;
    this._error = null;
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._foundries && !this._loading) this._loadFoundries();
    this._render();
  }

  async _loadFoundries() {
    this._loading = true;
    try {
      const res = await this._hass.connection.sendMessagePromise({ type: "uix/get_foundries" });
      this._foundries = res.foundries || {};
    } catch (err) {
      this._error = `Seznam foundries se nepodařilo načíst: ${err.message || err}`;
    }
    this._loading = false;
    this._render();
  }

  get _billets() {
    const foundry = this._foundries?.[this._config.foundry];
    return foundry?.forge?.billets || {};
  }

  _schema() {
    const names = Object.keys(this._foundries || {}).sort();
    const billets = this._billets;
    const fields = Object.keys(billets).map((name) => ({
      name,
      selector: selectorFor(name, billets[name]),
    }));
    return [
      { name: "foundry", required: true, selector: { select: { options: names, mode: "dropdown" } } },
      ...(fields.length ? [{ type: "expandable", name: "billety", title: "Hodnoty", expanded: true, schema: fields }] : []),
    ];
  }

  _data() {
    const billets = this._config.forge?.billets || {};
    const data = { foundry: this._config.foundry, billety: {} };
    for (const name of Object.keys(this._billets)) {
      const value = billets[name];
      data.billety[name] = value === null || value === undefined ? "" : value;
    }
    return data;
  }

  _valueChanged(ev) {
    ev.stopPropagation();
    const value = ev.detail.value;
    const config = { ...this._config, type: `custom:${CARD}`, foundry: value.foundry };
    const billets = {};
    for (const [name, raw] of Object.entries(value.billety || {})) {
      if (raw === "" || raw === null || raw === undefined) continue;
      billets[name] = raw;
    }
    config.forge = { ...(this._config.forge || {}), billets };
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true })
    );
    this._render();
  }

  _render() {
    if (!this._hass) return;
    if (!this._form) {
      const style = document.createElement("style");
      style.textContent = `
        .wrap { display: flex; flex-direction: column; gap: 12px; }
        .hint { color: var(--secondary-text-color); font-size: 12px; }
        .error { color: var(--error-color, #db4437); font-size: 13px; }
      `;
      const wrap = document.createElement("div");
      wrap.className = "wrap";
      this._hint = document.createElement("div");
      this._hint.className = "hint";
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => this._valueChanged(ev));
      this._form.computeLabel = (schema) =>
        ({ foundry: "Foundry", entity: "Entita", name: "Název", icon: "Ikona", color: "Barva" }[schema.name] ||
          schema.name);
      wrap.append(this._form, this._hint);
      this.shadowRoot.append(style, wrap);
    }
    if (this._error) {
      this._hint.className = "error";
      this._hint.textContent = this._error;
      return;
    }
    this._hint.textContent = this._foundries
      ? "Pole se generují z billetů zvolené foundry. Prázdné pole = výchozí hodnota z definice."
      : "Načítám foundries…";
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = this._data();
  }
}

if (!customElements.get(EDITOR)) customElements.define(EDITOR, FnsForgeEditor);

/** Doplní editor na třídu karty uix-forge, jakmile je zaregistrovaná. */
function patchCard() {
  const cls = customElements.get(CARD);
  if (!cls) return false;
  if (cls.__fnsEditorPatched) return true;
  cls.__fnsEditorPatched = true;
  cls.getConfigElement = async () => document.createElement(EDITOR);
  if (!cls.getStubConfig) {
    cls.getStubConfig = () => ({ foundry: "", forge: { billets: {} } });
  }
  // eslint-disable-next-line no-console
  console.info("%c FNS HA Tweaks %c editor karet uix-forge připojen ",
    "background:#4f5bd5;color:#fff;border-radius:4px 0 0 4px;padding:2px 6px",
    "background:#eef;color:#333;border-radius:0 4px 4px 0;padding:2px 6px");
  return true;
}

if (!patchCard()) {
  customElements.whenDefined(CARD).then(patchCard);
}
