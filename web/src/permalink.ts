import type { AppState } from "./types";

/** Sérialise les réglages (mode, poids, sens, filtres) dans le hash de l'URL,
 * pour partager ou retrouver une configuration. */
export function stateToHash(state: AppState): string {
  const w = state.crits.map((c) => c.weight).join(",");
  const d = state.crits.map((c) => (c.dir === 1 ? "1" : "0")).join("");
  const f = state.crits.map((c) => `${c.min ?? ""}:${c.max ?? ""}`).join(",");
  const params = new URLSearchParams({ m: state.mode, w, d });
  if (/[^:,]/.test(f)) params.set("f", f);
  return "#" + params.toString();
}

export function applyHash(state: AppState): void {
  const h = new URLSearchParams(location.hash.slice(1));
  const m = h.get("m");
  if (m === "niveau" || m === "tendance") state.mode = m;
  const w = h.get("w")?.split(",");
  const d = h.get("d");
  const f = h.get("f")?.split(",");
  state.crits.forEach((crit, j) => {
    const wj = w?.[j] !== undefined ? Number(w[j]) : NaN;
    if (Number.isInteger(wj) && wj >= 0 && wj <= 5) crit.weight = wj;
    if (d?.[j] === "0") crit.dir = -1;
    else if (d?.[j] === "1") crit.dir = 1;
    if (f?.[j] !== undefined) {
      const [min, max] = f[j].split(":");
      crit.min = min === "" || min === undefined ? null : Number(min);
      crit.max = max === "" || max === undefined ? null : Number(max);
    }
  });
}
