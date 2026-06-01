export type RegimeStatus = {
  id: number;
  symbol: string;
  timeframe: string;
  regime_type: string;
  confidence: string;
  rule_based_vote: string;
  clustering_vote: string;
  ml_vote: string;
  created_at: string;
};

export type RegimeTransition = {
  id: number;
  symbol: string;
  old_regime: string;
  new_regime: string;
  confidence: string;
  trigger_event: string;
  created_at: string;
};

export type RegimeConfidence = {
  id: number;
  symbol: string;
  timestamp: string;
  confidence_score: string;
  vote_weights: Record<string, number>;
};

export type RegimePerformance = {
  id: number;
  regime_type: string;
  strategy_name: string;
  total_trades: number;
  winning_trades: number;
  profit_factor: string;
  total_pnl: string;
  drawdown: string;
  updated_at: string;
};
