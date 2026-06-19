# Gate.io Spot Sermaye Koruma Botu

Gate.io spot piyasası için **düşük riskli**, yavaş ve kontrollü çalışan bir alım-satım
sistemi. Amaç sermayeyi korumak ve denetlenebilir emir durumu tutmaktır — yüksek
frekanslı işlem (HFT) değildir.

> ⚠️ Bu bir mühendislik iskelesidir, yatırım tavsiyesi değildir. Gerçek parayla
> çalıştırmadan önce küçük sermaye ve tek sembolle test edin.

### Hızlı Başlangıç

```bash
git clone https://github.com/azmiyuksel/gate.io-bot.git
cd gate.io-bot
cp .env.example .env
# .env dosyasını doldurun
start.bat   # Windows'ta menü açılır, [1] Paper veya [2] Live seçin
```

## Teknolojiler

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler
- **Borsa:** Gate.io REST API (HMAC imzalama, rate-limit, doğru spot market-emir
  semantiği: ALIM = quote tutarı / SATIM = base miktarı, IOC, precision & min-notional)
- **Frontend:** Next.js, TypeScript, TailwindCSS
- **Güvenlik:** JWT (access + iptal edilebilir refresh token), parola hash, RBAC,
  opsiyonel Fernet ile API anahtarı şifreleme
- **Bildirim:** Telegram (açılış/kapanış/stop-loss/günlük rapor)

## Stratejiler

Sistem iki strateji içerir; hangisinin canlı/paper'da çalışacağı `LIVE_STRATEGY`
ve `PAPER_STRATEGY` ile seçilir.

### `momentum_breakout_v1` — **varsayılan** (canlı + paper)

Sık işlem yapan, simetrik (long + short) momentum/breakout stratejisi. Hızlı
zaman çerçevesi için tasarlandı (paper 5m). EMA trend + Donchian kırılımı +
hacim genişlemesi ile girer, ATR stop + trailing ile çıkar (sabit take-profit
yok — kazananların koşmasına izin verir). Kırılım buffer'ı, gerçek fee/spread
maliyetinin altında tetiklenmeyecek şekilde tabanlanır.

> ⚙️ Bu strateji hızlı timeframe içindir. Canlıda timeframe ile uyumlu taramak
> için `LIVE_ENTRY_INTERVAL_MINUTES` değerini düşürün (ör. 5) — varsayılan 15.

### `capital_preservation_v1` — düşük riskli alternatif

- **Trend filtresi:** Sadece 200 EMA üzerinde long giriş
- **Giriş:** RSI(14) < 35, fiyat 20 EMA'ya yakın, aşırı 24s volatilite yok
- **Pozisyon boyutu:** İşlem başına sermayenin en fazla %1'i (notional)
- **Risk limitleri:** Günlük %2, haftalık %5 maks zarar, en fazla 3 açık pozisyon
- **Çıkış:** ATR stop-loss, en az 1:1.5 ödül/risk take-profit, trailing stop, manuel kapatma

Stratejiye ek canlı güvenlik katmanları: gerçek bakiye/equity takibi, emir mutabakatı
(reconciliation), global devre kesici (circuit breaker), piyasa-veri kalite kapısı,
stablecoin (USDT) depeg izleme ve drawdown derinleştikçe kademeli risk azaltma.

---

## Kurulum

Gereksinim: Docker + Docker Compose.

### Tek tıkla başlatma (önerilen)

`start.bat` dosyasına çift tıklayın — menüden mod seçin:

```
[1] Paper Trading  — Simülasyon, risksiz
[2] Live Trading   — Gerçek para, onay ekranı var
[3] Full Dev Mode  — Tüm servisler
[4] Durdur         — Servisleri indirir
[5] Log Goster     — Canlı loglar
[6] Cikis
```

### Manuel komutlar

```bash
cp .env.example .env
# .env içindeki zorunlu alanları doldurun (aşağıya bakın)

docker compose --profile paper up -d --build   # Paper trading
docker compose --profile live up -d --build    # Live trading
docker compose --profile paper --profile live up -d --build  # Her ikisi
```

### Profil yapısı

| Mod | Servisler |
|-----|-----------|
| **Paper** | postgres, redis, backend, frontend, paper-worker |
| **Live** | postgres, redis, backend, frontend, scheduler |
| **Full Dev** | Tümü (paper + live birlikte) |

Panel: `http://localhost:3000` · API: `http://localhost:8000`

### Zorunlu `.env` ayarları

