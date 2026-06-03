# Gate.io Spot Sermaye Koruma Botu

Gate.io spot piyasası için **düşük riskli**, yavaş ve kontrollü çalışan bir alım-satım
sistemi. Amaç sermayeyi korumak ve denetlenebilir emir durumu tutmaktır — yüksek
frekanslı işlem (HFT) değildir.

> ⚠️ Bu bir mühendislik iskelesidir, yatırım tavsiyesi değildir. Gerçek parayla
> çalıştırmadan önce küçük sermaye ve tek sembolle test edin.

## Teknolojiler

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler
- **Borsa:** Gate.io REST API (HMAC imzalama, rate-limit, doğru spot market-emir
  semantiği: ALIM = quote tutarı / SATIM = base miktarı, IOC, precision & min-notional)
- **Frontend:** Next.js, TypeScript, TailwindCSS
- **Güvenlik:** JWT (access + iptal edilebilir refresh token), parola hash, RBAC,
  opsiyonel Fernet ile API anahtarı şifreleme
- **Bildirim:** Telegram (açılış/kapanış/stop-loss/günlük rapor)

## Strateji (V1)

- **Trend filtresi:** Sadece 200 EMA üzerinde long giriş
- **Giriş:** RSI(14) < 35, fiyat 20 EMA'ya yakın, aşırı 24s volatilite yok
- **Pozisyon boyutu:** İşlem başına sermayenin en fazla %1'i (notional)
- **Risk limitleri:** Günlük %2, haftalık %5 maks zarar, en fazla 3 açık pozisyon
- **Çıkış:** ATR stop-loss, en az 1:2 ödül/risk take-profit, trailing stop, manuel kapatma

Stratejiye ek canlı güvenlik katmanları: gerçek bakiye/equity takibi, emir mutabakatı
(reconciliation), global devre kesici (circuit breaker), piyasa-veri kalite kapısı,
stablecoin (USDT) depeg izleme ve drawdown derinleştikçe kademeli risk azaltma.

---

## Kurulum

Gereksinim: Docker + Docker Compose.

```bash
cp .env.example .env
# .env içindeki zorunlu alanları doldurun (aşağıya bakın)
docker compose up --build
```

Bu komut şu servisleri ayağa kaldırır: `postgres`, `redis`, `backend` (API),
`scheduler` (işlem döngüsü), `paper-worker` (kağıt-ticaret), `frontend` (panel).

- Panel: `http://localhost:3000`
- API: `http://localhost:8000`

### Zorunlu `.env` ayarları

