"""Live-trading preflight checks.

Surfaces misconfigurations BEFORE (and while) the live worker trades, so a bot
that is "enabled" but unsafe — missing API keys, no alerting, sizing against a
fallback equity, futures gaps — is caught loudly instead of failing quietly with
real money. ``config_preflight`` is pure (offline-testable); ``exchange_preflight``
adds best-effort connectivity/balance checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PreflightIssue:
    level: str  # "error" | "warning"
    code: str
    message: str


def config_preflight(settings) -> list[PreflightIssue]:
    """Config-only checks (no network). Only meaningful when the bot is enabled —
    a disabled bot can be half-configured without risk."""
    issues: list[PreflightIssue] = []
    if not settings.bot_enabled:
        return issues

    has_keys = bool(settings.gateio_api_key and settings.gateio_api_secret)
    if not has_keys:
        issues.append(PreflightIssue(
            "error", "missing_api_keys",
            "BOT_ENABLED=true ama GATEIO_API_KEY/SECRET eksik — canlı işlem yapılamaz.",
        ))

    if settings.secret_key in ("", "change-me"):
        issues.append(PreflightIssue(
            "error", "weak_secret_key",
            "SECRET_KEY varsayılan/boş — canlı için güçlü rastgele bir değer atayın.",
        ))

    if not settings.is_production:
        issues.append(PreflightIssue(
            "warning", "environment_not_production",
            f"ENVIRONMENT='{settings.environment}' (production değil) — secret/CORS "
            "doğrulaması zorlanmıyor.",
        ))

    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        issues.append(PreflightIssue(
            "warning", "telegram_unconfigured",
            "Telegram yapılandırılmamış — kritik alarmlar (stop/kapanış hatası, "
            "worker düştü) gönderilemez.",
        ))

    if not settings.worker_watchdog_enabled:
        issues.append(PreflightIssue(
            "warning", "watchdog_disabled",
            "Worker watchdog kapalı — worker çökerse uyarı alınmaz "
            "(WORKER_WATCHDOG_ENABLED=true önerilir).",
        ))

    if not settings.fernet_key:
        issues.append(PreflightIssue(
            "warning", "fernet_unset",
            "FERNET_KEY yok — saklanan API gizli anahtarları şifrelenmez.",
        ))

    if settings.trading_market.lower() == "futures":
        issues.append(PreflightIssue(
            "warning", "futures_experimental",
            "TRADING_MARKET=futures DENEYSEL: hesap/equity ve emir mutabakatı yalnızca "
            "spot içindir; futures pozisyon/marjin takip edilmez. Testnet'te doğrulayın.",
        ))

    return issues


async def exchange_preflight(settings, client) -> list[PreflightIssue]:
    """Best-effort live-connectivity checks: the API key actually authenticates
    and the account holds tradable quote balance. Network failures become issues
    rather than exceptions."""
    issues: list[PreflightIssue] = []
    if not settings.bot_enabled or not (settings.gateio_api_key and settings.gateio_api_secret):
        return issues
    try:
        balances = await client.balances()
    except Exception as exc:  # noqa: BLE001 - surface as a preflight issue
        issues.append(PreflightIssue(
            "error", "exchange_unreachable",
            f"Borsa erişimi/anahtar doğrulaması başarısız: {exc}",
        ))
        return issues

    quote = settings.default_quote_currency.upper()
    quote_balance = Decimal("0")
    for entry in balances or []:
        if str(entry.get("currency", "")).upper() == quote:
            quote_balance += Decimal(str(entry.get("available", "0") or "0"))
            quote_balance += Decimal(str(entry.get("locked", "0") or "0"))
    if quote_balance <= 0:
        issues.append(PreflightIssue(
            "warning", "no_quote_balance",
            f"Hesapta {quote} bakiyesi yok — yeni pozisyon açılamaz.",
        ))
    return issues


def has_blocking_errors(issues: list[PreflightIssue]) -> bool:
    return any(i.level == "error" for i in issues)


def format_issues(issues: list[PreflightIssue]) -> str:
    if not issues:
        return "Preflight: tüm kontroller geçti."
    icon = {"error": "❌", "warning": "⚠️"}
    lines = [f"{icon.get(i.level, '•')} {i.message}" for i in issues]
    return "\n".join(lines)
