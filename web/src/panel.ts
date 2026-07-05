import type { AppState, Dataset, Mode } from "./types";

/** Poids par défaut au premier chargement (id → poids 0-5). */
const DEFAULT_WEIGHTS: Record<string, number> = {
  prix_maison_m2: 3,
  prix_terrain_m2: 0,
  loyer_maison_m2: 0,
  loyer_appart_m2: 0,
  ventes_1000hab: 1,
  taxe_fonciere: 1,
  revenu_median: 1,
  taux_pauvrete: 1,
  delits_1000hab: 2,
  solde_naturel: 1,
  nb_ecoles: 2,
  ips_ecoles: 1,
  reussite_dnb: 2,
  reussite_bac: 1,
  va_college: 0,
  dist_arret_tc: 2,
};

export function initialState(ds: Dataset): AppState {
  return {
    mode: "niveau",
    crits: ds.metrics.map((m) => ({
      weight: DEFAULT_WEIGHTS[m.id] ?? 1,
      dir: m.dir,
      min: null,
      max: null,
    })),
  };
}

/** Remet mode, poids, sens et filtres aux valeurs par défaut (en mutant `state`). */
export function resetToDefaults(ds: Dataset, state: AppState): void {
  state.mode = "niveau";
  ds.metrics.forEach((m, j) => {
    state.crits[j].weight = DEFAULT_WEIGHTS[m.id] ?? 1;
    state.crits[j].dir = m.dir;
    state.crits[j].min = null;
    state.crits[j].max = null;
  });
}

/** Construit le panneau (toggle de mode + une carte par critère) et appelle
 * `onChange` à chaque modification. Mute `state` en place. */
export function buildPanel(ds: Dataset, state: AppState, onChange: () => void): void {
  const modeEl = document.getElementById("mode-toggle")!;
  modeEl.innerHTML = `
    <div class="mode-switch" role="radiogroup" aria-label="Mode de coloration">
      <button data-mode="niveau" class="${state.mode === "niveau" ? "active" : ""}">Niveau actuel</button>
      <button data-mode="tendance" class="${state.mode === "tendance" ? "active" : ""}">Tendance 5 ans</button>
    </div>`;
  modeEl.querySelectorAll<HTMLButtonElement>("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.mode = btn.dataset.mode as Mode;
      modeEl.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b === btn));
      onChange();
    });
  });

  const critsEl = document.getElementById("criteres")!;
  critsEl.innerHTML = "";

  const resetRow = document.createElement("div");
  resetRow.className = "reset-row";
  resetRow.innerHTML =
    `<button id="reset-btn" title="Remettre poids, sens et filtres par défaut">↺ Réinitialiser les critères</button>`;
  resetRow.querySelector("button")!.addEventListener("click", () => {
    resetToDefaults(ds, state);
    buildPanel(ds, state, onChange); // re-render tous les contrôles avec les valeurs par défaut
    onChange();
  });
  critsEl.appendChild(resetRow);

  ds.metrics.forEach((m, j) => {
    const crit = state.crits[j];
    const row = document.createElement("div");
    row.className = "crit";
    row.innerHTML = `
      <div class="crit-head">
        <span class="crit-label" title="${m.unit}">${m.label}</span>
        <button class="crit-dir"></button>
        <span class="crit-weight"></span>
      </div>
      <label class="crit-poids" title="Poids du critère dans le score : 0 = ignoré, 5 = très important">
        Poids
        <input type="range" class="crit-slider" min="0" max="5" step="1" value="${crit.weight}"
               aria-label="Poids de ${m.label}">
      </label>
      <div class="crit-filter">
        <input type="number" class="crit-min" placeholder="min" value="${crit.min ?? ""}"
               aria-label="Filtre min ${m.label}">
        <span class="crit-unit">${m.unit}</span>
        <input type="number" class="crit-max" placeholder="max" value="${crit.max ?? ""}"
               aria-label="Filtre max ${m.label}">
      </div>`;

    const dirBtn = row.querySelector<HTMLButtonElement>(".crit-dir")!;
    const weightEl = row.querySelector<HTMLSpanElement>(".crit-weight")!;
    const slider = row.querySelector<HTMLInputElement>(".crit-slider")!;

    const refresh = () => {
      dirBtn.textContent = crit.dir === 1 ? "positif ↑" : "négatif ↓";
      dirBtn.title =
        crit.dir === 1
          ? "Critère positif : une valeur élevée améliore le score de la commune.\nCliquer pour inverser."
          : "Critère négatif : une valeur élevée dégrade le score de la commune.\nCliquer pour inverser.";
      dirBtn.classList.toggle("dir-negatif", crit.dir === -1);
      weightEl.textContent = crit.weight === 0 ? "ignoré" : `poids ${crit.weight}`;
      row.classList.toggle("inactive", crit.weight === 0 && crit.min === null && crit.max === null);
    };
    refresh();

    slider.addEventListener("input", () => {
      crit.weight = Number(slider.value);
      refresh();
      onChange();
    });
    dirBtn.addEventListener("click", () => {
      crit.dir = crit.dir === 1 ? -1 : 1;
      refresh();
      onChange();
    });
    row.querySelector<HTMLInputElement>(".crit-min")!.addEventListener("change", (e) => {
      const v = (e.target as HTMLInputElement).value;
      crit.min = v === "" ? null : Number(v);
      refresh();
      onChange();
    });
    row.querySelector<HTMLInputElement>(".crit-max")!.addEventListener("change", (e) => {
      const v = (e.target as HTMLInputElement).value;
      crit.max = v === "" ? null : Number(v);
      refresh();
      onChange();
    });

    critsEl.appendChild(row);
  });
}