| Değişken | Açıklama |
|----------|----------|
| `SECRET_KEY` | JWT imzalama anahtarı — güçlü ve benzersiz olmalı (üretimde "change-me" ile başlatma reddedilir) |
| `GATEIO_API_KEY` / `GATEIO_API_SECRET` | Gate.io API anahtarları (spot işlem izni) |
| `FERNET_KEY` | API sırlarını şifrelemek için (üret: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Bildirimler için (opsiyonel) |
| `TRADING_SYMBOLS` | İşlem yapılacak semboller, örn. `BTC_USDT,ETH_USDT` |

---

## Botu Aktif Hale Getirme (Adım Adım)

> Güvenlik açısından strateji **varsayılan olarak KAPALIDIR**. Bot, siz panelden
> stratejiyi açana kadar hiçbir işlem yapmaz.

**1. Servisleri başlatın**

```bash
docker compose up --build
```

**2. Admin kullanıcı oluşturun**

```bash
docker compose exec backend python app/scripts_create_admin.py \
  --email admin@example.com --password guclu-bir-parola
```

**3. Panele giriş yapın**

`http://localhost:3000` adresini açın, e-posta + parola ile giriş yapın. Oturum
kaydedilir ve access token otomatik yenilenir.

**4. Veritabanı tablolarının hazır olduğundan emin olun**

Yerel geliştirmede tablolar uygulama açılışında otomatik oluşturulur. Paylaşımlı/
üretim veritabanında migration kullanın:

```bash
docker compose exec backend alembic upgrade head
```

**5. Piyasa verisinin dolmasını bekleyin**

Strateji 200 EMA için **en az 210 mum** ister. `scheduler` her 15 dakikada bir
otomatik veri çeker; isterseniz hemen tetikleyin (admin token gerekir):

```bash
curl -X POST http://localhost:8000/api/v1/market-data/ingest \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

**6. Önce kağıt-ticaret (paper) ile test edin**

`paper-worker` servisi gerçek emir göndermeden stratejiyi simüle eder. Paneldeki
**Paper Trading** sayfasından başlatıp davranışı doğrulayın.

**7. Risk ayarlarını gözden geçirin**

Panelin ana sayfasında pozisyon boyutu, günlük/haftalık zarar limitleri ve maksimum
açık pozisyon sayısını kontrol edin. Küçük değerlerle başlayın.

**8. Stratejiyi ETKİNLEŞTİRİN (canlı işlem anahtarı)**

Canlı işlemin gerçek anahtarı veritabanındaki strateji durumudur (`is_enabled`).
Panelden açın ya da API ile:

```bash
curl -X PATCH http://localhost:8000/api/v1/dashboard/strategy \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"is_enabled": true}'
```

> Not: `.env` içindeki `BOT_ENABLED` yalnızca bir varsayılan bayraktır; **etkin
> kapı** yukarıdaki strateji durumudur.

**9. Devre kesicinin "armed" olduğundan emin olun**

```bash
curl http://localhost:8000/api/v1/circuit-breaker \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Tripli ise yeni işlem açılmaz; `POST /circuit-breaker/reset` ile sıfırlayın.

Bundan sonra `scheduler` her döngüde (15 dk) sembolleri tarar; tüm filtreler
(veri kalitesi, rejim, sağlık, risk, depeg, equity güveni) geçerse işlem açar.

### Botu durdurma

Stratejiyi kapatın (`{"is_enabled": false}`) veya devre kesiciyi tripleyin
(`POST /circuit-breaker/trip`). Her ikisi de yeni giriş açılmasını engeller;
açık pozisyonlar stop/TP yönetimiyle korunmaya devam eder.

---

## Otomatik güvenlik kapıları

Bir işlem açılmadan önce şu koşulların tümü sağlanmalıdır:

- Devre kesici tripli değil
- Strateji etkin (`is_enabled = true`)
- Equity güvenilir (borsa erişilebilir, snapshot bayat değil)
- Stablecoin (USDT) depeg yok
- Piyasa-veri kalitesi yeterli (INVALID veride duraklar, DEGRADED veride boyut yarılanır)
- Günlük/haftalık zarar limitleri ve maks açık pozisyon aşılmamış

---

## Geliştirme

```bash
cd backend
pip install -e '.[dev]'
ruff check app        # lint
pytest                # testler
```

- **Migration:** `alembic upgrade head` (uygula) · `alembic revision --autogenerate -m "..."` (model değişiminden sonra)
- **CI:** Her push/PR'da backend lint+test ve frontend tip-kontrollü build çalışır (`.github/workflows/ci.yml`).

## Gözlemlenebilirlik

- **Sağlık:** `GET /health` (canlılık), `GET /health/ready` (DB hazır mı)
- **Metrik:** `GET /metrics` (Prometheus)
- **Yapısal loglar:** her süreç JSON log üretir, istek bazında `correlation_id`
- **Denetim izi:** `GET /api/v1/dashboard/audit` (admin) — hassas işlemler kullanıcıya atfedilir
- **İşlem ekonomisi:** `GET /api/v1/dashboard/economics` — işlem başına beklenen değer,
  başabaş win-rate, gerçekleşen edge ve **al-tut'a (BTC) göre alfa**

## Dahili modüller (kısa)

- **Backtest** (`backend/app/backtest`): gerçekçi maker/taker maliyet modeli, lookahead-bias'sız
  doldurma, compounding Monte Carlo, al-tut benchmark, multiple-testing/deflated-Sharpe uyarısı
- **Walk-forward** (`backend/app/walkforward`): train/test embargo'lu pencereler, Optuna optimizasyonu, deployment kapısı
- **Piyasa-veri kalitesi** (`market_data_quality`): doğrulama, gap/spike/anomali tespiti, 0-100 sağlık skoru
- **Strateji Araştırma Lab'ı** (`strategy_research`): evrimsel strateji keşfi ve üretime terfi kapısı
- **Otomatik Öğrenme** (`auto_learning`): pattern madenciliği + aday strateji üretimi — **asla otomatik dağıtmaz**, insan onayı şart
- **Portföy** (`portfolio`): mean-variance / risk-parity tahsis, gerçek stress-test, VaR/CVaR
- **Execution kalitesi** (`execution_quality`): slippage, implementation shortfall, VWAP/TWAP, adverse-selection (TCA)

Detaylı API uç-noktaları için ilgili modüllerin kod ve şemalarına bakın; tüm uç-noktalar
tek bir `/api/v1` ön-eki altında sunulur.
