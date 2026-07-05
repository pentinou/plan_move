import type { AppState, CommuneData, Dataset } from "./types";

/** Score composite 0-100 d'une commune, ou null si exclue par un filtre
 * ou sans aucune donnée pour les critères pondérés (poids des critères
 * manquants redistribué sur les critères disponibles). */
export function scoreCommune(c: CommuneData, state: AppState): number | null {
  const pcts = state.mode === "niveau" ? c.vp : c.tp;
  let sum = 0;
  let wsum = 0;
  for (let j = 0; j < state.crits.length; j++) {
    const crit = state.crits[j];
    const raw = c.v[j];
    if (crit.min !== null && (raw === null || raw < crit.min)) return null;
    if (crit.max !== null && (raw === null || raw > crit.max)) return null;
    if (crit.weight === 0) continue;
    const p = pcts[j];
    if (p === null) continue;
    sum += crit.weight * (crit.dir === 1 ? p : 100 - p);
    wsum += crit.weight;
  }
  return wsum > 0 ? sum / wsum : null;
}

export function computeScores(ds: Dataset, state: AppState): Map<string, number | null> {
  const out = new Map<string, number | null>();
  for (const [code, c] of Object.entries(ds.communes)) {
    out.set(code, scoreCommune(c, state));
  }
  return out;
}
