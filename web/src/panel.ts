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
  maire_politique: 0,
  medecins_10khab: 2,
  nb_creches: 1,
  dist_hopital: 2,
  note_hopital: 1,
  part_logements_sociaux: 0,
  equip_loisirs_10khab: 1,
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

/** Thèmes repliés par l'utilisateur — conservé entre deux re-rendus du panneau
 * (réinitialisation comprise), le temps de la session. */
const themesReplies = new Set<string>();

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

  let themeCourant = "";
  let themeBody: HTMLElement = critsEl;
  ds.metrics.forEach((m, j) => {
    if (m.theme && m.theme !== themeCourant) {
      themeCourant = m.theme;
      const theme = m.theme;
      const titre = document.createElement("button");
      titre.className = "theme-titre";
      const body = document.createElement("div");
      body.className = "theme-body";
      const applique = () => {
        const ouvert = !themesReplies.has(theme);
        body.hidden = !ouvert;
        titre.textContent = `${ouvert ? "▾" : "▸"} ${theme}`;
        titre.setAttribute("aria-expanded", String(ouvert));
      };
      titre.addEventListener("click", () => {
        themesReplies.has(theme) ? themesReplies.delete(theme) : themesReplies.add(theme);
        applique();
      });
      applique();
      critsEl.appendChild(titre);
      critsEl.appendChild(body);
      themeBody = body;
    }
    const crit = state.crits[j];
    const row = document.createElement("div");
    row.className = "crit";
    row.innerHTML = `
      <div class="crit-head">
        <span class="crit-label" title="${m.unit}">${m.label}</span>
        <button class="crit-info" aria-expanded="false"
                title="Qu'est-ce que ce critère et comment le lire ?">?</button>
        <button class="crit-dir"></button>
        <span class="crit-weight"></span>
      </div>
      <div class="crit-desc" hidden></div>
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
    themeBody.appendChild(row);

    const dirBtn = row.querySelector<HTMLButtonElement>(".crit-dir")!;
    const weightEl = row.querySelector<HTMLSpanElement>(".crit-weight")!;
    const slider = row.querySelector<HTMLInputElement>(".crit-slider")!;
    const infoBtn = row.querySelector<HTMLButtonElement>(".crit-info")!;
    const descEl = row.querySelector<HTMLDivElement>(".crit-desc")!;

    const refresh = () => {
      dirBtn.textContent = crit.dir === 1 ? "positif ↑" : "négatif ↓";
      dirBtn.title =
        crit.dir === 1
          ? "Critère positif : une valeur élevée améliore le score de la commune.\nCliquer pour inverser."
          : "Critère négatif : une valeur élevée dégrade le score de la commune.\nCliquer pour inverser.";
      dirBtn.classList.toggle("dir-negatif", crit.dir === -1);
      weightEl.textContent = crit.weight === 0 ? "ignoré" : `poids ${crit.weight}`;
      row.classList.toggle("inactive", crit.weight === 0 && crit.min === null && crit.max === null);
      const lectureCarte =
        crit.weight === 0
          ? "Poids à 0 : ce critère ne colore pas la carte (les filtres min/max restent actifs)."
          : crit.dir === 1
            ? "Sur la carte : une valeur élevée tire la commune vers le bleu, une valeur basse vers le rouge (combiné aux autres critères actifs — mettez les autres poids à 0 pour lire ce critère seul)."
            : "Sur la carte : une valeur basse tire la commune vers le bleu, une valeur élevée vers le rouge (combiné aux autres critères actifs — mettez les autres poids à 0 pour lire ce critère seul).";
      descEl.innerHTML = `${m.desc ?? ""}<br><em class="crit-desc-carte">${lectureCarte}</em>`;
    };
    refresh();

    infoBtn.addEventListener("click", () => {
      descEl.hidden = !descEl.hidden;
      infoBtn.setAttribute("aria-expanded", String(!descEl.hidden));
      infoBtn.classList.toggle("open", !descEl.hidden);
    });

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
  });
}
