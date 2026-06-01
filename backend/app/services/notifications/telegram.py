import httpx

from app.core.config import get_settings


class TelegramNotifier:
    async def send(self, message: str) -> None:
        settings = get_settings()
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"chat_id": settings.telegram_chat_id, "text": message, "parse_mode": "Markdown"})

    async def send_trade_opened(self, symbol: str, side: str, quantity: float, price: float) -> None:
        emoji = "\U0001f4c8" if side == "buy" else "\U0001f4c9"
        msg = (
            f"{emoji} *Paper Trade Açıldı*\n"
            f"Sembol: `{symbol}`\n"
            f"Yön: *{side.upper()}*\n"
            f"Miktar: `{quantity:.6f}`\n"
            f"Fiyat: `${price:,.2f}`"
        )
        await self.send(msg)

    async def send_trade_closed(self, symbol: str, pnl: float, reason: str) -> None:
        emoji = "\u2705" if pnl >= 0 else "\u274c"
        msg = (
            f"{emoji} *Paper Trade Kapandı*\n"
            f"Sembol: `{symbol}`\n"
            f"PnL: `${pnl:,.2f}`\n"
            f"Sebep: _{reason}_"
        )
        await self.send(msg)

    async def send_stop_loss_triggered(self, symbol: str, loss: float) -> None:
        msg = (
            f"\U0001f6d1 *Stop Loss Tetiklendi*\n"
            f"Sembol: `{symbol}`\n"
            f"Zarar: `${loss:,.2f}`"
        )
        await self.send(msg)

    async def send_daily_loss_limit(self, loss_pct: float) -> None:
        msg = (
            f"\u26a0\ufe0f *Günlük Zarar Limiti Aşıldı*\n"
            f"Günlük zarar: `%{loss_pct:.2f}`\n"
            f"Sistem duraklatıldı."
        )
        await self.send(msg)

    async def send_system_paused(self, reason: str) -> None:
        msg = f"\U0001f534 *Paper Trading Duraklatıldı*\nSebep: _{reason}_"
        await self.send(msg)

    async def send_daily_summary(self, metrics: dict) -> None:
        msg = (
            f"\U0001f4ca *Günlük Paper Trading Özeti*\n"
            f"Realized PnL: `${metrics.get('realized_pnl', 0):,.2f}`\n"
            f"Win Rate: `%{metrics.get('win_rate_rolling_100', 0) * 100:.1f}`\n"
            f"Sharpe: `{metrics.get('rolling_sharpe', 0):.2f}`\n"
            f"Drawdown: `%{abs(metrics.get('drawdown', 0)) * 100:.2f}`"
        )
        await self.send(msg)

    async def send_portfolio_rebalance(self, reason: str, old_weights: dict, new_weights: dict) -> None:
        old_str = ", ".join([f"{k}: {v:.1%}" for k, v in old_weights.items()])
        new_str = ", ".join([f"{k}: {v:.1%}" for k, v in new_weights.items()])
        msg = (
            f"🔄 *Portföy Yeniden Dengelendi*\n"
            f"Sebep: `{reason}`\n"
            f"Eski Ağırlıklar: `{old_str}`\n"
            f"Yeni Ağırlıklar: `{new_str}`"
        )
        await self.send(msg)

    async def send_portfolio_risk_limit(self, limit_type: str, value: float) -> None:
        msg = (
            f"⚠️ *Portföy Risk Sınırı Aşıldı*\n"
            f"Sınır Tipi: `{limit_type}`\n"
            f"Mevcut Değer: `{value:.2%}`\n"
            f"Sistem risk kontrolü devrede."
        )
        await self.send(msg)

    async def send_portfolio_correlation_warning(self, pairs_above_limit: list) -> None:
        pairs_str = "\n".join([f"• `{p[0]}` vs `{p[1]}`: {p[2]:.2f}" for p in pairs_above_limit])
        msg = (
            f"📊 *Yüksek Korelasyon Uyarısı*\n"
            f"Korelasyon sınırı (>0.8) aşan çiftler:\n"
            f"{pairs_str}"
        )
        await self.send(msg)

    async def send_portfolio_drawdown_warning(self, current_drawdown: float) -> None:
        msg = (
            f"📉 *Portföy Drawdown Uyarısı*\n"
            f"Mevcut Drawdown: `%{current_drawdown * 100:.2f}`\n"
            f"Lütfen risk limitlerinizi kontrol edin."
        )
        await self.send(msg)

    async def send_regime_transition(self, symbol: str, old_regime: str, new_regime: str, confidence: float) -> None:
        msg = (
            f"🔄 *Piyasa Rejimi Değişti*\n"
            f"Sembol: `{symbol}`\n"
            f"Eski Rejim: *{old_regime}*\n"
            f"Yeni Rejim: *{new_regime}*\n"
            f"Güven Skoru: `{confidence:.2%}`"
        )
        await self.send(msg)

    async def send_volatility_spike(self, symbol: str, atr_value: float) -> None:
        msg = (
            f"⚡ *Yüksek Volatilite Tespiti*\n"
            f"Sembol: `{symbol}`\n"
            f"ATR: `{atr_value:.6f}`\n"
            f"Risk limitleri daraltıldı (%50 exposure)."
        )
        await self.send(msg)

    async def send_regime_confidence_warning(self, symbol: str, score: float) -> None:
        msg = (
            f"⚠️ *Düşük Tahmin Güven Skoru*\n"
            f"Sembol: `{symbol}`\n"
            f"Güven Skoru: `{score:.2%}`\n"
            f"Yeni işlemler duraklatıldı."
        )
        await self.send(msg)

    async def send_strategy_degradation(self, strategy_name: str, drift_score: float, action: str) -> None:
        msg = (
            f"⚠️ *Strateji Bozulması Tespit Edildi*\n"
            f"Strateji: `{strategy_name}`\n"
            f"Drift Skoru: `{drift_score:.2f}`\n"
            f"Alınan Önlem: *{action}*"
        )
        await self.send(msg)

    async def send_strategy_paused(self, strategy_name: str, reason: str) -> None:
        msg = (
            f"🛑 *Strateji Durduruldu (PAUSED)*\n"
            f"Strateji: `{strategy_name}`\n"
            f"Sebep: `{reason}`\n"
            f"Tekrar aktif edilene kadar yeni işlemler engellendi."
        )
        await self.send(msg)

    async def send_strategy_risk_reduced(self, strategy_name: str, multiplier: float) -> None:
        msg = (
            f"📉 *Strateji Pozisyon Riski Düşürüldü*\n"
            f"Strateji: `{strategy_name}`\n"
            f"Yeni Risk Çarpanı: `{multiplier:.2f}x`"
        )
        await self.send(msg)

    async def send_strategy_recovered(self, strategy_name: str) -> None:
        msg = (
            f"✅ *Strateji Performansı Toparlandı*\n"
            f"Strateji: `{strategy_name}`\n"
            f"Normal risk ayarlarına geri dönüldü."
        )
        await self.send(msg)

    async def send_execution_slippage_warning(self, strategy_name: str, slippage_pct: float, category: str) -> None:
        msg = (
            f"⚠️ *Yüksek Fiyat Kayması (Slippage) Uyarısı*\n"
            f"Strateji: `{strategy_name}`\n"
            f"Fiyat Kayması: `%{slippage_pct * 100:.3f}`\n"
            f"Kategori: *{category}*"
        )
        await self.send(msg)

    async def send_execution_latency_spike(self, strategy_name: str, latency_ms: float) -> None:
        msg = (
            f"⚡ *Gecikme (Latency) Artışı Tespit Edildi*\n"
            f"Strateji: `{strategy_name}`\n"
            f"Gecikme Süresi: `{latency_ms:.1f} ms`"
        )
        await self.send(msg)

    async def send_execution_fill_rate_drop(self, strategy_name: str, fill_rate: float) -> None:
        msg = (
            f"📉 *Emir Gerçekleşme Oranı (Fill Rate) Düştü*\n"
            f"Strateji: `{strategy_name}`\n"
            f"Gerçekleşme Oranı: `%{fill_rate * 100:.1f}`"
        )
        await self.send(msg)




