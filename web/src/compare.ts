import type { AppState, Dataset } from "./types";
import { fmt, getSeries } from "./fiche";

/** Couleur de contour sur la carte selon la position dans la sélection,
 * reprise en pastille dans l'en-tête de colonne du comparateur. */
export const SEL_COLORS = ["#c2185b", "#7b1fa2", "#00838f", "#ef6c00", "#5d4037"];

/** Lignes de contexte comparables : id de série → libellé, sens (+1 : plus c'est haut, mieux c'est). */
const CTX: [string, string, 1 | -1][] = [
  ["violences_1000hab", "Violences / 1000 hab", -1],
  ["vols_1000hab", "Vols / 1000 hab", -1],
  ["cambriolages_1000hab", "Cambriolages / 1000 hab", -1],
  ["nb_arrets_2km", "Arrêts TC à ≤2 km", 1],
];

/** Classe de cellule par commune : meilleure valeur en vert, moins bonne en
 * rouge, selon le sens du critère. Rien si égalité ou moins de deux valeurs. */
function cellClasses(vals: (number | null)[], dir: 1 | -1): string[] {
  const connus = vals.filter((v): v is number => v !== null && v !== undefined);
  if (connus.length < 2) return vals.map(() => "");
  const best = dir === 1 ? Math.max(...connus) : Math.min(...connus);
  const worst = dir === 1 ? Math.min(...connus) : Math.max(...connus);
  if (best === worst) return vals.map(() => "");
  return vals.map((v) =>
    v === null || v === undefined ? "" : v === best ? "cmp-best" : v === worst ? "cmp-worst" : ""
  );
}

function ligne(label: string, cells: string[], cls = ""): string {
  return `<tr${cls ? ` class="${cls}"` : ""}><td class="cmp-crit">${label}</td>${cells.join("")}</tr>`;
}

function cellules(vals: (number | null)[], dir: 1 | -1, rendu: (v: number, i: number) => string): string[] {
  const classes = cellClasses(vals, dir);
  return vals.map((v, i) =>
    `<td class="num ${classes[i]}">${v === null || v === undefined ? "—" : rendu(v, i)}</td>`
  );
}

/** Affiche le panneau de comparaison de 2+ communes dans #fiche : une colonne
 * par commune, lignes en vis-à-vis, meilleure/moins bonne valeur colorée. */
export async function showCompare(
  codes: string[],
  ds: Dataset,
  state: AppState,
  scores: Map<string, number | null>,
  onRemove: (code: string) => void,
  onClose: () => void
): Promise<void> {
  const el = document.getElementById("fiche")!;
  codes = codes.filter((k) => ds.communes[k]);
  const communes = codes.map((k) => ds.communes[k]);
  const token = String(Math.random());
  el.dataset.rendu = token;
  el.hidden = false;
  el.classList.add("compare");
  el.style.width = `${260 + 180 * codes.length}px`; // borné par le max-width CSS

  const parDept = await Promise.all(communes.map((c) => getSeries(c.d)));
  if (el.dataset.rendu !== token) return; // une autre fiche a pris la main pendant le chargement
  const series = codes.map((code, i) => parDept[i][code] ?? {});

  const enTetes = communes
    .map(
      (c, i) => `<th class="cmp-com">
        <button class="cmp-remove" data-code="${codes[i]}" title="Retirer ${c.n} de la comparaison">×</button>
        <span class="cmp-chip" style="background:${SEL_COLORS[i % SEL_COLORS.length]}"></span>
        <span class="cmp-nom">${c.n}</span> <span class="fiche-dept">(${c.d})</span>
        <div class="cmp-pop">${c.p ? c.p.toLocaleString("fr-FR") + " hab." : "&nbsp;"}</div>
      </th>`
    )
    .join("");

  const lignes: string[] = [];

  const vScores = codes.map((k) => scores.get(k) ?? null);
  lignes.push(
    ligne(
      `Score selon vos critères <br><small>/100</small>`,
      cellules(vScores, 1, (v) => `<strong>${fmt(v, 0)}</strong>`),
      "cmp-score"
    )
  );

  let theme = "";
  ds.metrics.forEach((m, j) => {
    const vals = communes.map((c) => c.v[j]);
    if (vals.every((v) => v === null || v === undefined)) return;
    if (m.theme && m.theme !== theme) {
      theme = m.theme;
      lignes.push(`<tr class="cmp-theme"><td colspan="${codes.length + 1}">${theme}</td></tr>`);
    }
    lignes.push(
      ligne(
        `${m.label}<br><small>${m.unit}</small>`,
        cellules(vals, state.crits[j].dir, (v, i) => {
          const pct = communes[i].vp[j];
          return `<strong>${fmt(v, m.dec)}</strong>${pct === null ? "" : `<br><small>centile ${pct}</small>`}`;
        })
      )
    );
  });

  const ctxLignes = CTX.map(([id, label, dir]) => {
    const derniers = series.map((s) => {
      const serie = s[id];
      return serie?.length ? serie[serie.length - 1] : null;
    });
    if (derniers.every((d) => d === null)) return "";
    const annees = derniers.filter((d) => d !== null).map((d) => d![0]);
    return ligne(
      `${label}<br><small>${Math.min(...annees) === Math.max(...annees) ? annees[0] : "dernière année connue"}</small>`,
      cellules(derniers.map((d) => (d ? d[1] : null)), dir, (v) => `<strong>${fmt(v)}</strong>`)
    );
  }).filter(Boolean);
  if (ctxLignes.length) {
    lignes.push(`<tr class="cmp-theme"><td colspan="${codes.length + 1}">Contexte</td></tr>`);
    lignes.push(...ctxLignes);
  }

  // largeurs figées : les colonnes des communes sont identiques, valeurs en vis-à-vis
  const largeurCommune = (64 / codes.length).toFixed(2);
  el.innerHTML = `
    <button id="fiche-close" aria-label="Fermer la comparaison">×</button>
    <h2>Comparaison</h2>
    <table class="cmp-table" style="min-width:${170 + 135 * codes.length}px">
      <colgroup>
        <col style="width:36%">
        ${codes.map(() => `<col style="width:${largeurCommune}%">`).join("")}
      </colgroup>
      <thead><tr><th class="cmp-crit"></th>${enTetes}</tr></thead>
      <tbody>${lignes.join("")}</tbody>
    </table>
    <p class="fiche-astuce">Maj+clic sur la carte : ajouter ou retirer une commune.
      <span class="cmp-legende"><span class="cmp-ex cmp-best">vert</span> meilleure valeur,
      <span class="cmp-ex cmp-worst">rouge</span> moins bonne, selon le sens de chaque critère.</span></p>`;

  document.getElementById("fiche-close")!.addEventListener("click", onClose);
  el.querySelectorAll<HTMLButtonElement>(".cmp-remove").forEach((btn) => {
    btn.addEventListener("click", () => onRemove(btn.dataset.code!));
  });
}
