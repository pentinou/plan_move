import type { Dataset } from "./types";

interface PrenomsData {
  annee: number;
  depts: Record<string, { filles: [string, number][]; garcons: [string, number][] }>;
}
/** code commune → métrique → [année, valeur][] */
type Series = Record<string, Record<string, [number, number][]>>;
/** code commune → [nom, maternelle, élémentaire, secteur, ips][] */
type EcolesListe = Record<string, [string, number, number, string, number | null][]>;

const seriesCache = new Map<string, Promise<Series>>();
const ecolesCache = new Map<string, Promise<EcolesListe>>();
let prenomsPromise: Promise<PrenomsData> | null = null;

const CONTEXTE: [string, string][] = [
  ["nb_ventes", "Ventes immobilières / an"],
  ["naissances", "Naissances / an"],
  ["deces", "Décès / an"],
  ["violences_1000hab", "Violences / 1000 hab"],
  ["vols_1000hab", "Vols / 1000 hab"],
  ["cambriolages_1000hab", "Cambriolages / 1000 hab"],
  ["nb_arrets_2km", "Arrêts TC à ≤2 km"],
];

function fetchJson<T>(url: string): Promise<T> {
  return fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  });
}

function getSeries(dept: string): Promise<Series> {
  if (!seriesCache.has(dept)) {
    seriesCache.set(dept, fetchJson<Series>(`data/series/${dept}.json`).catch(() => ({})));
  }
  return seriesCache.get(dept)!;
}

function getEcoles(dept: string): Promise<EcolesListe> {
  if (!ecolesCache.has(dept)) {
    ecolesCache.set(dept, fetchJson<EcolesListe>(`data/ecoles/${dept}.json`).catch(() => ({})));
  }
  return ecolesCache.get(dept)!;
}

function getPrenoms(): Promise<PrenomsData> {
  prenomsPromise ??= fetchJson<PrenomsData>("data/prenoms.json").catch(() => ({ annee: 0, depts: {} }));
  return prenomsPromise;
}

/** Mini-graphique d'évolution (SVG inline), point final mis en évidence. */
function sparkline(points: [number, number][]): string {
  if (points.length < 2) return "";
  const w = 90;
  const h = 22;
  const pad = 2;
  const ys = points.map((p) => p[1]);
  const xs = points.map((p) => p[0]);
  const [xmin, xmax] = [Math.min(...xs), Math.max(...xs)];
  const [ymin, ymax] = [Math.min(...ys), Math.max(...ys)];
  const sx = (x: number) => pad + ((x - xmin) / (xmax - xmin || 1)) * (w - 2 * pad);
  const sy = (y: number) => h - pad - ((y - ymin) / (ymax - ymin || 1)) * (h - 2 * pad);
  const pts = points.map((p) => `${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const first = points[0];
  const title = `${first[0]} : ${first[1].toLocaleString("fr-FR")} → ${last[0]} : ${last[1].toLocaleString("fr-FR")}`;
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">
    <title>${title}</title>
    <polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.3"/>
    <circle cx="${sx(last[0]).toFixed(1)}" cy="${sy(last[1]).toFixed(1)}" r="2" fill="currentColor"/>
  </svg>`;
}

function fmt(v: number | null, dec = 1): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("fr-FR", { maximumFractionDigits: dec });
}

export async function showFiche(code: string, ds: Dataset, onClose?: () => void): Promise<void> {
  const el = document.getElementById("fiche")!;
  const c = ds.communes[code];
  if (!c) return;
  el.hidden = false;
  el.innerHTML = `<p class="fiche-chargement">Chargement de ${c.n}…</p>`;

  const [series, ecoles, prenoms] = await Promise.all([
    getSeries(c.d),
    getEcoles(c.d),
    getPrenoms(),
  ]);
  const s = series[code] ?? {};

  const critRows = ds.metrics
    .map((m, j) => {
      const v = c.v[j];
      if (v === null) return "";
      const t = c.t[j];
      const pct = c.vp[j];
      return `<tr>
        <td>${m.label}<br><small>${m.unit}</small></td>
        <td class="num"><strong>${fmt(v, m.dec)}</strong>${pct === null ? "" : `<br><small>centile ${pct}</small>`}</td>
        <td class="num">${t === null ? "—" : (t > 0 ? "+" : "") + fmt(t) + " %/an"}</td>
        <td class="spark-cell">${sparkline(s[m.id] ?? [])}</td>
      </tr>`;
    })
    .join("");

  const ctxRows = CONTEXTE.map(([id, label]) => {
    const serie = s[id];
    if (!serie?.length) return "";
    const last = serie[serie.length - 1];
    return `<tr>
      <td>${label}</td>
      <td class="num"><strong>${fmt(last[1])}</strong> <small>(${last[0]})</small></td>
      <td class="spark-cell">${sparkline(serie)}</td>
    </tr>`;
  }).join("");

  const pren = prenoms.depts[c.d];
  const prenomsHtml = pren
    ? `<h3>Prénoms les plus donnés en ${prenoms.annee} <small>(département ${c.d})</small></h3>
       <div class="prenoms-cols">
         <ol>${pren.filles.map((p) => `<li>${p[0]}</li>`).join("")}</ol>
         <ol>${pren.garcons.map((p) => `<li>${p[0]}</li>`).join("")}</ol>
       </div>`
    : "";

  const liste = ecoles[code] ?? [];
  const ecolesHtml = liste.length
    ? `<h3>Écoles de la commune <small>(${liste.length})</small></h3>
       <ul class="liste-ecoles">${liste
         .slice(0, 20)
         .map(
           ([nom, mat, ele, secteur, ips]) => `<li>
             <span>${nom}</span>
             <span class="badges">
               ${mat ? '<span class="badge">Mat.</span>' : ""}
               ${ele ? '<span class="badge">Élém.</span>' : ""}
               ${secteur.startsWith("Pr") ? '<span class="badge badge-prive">Privé</span>' : ""}
               ${ips !== null ? `<span class="badge badge-ips" title="Indice de position sociale">IPS ${fmt(ips, 0)}</span>` : ""}
             </span>
           </li>`
         )
         .join("")}${liste.length > 20 ? `<li><em>… et ${liste.length - 20} autres</em></li>` : ""}</ul>`
    : `<h3>Écoles de la commune</h3><p><em>Aucune école maternelle/élémentaire dans la commune.</em></p>`;

  el.innerHTML = `
    <button id="fiche-close" aria-label="Fermer">×</button>
    <h2>${c.n} <span class="fiche-dept">(${c.d})</span></h2>
    <p class="fiche-pop">${c.p ? c.p.toLocaleString("fr-FR") + " habitants" : ""}</p>
    <table class="fiche-table">
      <thead><tr><th>Critère</th><th>Valeur</th><th>Tendance</th><th>Évolution</th></tr></thead>
      <tbody>${critRows || '<tr><td colspan="4"><em>Aucune donnée</em></td></tr>'}</tbody>
    </table>
    ${ctxRows ? `<h3>Contexte</h3><table class="fiche-table"><tbody>${ctxRows}</tbody></table>` : ""}
    ${ecolesHtml}
    ${prenomsHtml}`;
  document.getElementById("fiche-close")!.addEventListener("click", () => {
    el.hidden = true;
    onClose?.();
  });
}
