export type Provider = {
  id: number;
  name: string;
  specialty: string;
  location: string;
  encounters: number;
  observed: number;
  avg_cost: number;
  quality: number | null;
  rank: number | null;
  components: {
    outcome: number;
    cost: number;
    reliability: number;
    volume: number;
    completeness: number;
    shrinkage: number;
    residual: number;
    cost_ratio: number;
    status: string;
    version: string;
  };
};
export type Run = {
  id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  seconds: number | null;
  error: string | null;
};
export type Analytics = {
  providers: number;
  encounters: number;
  scored: number;
  mean_score: number | null;
  specialties: { name: string; count: number }[];
  distribution: { name: string; count: number }[];
  locations: string[];
  latest_run: Run | null;
  last_success: Run | null;
};
export type ProviderPage = {
  items: Provider[];
  total: number;
  page: number;
  page_size: number;
};
