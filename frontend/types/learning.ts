export type LearningStatus = {
  enabled: boolean;
  latest_cycle: {
    id: number;
    status: string;
    started_at: string;
    strategies_validated: number;
    promotion_requests: number;
  } | null;
  pending_approvals: number;
  knowledge: Record<string, number>;
  safety_invariants: string[];
};

export type LearningRunResult = {
  cycle_id: number;
  status: string;
  patterns_found: number;
  hypotheses_generated: number;
  features_discovered: number;
  strategies_evolved: number;
  strategies_validated: number;
  promotion_requests: number;
  safety_invariants_held: boolean;
};

export type KnowledgeEntry = {
  id: number;
  knowledge_type: string;
  title: string;
  description: string;
  symbol: string;
  regime: string | null;
  confidence: string | number;
  support: number;
  created_at: string;
};

export type DiscoveredFeature = {
  id: number;
  name: string;
  formula: string;
  symbol: string;
  timeframe: string;
  correlation_with_profit: string | number;
  importance_score: string | number;
  stability_score: string | number;
  created_at: string;
};

export type StrategyRanking = {
  id: number;
  strategy_id: number;
  version_id: number | null;
  score: string | number;
  robustness: string | number;
  walk_forward: string | number;
  stability: string | number;
  sharpe: string | number;
  drawdown: string | number;
  created_at: string;
};

export type PromotionRequest = {
  id: number;
  strategy_id: number;
  version_id: number | null;
  status: string;
  ranking_score: string | number;
  gate_passed: boolean;
  gate_reasons: string[];
  validation: Record<string, unknown>;
  requested_by: string;
  decided_by: string | null;
  decision_note: string | null;
  created_at: string;
  decided_at: string | null;
};

export type LearningHypothesis = {
  id: number;
  statement: string;
  feature: string;
  condition: string;
  status: string;
  supported: boolean;
  edge: string | number;
  p_value: string | number;
  sample_size: number;
  created_at: string;
};
