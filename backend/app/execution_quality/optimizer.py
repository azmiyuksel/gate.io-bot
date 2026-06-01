from typing import Dict, List, Any


class AdaptiveExecutionOptimizer:
    @staticmethod
    def generate_recommendations(
        avg_slippage_pct: float,
        avg_latency_ms: float,
        rolling_volatility: float,
        partial_fill_ratio: float
    ) -> List[Dict[str, str]]:
        """
        Generates action-oriented optimization recommendations based on execution metrics:
        - Slippage: Switch to Limit orders if too high.
        - Latency: Warn if network lag is bottlenecking.
        - Volatility: Reduce position sizing if slippage risk is critical.
        """
        recommendations = []
        
        # 1. Slippage-based recommendations
        if avg_slippage_pct > 0.0020:  # > 0.2% slippage
            recommendations.append({
                "type": "ORDER_TYPE_OPTIMIZATION",
                "severity": "HIGH",
                "message": "Fiyat kayması (slippage) kritik seviyede. Market emirler yerine Limit emir kullanımına geçilmesi öneriliyor.",
                "action": "Switch to Limit Orders"
            })
        elif avg_slippage_pct > 0.0005:  # > 0.05% slippage
            recommendations.append({
                "type": "ORDER_TYPE_OPTIMIZATION",
                "severity": "MEDIUM",
                "message": "Fiyat kayması yükseliyor. Pasif limit emirleri veya takip eden emirler tercih edilebilir.",
                "action": "Prefer Limit Orders"
            })

        # 2. Latency-based recommendations
        if avg_latency_ms > 1500.0:  # > 1.5 seconds
            recommendations.append({
                "type": "LATENCY_OPTIMIZATION",
                "severity": "HIGH",
                "message": "Toplam işlem gecikmesi (latency) çok yüksek. Borsa API uç noktasını (endpoint) kontrol edin.",
                "action": "Change API Endpoint / Server Location"
            })
        elif avg_latency_ms > 600.0:
            recommendations.append({
                "type": "LATENCY_OPTIMIZATION",
                "severity": "MEDIUM",
                "message": "Ağ gecikmesi ideal sınırların üzerinde. Sunucu gecikmesini kontrol edin.",
                "action": "Optimize Network Routing"
            })

        # 3. Volatility-based recommendations
        if rolling_volatility > 0.03 and avg_slippage_pct > 0.0020:
            recommendations.append({
                "type": "RISK_OPTIMIZATION",
                "severity": "CRITICAL",
                "message": "Yüksek oynaklık (volatility) ve yüksek slippage bir arada tespit edildi. Emir büyüklükleri azaltılmalı.",
                "action": "Scale Down Position Quantity by 30-50%"
            })

        # 4. Partial fill-based recommendations
        if partial_fill_ratio > 0.3:
            recommendations.append({
                "type": "LIQUIDITY_OPTIMIZATION",
                "severity": "MEDIUM",
                "message": "Kısmi dolum oranı yüksek. Likiditesi daha yüksek işlem çiftleri seçilmeli veya emir bölme (order splitting) uygulanmalı.",
                "action": "Apply Order Splitting"
            })

        if not recommendations:
            recommendations.append({
                "type": "SYSTEM_HEALTHY",
                "severity": "INFO",
                "message": "İcra kalitesi en uygun seviyededir. Herhangi bir optimizasyon eylemi gerekmiyor.",
                "action": "Maintain Current Settings"
            })

        return recommendations