| Değişken | Açıklama |
|----------|----------|
| `SECRET_KEY` | JWT imzalama anahtarı — güçlü ve benzersiz olmalı (üretimde "change-me" ile başlatma reddedilir) |
| `GATEIO_API_KEY` / `GATEIO_API_SECRET` | Gate.io API anahtarları (spot işlem izni) |
| `FERNET_KEY` | API sırlarını şifrelemek için (üret: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Bildirimler için (opsiyonel) |
| `TRADING_SYMBOLS` | İşlem yapılacak semboller, örn. `BTC_USDT,ETH_USDT` |

### Docker'sız (yerel geliştirme) çalıştırma

Docker kullanmadan elle çalıştırmak için gereksinimler: **Python 3.12**, **Node 22**,
ve çalışan bir **PostgreSQL** + **Redis** (yerelde kurulu ya da yalnızca bu ikisini
Docker'la başlatabilirsiniz: `docker compose up -d postgres redis`).

`.env`'de host adlarını yerelde çalışacak şekilde güncelleyin:

```bash
DATABASE_URL=postgresql+psycopg://gatebot:gatebot@localhost:5432/gatebot
REDIS_URL=redis://localhost:6379/0
```

**Backend (API) — terminal 1:**

```bash
cd backend
pip install -e .                 # bağımlılıklar (Python 3.12)
alembic upgrade head             # tabloları oluştur (ya da uygulama açılışta oluşturur)
uvicorn app.main:app --reload --port 8000
```

**Scheduler (işlem döngüsü) — terminal 2:**

```bash
cd backend
python -m app.workers.scheduler
```

**Paper worker (kağıt-ticaret) — terminal 3 (opsiyonel):**

```bash
cd backend
python -m app.workers.paper_worker
```

**Frontend (panel) — terminal 4:**

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run dev
```

Admin kullanıcıyı yerelde şu şekilde oluşturun:

```bash
cd backend
python app/scripts_create_admin.py --email admin@example.com --password guclu-bir-parola
```

Panel yine `http://localhost:3000`, API `http://localhost:8000` üzerinden erişilir.
Bundan sonra aşağıdaki "Botu Aktif Hale Getirme" adımlarını izleyin.

---

## Botu Aktif Hale Getirme (Adım Adım)

> Güvenlik açısından strateji **varsayılan olarak KAPALIDIR**. Bot, siz panelden
> stratejiyi açana kadar hiçbir işlem yapmaz.

**1. Servisleri başlatın**

```bash
# Canlı işlem için:
docker compose --profile live up -d --build

# Ya da start.bat ile:
# [2] Live Trading seçin
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

**8. Stratejiyi ETKİNLEŞTİRİN — iki anahtar birden gerekir**

Canlı işlem açılması için **HEM** `.env`'deki master anahtar **HEM** veritabanındaki
strateji anahtarı açık olmalıdır. İkisinden biri kapalıysa yeni işlem açılmaz
(açık pozisyonlar yine de stop/TP ile yönetilmeye devam eder).

1. `.env` içinde master anahtarı açın ve `backend` + `scheduler` servislerini yeniden başlatın:

   ```bash
   # .env
   BOT_ENABLED=true
   ```
   ```bash
   docker compose --profile live up -d --force-recreate backend scheduler
   ```

2. Strateji anahtarını panelden açın ya da API ile:

   ```bash
   curl -X PATCH http://localhost:8000/api/v1/dashboard/strategy \
     -H "Authorization: Bearer <ACCESS_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"is_enabled": true}'
   ```

**9. Devre kesicinin "armed" olduğundan emin olun**

```bash
curl http://localhost:8000/api/v1/circuit-breaker \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Tripli ise yeni işlem açılmaz; `POST /circuit-breaker/reset` ile sıfırlayın.

Bundan sonra `scheduler` her döngüde (15 dk) sembolleri tarar; tüm filtreler
(veri kalitesi, rejim, sağlık, risk, depeg, equity güveni) geçerse işlem açar.

### Botu durdurma

Stratejiyi kapatın (`{"is_enabled": false}`) veya `.env`'de `BOT_ENABLED=false`
yapın ya da devre kesiciyi tripleyin (`POST /circuit-breaker/trip`). Üçü de yeni
giriş açılmasını engeller; açık pozisyonlar stop/TP yönetimiyle korunmaya devam eder.

---

## Test hesabı ile kullanım (önerilen ilk adım)

Gerçek para riske atmadan stratejiyi denemenin iki yolu var:

**A) Kağıt-ticaret (paper) — gerçek emir yok, simülasyon.** En güvenli yöntem.

1. `.env`'de `BOT_ENABLED=false` bırakın (canlı işlem kapalı).
2. `start.bat` ile **[1] Paper Trading** seçin ya da:
   ```bash
   docker compose --profile paper up -d --build
   ```
3. Panelde **Paper Trading** sayfasından başlatın. Bot gerçek piyasa verisiyle
   sinyalleri simüle eder, emirleri sanal hesapta doldurur ve PnL/metilkleri gösterir.
4. Davranıştan memnun olana kadar burada kalın — gerçek bakiye etkilenmez.

**B) Gate.io testnet API anahtarlarıyla dry-run (opsiyonel, ileri seviye).**

