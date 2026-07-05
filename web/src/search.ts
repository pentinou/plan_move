import type { Dataset } from "./types";

const norm = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Recherche de commune par nom (insensible aux accents), 8 résultats max. */
export function buildSearch(ds: Dataset, onPick: (code: string) => void): void {
  const input = document.getElementById("recherche") as HTMLInputElement;
  const box = document.getElementById("recherche-resultats")!;
  const index = Object.entries(ds.communes).map(([code, c]) => ({
    code,
    normed: norm(c.n),
    nom: c.n,
    dept: c.d,
    pop: c.p ?? 0,
  }));

  function close() {
    box.hidden = true;
    box.innerHTML = "";
  }

  input.addEventListener("input", () => {
    const q = norm(input.value.trim());
    if (q.length < 2) return close();
    const starts = index.filter((e) => e.normed.startsWith(q));
    const contains = starts.length < 8 ? index.filter((e) => !e.normed.startsWith(q) && e.normed.includes(q)) : [];
    const results = [...starts.sort((a, b) => b.pop - a.pop), ...contains.sort((a, b) => b.pop - a.pop)].slice(0, 8);
    if (!results.length) return close();
    box.innerHTML = results
      .map((e) => `<button data-code="${e.code}">${e.nom} <small>(${e.dept})</small></button>`)
      .join("");
    box.hidden = false;
    box.querySelectorAll<HTMLButtonElement>("button").forEach((b) =>
      b.addEventListener("click", () => {
        onPick(b.dataset.code!);
        input.value = "";
        close();
      })
    );
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
    if (e.key === "Enter") box.querySelector<HTMLButtonElement>("button")?.click();
  });
}
