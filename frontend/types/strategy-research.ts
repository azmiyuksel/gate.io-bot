export type ResearchStrategy = {
  id: number;
  name: string;
  template: string;
  status: "CANDIDATE" | "PROMOTED" | "REJECTED" | "ARCHIVED" | string;
  origin: string;
  family_id: number | null;
  best_fitness: string | number;
  best_version_id: number | null;
  parameters: Record<string, number>;
  created_at: string;
  updated_at: string;
};

export type StrategyVersion = {
  id: number;
  strategy_id: number;
  version: number;
  parameters: Record<string, number>;
  sharpe: string | number;
  profit_factor: string | number;
  max_drawdown: string | number;
  stability_score: string | number;
  consistency_score: string | number;
  fitness: string | number;
  overfit: boolean;
  total_trades: number;
  created_at: string;
};

export type ResearchExperiment = {
  id: number;
  experiment_type: string;
  status: string;
  strategy_id: number | null;
  symbol: string;
  timeframe: string;
  result: Record<string, unknown>;
  fitness: string | number;
  created_at: string;
  completed_at: string | null;
};

export type FeatureRecord = {
  id: number;
  name: string;
  category: string;
  symbol: string;
  timeframe: string;
  importance_score: string | number;
  correlation_with_profit: string | number;
  stability_score: string | number;
  updated_at: string;
};

export type HypothesisTest = {
  id: number;
  statement: string;
  feature: string;
  condition: string;
  status: "SUPPORTED" | "REJECTED" | "INCONCLUSIVE" | "UNTESTED" | string;
  supported: boolean;
  edge: string | number;
  p_value: string | number;
  sample_size: number;
  result: Record<string, unknown>;
  created_at: string;
};

export type ResearchRunResult = {
  evaluated: number;
  promoted: number;
  best_fitness: number;
  best_strategy_id: number | null;
  best_sharpe: number | null;
  reason: string | null;
  leaderboard: Array<{
    strategy_id: number;
    name: string;
    fitness: number;
    sharpe: number;
    overfit: boolean;
  }>;
};

export type PromotionResult = {
  strategy_id: number;
  decision: string;
  passed: boolean;
  reasons: string[];
};