1. Gate.io testnet'ten test API anahtarı alın.
2. `.env`'de borsa adresini testnet'e ve anahtarları testnet anahtarlarınıza çevirin:
   ```bash
   GATEIO_BASE_URL=<gate.io testnet REST adresi>
   GATEIO_WS_URL=<gate.io testnet WS adresi>
   GATEIO_API_KEY=<testnet key>
   GATEIO_API_SECRET=<testnet secret>
   ```
3. "Botu Aktif Hale Getirme" adımlarını izleyin (testnet bakiyesi gerçek değildir).

> Testnet adreslerini Gate.io'nun güncel dokümantasyonundan doğrulayın. Spot
> testnet sunulmuyorsa **(A) kağıt-ticaret** yöntemini kullanın.

## Gerçek hesap ile kullanım

> 💸 Bu mod **gerçek para** ile işlem açar. Önce mutlaka kağıt-ticaret ile test edin.

1. **Gate.io API anahtarı** oluşturun — yalnızca **spot işlem** izni verin;
   **çekim (withdraw) iznini kapalı** tutun. Mümkünse IP kısıtlaması ekleyin.
2. `.env`'i doldurun: gerçek `GATEIO_API_KEY`/`GATEIO_API_SECRET`, güçlü `SECRET_KEY`,
   `FERNET_KEY`, `TRADING_SYMBOLS` ve (opsiyonel) Telegram bilgileri.
   `GATEIO_BASE_URL`/`GATEIO_WS_URL`'i Gate.io canlı (mainnet) adreslerinde bırakın.
3. Servisleri başlatın (`start.bat` ile **[2] Live Trading** ya da
   `docker compose --profile live up -d --build`), admin oluşturun, panele girin.
4. **Küçük başlayın:** tek sembol ve düşük `max_capital_per_trade_pct` ile.
   İsteğe bağlı: aşırı dar `STRATEGY_MAX_24H_RANGE_PCT` değerini sembole göre ayarlayın.
5. Önce strateji **kapalıyken** birkaç döngü gözlemleyin (loglar + panel) — veri
   çekiliyor mu, equity doğru mu, depeg/veri-kalitesi uyarısı var mı?
6. Hazır olunca **iki anahtarı da açın**: `.env`'de `BOT_ENABLED=true` (+ servisleri
   yeniden başlat) ve panelden strateji `is_enabled=true`.
7. Devre kesicinin armed olduğunu doğrulayın. Bot bir sonraki döngüde işlem açabilir.
8. İlk günlerde Telegram bildirimlerini ve **işlem ekonomisi** sayfasını
   (`/api/v1/dashboard/economics`) yakından izleyin; edge/al-tut karşılaştırması negatifse durun.

---

## Otomatik güvenlik kapıları

Bir işlem açılmadan önce şu koşulların tümü sağlanmalıdır:

- Master anahtar açık (`BOT_ENABLED=true`) **ve** strateji etkin (`is_enabled=true`)
- Devre kesici tripli değil
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
  başabaş win-rate, gerçekleşen edge, **al-tut'a (BTC) göre alfa** ve **strateji
  bazında kırılım** (`by_strategy`) + `?strategy=<ad>` filtresi (rejim
  yönlendirme açıkken hangi stratejinin edge ürettiğini görmek için)

## Kâr özellikleri (opt-in) ve paper'da deneme

Aşağıdaki özellikler **varsayılan kapalıdır** (canlı davranışı izinsiz değiştirmemek
için). Önce **paper'da** açıp `economics` ile al-tut'a karşı alfayı izleyin, edge
pozitifse canlıya alın.

| Bayrak | Ne yapar |
|--------|----------|
| `REGIME_ROUTING_ENABLED` | Rejime göre strateji seçer (trend→momentum, range→mean-reversion) |
| `FUNDING_CARRY_ENABLED` | Funding toplayan yönde boyutu artırır (futures, cap'li) |
| `SCALE_OUT_ENABLED` | +R'de kısmi kâr alır, stop'u breakeven'a çeker, kalanı koşturur |
| `MAKER_PEG_ENABLED` | Adaptive maker limitini order-book'a peg'ler (daha iyi doluş) |
| `PORTFOLIO_VOL_TARGET_ENABLED` | Tüm kitabı istikrarlı realize-vol bütçesine ölçekler |
| `SESSION_FILTER_ENABLED` | Düşük-likidite UTC saatlerinde/hafta sonu yeni giriş açmaz |

**Önerilen deneme sırası** (en yüksek beklenen-değer etkisi): önce
`REGIME_ROUTING_ENABLED` ve `SCALE_OUT_ENABLED`. Paper, bu özellikleri canlıyla
aynı kod yolundan aynalar (`PAPER_MIRROR_LIVE=true`).

```bash
# .env — paper'da deneme
SCALE_OUT_ENABLED=true
REGIME_ROUTING_ENABLED=true
# sonra: docker compose --profile paper up -d --force-recreate paper-worker
# izleme: GET /api/v1/dashboard/economics  -> by_strategy[*].has_edge ve benchmark.outperforms
```

Tüm bayrakların ayrıntılı açıklaması için `.env.example`'a bakın.

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
