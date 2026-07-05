export interface MetricMeta {
  id: string;
  label: string;
  unit: string;
  dir: 1 | -1; // +1 : plus c'est haut, mieux c'est (sens par défaut, inversable dans l'UI)
  dec: number;
}

export interface CommuneData {
  n: string; // nom
  d: string; // département
  p: number | null; // population
  c: [number, number]; // centre [lon, lat]
  v: (number | null)[]; // niveau (valeur brute lissée), indexé comme metrics
  t: (number | null)[]; // tendance en %/an
  vp: (number | null)[]; // percentile 0-100 du niveau
  tp: (number | null)[]; // percentile 0-100 de la tendance
}

export interface Dataset {
  generated: string;
  metrics: MetricMeta[];
  communes: Record<string, CommuneData>;
}

export type Mode = "niveau" | "tendance";

export interface CritState {
  weight: number; // 0-5
  dir: 1 | -1; // sens courant (inversable)
  min: number | null; // filtre dur sur la valeur brute (niveau)
  max: number | null;
}

export interface AppState {
  mode: Mode;
  crits: CritState[];
}
