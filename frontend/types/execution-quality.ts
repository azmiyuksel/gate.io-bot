export type ExecutionQualityStatus = {
  strategy_name: string;
  execution_quality_score: string | number;
  slippage_avg: string | number;
  slippage_std: string | number;
  latency_total_execution_ms: string | number;
  fill_completion_rate: string | number;
  partial_fill_ratio: string | number;
  quality_category: "Excellent" | "Good" | "Acceptable" | "Poor" | string;
  anomaly_status: "NORMAL" | "ANOMALOUS" | string;
  anomaly_reason: string;
};

export type ExecutionSlippageLog = {
  id: number;
  execution_order_id: number;
  slippage_pct: string | number;
  slippage_category: "GOOD" | "NORMAL" | "BAD" | "CRITICAL" | string;
  volatility_rolling: string | number;
  spread: string | number;
  created_at: string;
};

export type ExecutionLatencyLog = {
  id: number;
  execution_order_id: number;
  signal_to_submit_ms: number;
  submit_to_ack_ms: number;
  ack_to_fill_ms: number;
  total_execution_delay_ms: number;
  created_at: string;
};

export type ExecutionQualityRecommendation = {
  type: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "INFO" | string;
  message: string;
  action: string;
};

export type ExecutionReport = {
  id: number;
  strategy_name: string;
  start_time: string;
  end_time: string;
  total_orders: number;
  total_fills: number;
  average_slippage_pct: string | number;
  average_latency_ms: string | number;
  average_quality_score: string | number;
  sharpe_decay: string | number;
  slippage_cost_usd: string | number;
  report_data: {
    slippage_distribution?: {
      good: number;
      normal: number;
      bad: number;
      critical: number;
    };
    recommendations?: ExecutionQualityRecommendation[];
  };
  created_at: string;
};
