import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import "./style.css";
import { buildPanel, initialState } from "./panel";
import { computeScores } from "./scoring";
import { showFiche } from "./fiche";
import { buildSearch } from "./search";
import { applyHash, stateToHash } from "./permalink";
import type { Dataset } from "./types";

const COLOR_NA = "#d9d9d9";
// rampe RdYlBu (0 = mauvais, 100 = bon), lisible par les daltoniens
const SCORE_RAMP: [number, string][] = [
  [0, "#d7191c"],
  [25, "#fdae61"],
  [50, "#ffffbf"],
  [75, "#abd9e9"],
  [100, "#2c7bb6"],
];

async function init() {
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  const ds: Dataset = await fetch("data/metrics.json").then((r) => r.json());

  // points nommés pour les étiquettes (construits côté client, rien à exporter)
  const labelsGeojson = {
    type: "FeatureCollection" as const,
    features: Object.entries(ds.communes).map(([code, c]) => ({
      type: "Feature" as const,
      id: code,
      geometry: { type: "Point" as const, coordinates: c.c },
      properties: { nom: c.n, pop: c.p ?? 0 },
    })),
  };
  const baseUrl = location.href.replace(/[#?].*$/, "").replace(/[^/]*$/, "");

  const map = new maplibregl.Map({
    container: "map",
    center: [2.4, 46.6],
    zoom: 5.3,
    minZoom: 4,
    maxZoom: 13,
    attributionControl: false,
    style: {
      version: 8,
      glyphs: baseUrl + "fonts/{fontstack}/{range}.pbf",
      sources: {
        communes: {
          type: "vector",
          url: "pmtiles://" + new URL("data/communes.pmtiles", location.href).href,
          promoteId: "code",
        },
        departements: {
          type: "geojson",
          data: "data/departements.geojson",
        },
        labels: {
          type: "geojson",
          data: labelsGeojson,
        },
      },
      layers: [
        { id: "fond", type: "background", paint: { "background-color": "#f4f2ee" } },
        {
          id: "communes-fill",
          type: "fill",
          source: "communes",
          "source-layer": "communes",
          paint: {
            "fill-color": [
              "interpolate",
              ["linear"],
              ["coalesce", ["feature-state", "score"], -1],
              -1, COLOR_NA,
              ...SCORE_RAMP.flat(),
            ] as any,
            "fill-opacity": 0.9,
          },
        },
        {
          id: "communes-line",
          type: "line",
          source: "communes",
          "source-layer": "communes",
          minzoom: 8,
          paint: {
            "line-color": "#8a8a8a",
            "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.2, 12, 1] as any,
          },
        },
        {
          id: "commune-hover",
          type: "line",
          source: "communes",
          "source-layer": "communes",
          paint: {
            "line-color": "#222",
            "line-width": ["case", ["boolean", ["feature-state", "hover"], false], 2, 0] as any,
          },
        },
        {
          id: "departements-line",
          type: "line",
          source: "departements",
          paint: { "line-color": "#666", "line-width": 0.8 },
        },
        {
          id: "commune-selected",
          type: "line",
          source: "communes",
          "source-layer": "communes",
          paint: {
            "line-color": "#c2185b",
            "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 3.5, 0] as any,
          },
        },
        {
          id: "noms-communes",
          type: "symbol",
          source: "labels",
          layout: {
            "text-field": ["get", "nom"] as any,
            "text-font": ["Noto Sans Regular"],
            "text-size": ["interpolate", ["linear"], ["zoom"], 5, 10, 9, 12, 12, 14] as any,
            "symbol-sort-key": ["-", 0, ["get", "pop"]] as any,
            "text-padding": 4,
            "text-max-width": 8,
          },
          paint: {
            "text-color": "#37414b",
            "text-halo-color": "rgba(255,255,255,0.9)",
            "text-halo-width": 1.4,
          },
          // seuil de population décroissant avec le zoom, la collision fait le reste
          filter: [
            ">=",
            ["get", "pop"],
            ["step", ["zoom"], 80000, 6, 30000, 7, 15000, 8, 5000, 9, 1500, 10, 0],
          ] as any,
        },
      ],
    },
  });
  // réseaux routier et ferré (couches optionnelles, si le pipeline les a générées)
  map.once("load", async () => {
    const url = new URL("data/reseaux.pmtiles", location.href).href;
    // vérifie la signature du fichier : le serveur de dev renvoie index.html (200)
    // pour les fichiers absents, un simple test de statut ne suffit pas
    const head = await fetch(url, { headers: { Range: "bytes=0-6" } }).catch(() => null);
    if (!head?.ok || !(await head.text()).startsWith("PMTiles")) return;
    map.addSource("reseaux", { type: "vector", url: "pmtiles://" + url });
    map.addLayer(
      {
        id: "routes",
        type: "line",
        source: "reseaux",
        "source-layer": "routes",
        paint: {
          "line-color": ["match", ["get", "classe"], "autoroute", "#c62828", "#8d6e63"] as any,
          "line-width": [
            "interpolate", ["linear"], ["zoom"],
            5, ["match", ["get", "classe"], "autoroute", 1.2, 0.5] as any,
            11, ["match", ["get", "classe"], "autoroute", 3, 1.5] as any,
          ] as any,
          "line-opacity": 0.85,
        },
      },
      "commune-selected" // sous le surlignage et les étiquettes
    );
    map.addLayer(
      {
        id: "voies-ferrees",
        type: "line",
        source: "reseaux",
        "source-layer": "fer",
        paint: {
          "line-color": "#37474f",
          "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.6, 11, 1.6] as any,
          "line-dasharray": [3, 2],
        },
      },
      "commune-selected"
    );
    for (const id of ["routes", "voies-ferrees"]) {
      const cb = document.querySelector<HTMLInputElement>(`#affichage input[data-layer="${id}"]`);
      if (cb) map.setLayoutProperty(id, "visibility", cb.checked ? "visible" : "none");
    }
  });

  // cases à cocher d'affichage des couches
  const affichageEl = document.getElementById("affichage")!;
  affichageEl.innerHTML =
    `<div class="affichage-titre">Affichage</div>` +
    [
      ["noms-communes", "Noms des communes"],
      ["routes", "Routes principales"],
      ["voies-ferrees", "Voies ferrées"],
    ]
      .map(
        ([id, label]) =>
          `<label class="affichage-item"><input type="checkbox" data-layer="${id}" checked> ${label}</label>`
      )
      .join("");
  affichageEl.querySelectorAll<HTMLInputElement>("input").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = cb.dataset.layer!;
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", cb.checked ? "visible" : "none");
    });
  });

  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(
    new maplibregl.AttributionControl({
      compact: true,
      customAttribution: "Contours © IGN/Etalab — données publiques (Licence Ouverte)",
    })
  );

  const state = initialState(ds);
  applyHash(state);
  const scores = { current: computeScores(ds, state) };

  const alerteEl = document.getElementById("alerte-carte")!;
  function updateAlerte() {
    const allNull = [...scores.current.values()].every((s) => s === null);
    if (!allNull) {
      alerteEl.hidden = true;
      return;
    }
    const anyWeight = state.crits.some((c) => c.weight > 0);
    alerteEl.innerHTML = anyWeight
      ? `<b>Aucune commune n'est colorée.</b> Un filtre <b>min/max</b> exclut toutes les communes
         (souvent un filtre posé sur un critère peu renseigné, comme le taux de pauvreté).
         Videz les cases min/max concernées, ou cliquez sur <b>↺ Réinitialiser les critères</b>.`
      : `<b>Aucun critère actif.</b> Tous les poids sont à 0, il n'y a rien à évaluer.
         Montez le poids d'au moins un critère, ou cliquez sur <b>↺ Réinitialiser les critères</b>.`;
    alerteEl.hidden = false;
  }

  function applyScores() {
    for (const [code, score] of scores.current) {
      map.setFeatureState(
        { source: "communes", sourceLayer: "communes", id: code },
        { score: score === null ? null : Math.round(score * 10) / 10 }
      );
    }
    updateAlerte();
  }

  let pending = false;
  function refresh() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      scores.current = computeScores(ds, state);
      applyScores();
      history.replaceState(null, "", stateToHash(state));
    });
  }

  // commune sélectionnée (recherche ou clic) : contour surligné jusqu'à fermeture de la fiche
  let selected: string | null = null;
  function selectCommune(code: string | null) {
    if (selected !== null) {
      map.setFeatureState({ source: "communes", sourceLayer: "communes", id: selected }, { selected: false });
    }
    selected = code;
    if (code !== null) {
      map.setFeatureState({ source: "communes", sourceLayer: "communes", id: code }, { selected: true });
    }
  }
  function openCommune(code: string) {
    selectCommune(code);
    showFiche(code, ds, () => selectCommune(null));
  }

  buildPanel(ds, state, refresh);
  buildSearch(ds, (code) => {
    const c = ds.communes[code];
    // padding à droite : la fiche (360 px) ne doit pas masquer la commune
    map.flyTo({ center: c.c, zoom: 11.5, padding: { top: 0, bottom: 0, left: 0, right: 380 } });
    openCommune(code);
  });
  map.once("load", applyScores);
  map.on("idle", () => {
    (window as any).__mapIdle = true; // point d'accroche pour les tests visuels
  });
  (window as any).__map = map;

  // survol : contour + infobulle nom / score
  const popup = new maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    className: "hover-popup",
  });
  let hovered: string | number | null = null;
  map.on("mousemove", "communes-fill", (e) => {
    const f = e.features?.[0];
    if (!f || f.id === undefined) return;
    if (hovered !== null && hovered !== f.id) {
      map.setFeatureState({ source: "communes", sourceLayer: "communes", id: hovered }, { hover: false });
    }
    hovered = f.id;
    map.setFeatureState({ source: "communes", sourceLayer: "communes", id: f.id }, { hover: true });
    map.getCanvas().style.cursor = "pointer";
    const code = String(f.id);
    const c = ds.communes[code];
    const score = scores.current.get(code);
    popup
      .setLngLat(e.lngLat)
      .setHTML(
        `<strong>${c?.n ?? f.properties.nom}</strong> (${c?.d ?? ""})<br>` +
          (score === null || score === undefined
            ? "<em>hors filtres ou sans données</em>"
            : `score : <strong>${score.toFixed(0)}</strong>/100`)
      )
      .addTo(map);
  });
  map.on("mouseleave", "communes-fill", () => {
    if (hovered !== null) {
      map.setFeatureState({ source: "communes", sourceLayer: "communes", id: hovered }, { hover: false });
    }
    hovered = null;
    map.getCanvas().style.cursor = "";
    popup.remove();
  });

  map.on("click", "communes-fill", (e) => {
    const f = e.features?.[0];
    if (f?.id !== undefined) openCommune(String(f.id));
  });
}

init();
