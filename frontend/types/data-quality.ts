export type DataQualityStatus = {
  symbol: string;
  timeframe: string;
  health_score: string | number;
  category: "EXCELLENT" | "GOOD" | "RISKY" | "UNRELIABLE" | string;
  trade_status: "CLEAN" | "DEGRADED" | "INVALID" | string;
  consistency_score: string | number;
  completeness_score: string | number;
  anomaly_inverse_score: string | number;
  latency_score: string | number;
  candles_evaluated: number;
  anomalies_found: number;
  missing_candles: number;
  feed_latency_ms: string | number;
  updated_at: string | null;
};

export type DataQualityScore = {
  symbol: string;
  timeframe: string;
  health_score: string | number;
  category: string;
  trade_status: string;
};

export type MarketDataAnomaly = {
  id: number;
  symbol: string;
  timeframe: string;
  timestamp: string;
  anomaly_type: string;
  severity: "INFO" | "WARNING" | "CRITICAL" | string;
  detection_method: string;
  observed_value: string | number | null;
  threshold_value: string | number | null;
  repair_action: string;
  detail: string;
  source: string;
  created_at: string;
};

export type MarketDataHealthLog = {
  id: number;
  symbol: string;
  timeframe: string;
  health_score: string | number;
  consistency_score: string | number;
  completeness_score: string | number;
  anomaly_inverse_score: string | number;
  latency_score: string | number;
  category: string;
  trade_status: string;
  candles_evaluated: number;
  anomalies_found: number;
  missing_candles: number;
  feed_latency_ms: string | number;
  created_at: string;
};

export type DataQualityReport = {
  id: number;
  symbol: string;
  timeframe: string;
  start_time: string;
  end_time: string;
  total_candles: number;
  valid_candles: number;
  anomalies_total: number;
  missing_candles: number;
  average_health_score: string | number;
  category: string;
  anomaly_breakdown: Record<string, number>;
  created_at: string;
};

export type RevalidateResult = {
  symbol: string;
  timeframe: string;
  total: number;
  valid: number;
  clean_emitted: number;
  anomalies: number;
  missing_candles: number;
  health_score: string | number;
  category: string;
  trade_status: string;
};
