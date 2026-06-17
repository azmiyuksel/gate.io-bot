import {
  Activity,
  BarChart3,
  Beaker,
  BookOpen,
  Database,
  LayoutDashboard,
  LineChart,
  type LucideIcon,
  PieChart,
  Play,
  Shield,
  Zap,
} from "lucide-react";

/**
 * Türkçe yardım içeriği. Finans bilmeyen bir kullanıcı için sade dille yazılır:
 * her ekranın ne işe yaradığı, ekrandaki her buton/liste/alanın ne yaptığı ve
 * hangi ayarı değiştirince neyin değişeceği anlatılır. Teknik terimler en altta
 * "Finansal Terimler Sözlüğü" bölümünde açıklanır.
 */

export type HelpItemKind = "Buton" | "Liste" | "Alan" | "Onay kutusu" | "Gösterge" | "Sekme";

export interface HelpItem {
  name: string;
  kind: HelpItemKind;
  desc: string;
}

export interface HelpModule {
  id: string;
  route: string;
  title: string;
  icon: LucideIcon;
  summary: string;
  forBeginner: string;
  items: HelpItem[];
  tips?: string[];
}

export interface GlossaryTerm {
  term: string;
  def: string;
}

export const HELP_MODULES: HelpModule[] = [
  {
    id: "dashboard",
    route: "/",
    title: "Dashboard (Genel Bakış)",
    icon: LayoutDashboard,
    summary:
      "Hesabın genel durumunu tek ekranda gösterir: toplam paran, bugünkü ve bu haftaki kâr/zarar, botun çalışıp çalışmadığı ve temel risk ayarların.",
    forBeginner:
      "Buraya 'kontrol paneli' gibi bak. Sabah açıp 'her şey yolunda mı?' diye bakacağın yer. Asıl ayarları burada yaparsın, asıl işlemleri Paper Trading ekranında izlersin.",
    items: [
      { name: "Toplam bakiye", kind: "Gösterge", desc: "Hesabındaki toplam para (nakit + açık pozisyonların güncel değeri). Buna 'equity' (öz sermaye) denir." },
      { name: "Günlük / Haftalık PnL", kind: "Gösterge", desc: "PnL = kâr/zarar (Profit and Loss). Bugün ve bu hafta kaç para kazandın/kaybettin. Yeşil = kâr, kırmızı = zarar." },
      { name: "Bot durumu", kind: "Gösterge", desc: "Botun 'Çalışıyor' mu yoksa 'Durdu' mu olduğunu söyler. Çalışıyorsa otomatik işlem açıp kapatabilir." },
      { name: "İşlem sermaye %", kind: "Alan", desc: "Bir tek işleme paranın en fazla yüzde kaçını koyacağını sınırlar. Büyütürsen işlemler büyür (daha çok kazanç ama daha çok risk); küçültürsen daha temkinli olur." },
      { name: "Günlük zarar %", kind: "Alan", desc: "Bir günde bu kadar kaybedersen bot yeni işlem açmayı durdurur (otomatik fren). Düşük tutmak seni kötü günlerde korur." },
      { name: "Haftalık zarar %", kind: "Alan", desc: "Aynı frenin haftalık olanı. Bir haftada bu sınırı geçen zarar olursa bot durur." },
      { name: "ATR çarpanı", kind: "Alan", desc: "Zarar-durdur (stop-loss) noktasının ne kadar 'geniş' olacağını ayarlar. Büyük değer = stop fiyattan daha uzakta (erken kapanmaz ama zarar büyük olabilir); küçük değer = stop yakında (çabuk korur ama gürültüde erken kapanabilir). ATR için sözlüğe bak." },
      { name: "Kaydet", kind: "Buton", desc: "Yukarıdaki risk ayarlarını kaydeder. Kaydetmeden çıkarsan değişiklikler uygulanmaz." },
      { name: "Giriş / Kayıt Ol / Çıkış", kind: "Buton", desc: "Hesaba giriş yapmak, yeni hesap açmak veya oturumu kapatmak için." },
    ],
    tips: [
      "Yeni başlıyorsan 'İşlem sermaye %' ve 'Günlük zarar %' değerlerini düşük tut; botu önce Paper Trading'de (sahte parayla) izle.",
    ],
  },
  {
    id: "paper-trading",
    route: "/paper-trading",
    title: "Paper Trading (Sahte Parayla Test)",
    icon: Play,
    summary:
      "Gerçek piyasa fiyatlarıyla ama SAHTE parayla işlem yapar. Strateji gerçekten para kazandırıyor mu, hiç risk almadan burada görürsün.",
    forBeginner:
      "Uçuş simülatörü gibi: gerçek gökyüzü, sahte uçak. Strateji burada kâr ediyorsa gerçeğe geçmeye değer. Para gerçek değildir, gönül rahatlığıyla dene.",
    items: [
      { name: "Başlat [S]", kind: "Buton", desc: "Botu çalıştırır; sinyal geldikçe sahte işlem açıp kapatmaya başlar. (Klavyede S tuşu da çalışır.)" },
      { name: "Duraklat [P]", kind: "Buton", desc: "Yeni işlem açmayı geçici durdurur ama açık pozisyonları yönetmeye devam eder. Devam etmek için 'Devam Et'." },
      { name: "Devam Et [R]", kind: "Buton", desc: "Duraklatılmış botu tekrar çalıştırır." },
      { name: "Durdur [X]", kind: "Buton", desc: "Botu tamamen durdurur." },
      { name: "Sıfırla", kind: "Buton", desc: "Tüm sahte geçmişi siler: bakiye başlangıca döner, işlemler/pozisyonlar/grafik temizlenir. Yeni bir teste taze başlamak için kullan. (Geri alınamaz.)" },
      { name: "Sembol listesi (Hızlı İşlem)", kind: "Liste", desc: "Elle işlem açarken hangi kripto çiftinde (örn. BTC_USDT) işlem yapacağını seçersin." },
      { name: "Yön: AL / SAT", kind: "Liste", desc: "AL (long) = fiyat yükselirse kazanırsın. SAT (short) = fiyat düşerse kazanırsın. Short'ta önce SAT açılır, sonra AL ile kapatılır." },
      { name: "Miktar (Qty)", kind: "Alan", desc: "Elle açacağın işlemin büyüklüğü (kaç adet)." },
      { name: "AL / SAT (işlem butonu)", kind: "Buton", desc: "Seçtiğin sembol, yön ve miktarla elle bir işlem açar (botu beklemeden)." },
      { name: "Kapat (pozisyon satırı)", kind: "Buton", desc: "O açık pozisyonu hemen kapatır ve kâr/zararı gerçekleştirir." },
      { name: "Risk göstergeleri", kind: "Gösterge", desc: "Günlük Zarar, Drawdown, Exposure ve Açık Pozisyon çubukları; limitlere ne kadar yaklaştığını gösterir. Dolan çubuk = sınıra yaklaşıyorsun." },
      { name: "Sembol / Yön / Sayfa filtreleri (Son İşlemler)", kind: "Liste", desc: "İşlem geçmişini sembole veya yöne göre süzer; 'Son 10/25/50/100' kaç satır gösterileceğini seçer." },
      { name: "Yön etiketi: LONG / SHORT / KAPAT", kind: "Gösterge", desc: "LONG = al-yükselişe oyna açılışı, SHORT = sat-düşüşe oyna açılışı, KAPAT = pozisyon kapanışı. Bu yüzden 'AL gelmeden SAT' görmek normaldir (short açılışı)." },
      { name: "Sinyal Teşhisi (signal diagnostics)", kind: "Gösterge", desc: "Bot neden işlem açmadı/açtı onu özetler (örn. 'hacim düşük', 'trend uygun değil'). Botun sessiz durmasının sebebini buradan anlarsın." },
      { name: "Equity / Toplam Getiri / Win Rate / Max Drawdown", kind: "Gösterge", desc: "Sırasıyla: güncel toplam para, baştan beri yüzde kazanç, kazanan işlem oranı, en büyük tepe-dip düşüş. Terimler için sözlüğe bak." },
    ],
    tips: [
      "Strateji değiştirdikten sonra temiz bir karşılaştırma için önce 'Sıfırla' de.",
      "Bot 'risk limiti' yüzünden duraklarsa: önce Sıfırla; sorun sürerse Dashboard'dan günlük/drawdown limitlerini gözden geçir.",
    ],
  },
  {
    id: "portfolio",
    route: "/portfolio",
    title: "Portföy",
    icon: PieChart,
    summary:
      "Paranı birden çok stratejiye/varlığa nasıl dağıttığını gösterir ve 'tüm yumurtalar aynı sepette mi?' riskini ölçer.",
    forBeginner:
      "Tek bir şeye değil, birden çok şeye yatırım yapınca riski yayarsın. Bu ekran o dağılımı ve dengeyi gösterir.",
    items: [
      { name: "Yenile", kind: "Buton", desc: "Portföy verilerini en güncel haline getirir." },
      { name: "Yeniden Dengele", kind: "Buton", desc: "Dağılım bozulduysa ağırlıkları hedefe geri çeker (örn. biri çok büyüdüyse bir kısmını diğerlerine kaydırır)." },
      { name: "Portföyü Sıfırla", kind: "Buton", desc: "Portföy verisini başa alır." },
      { name: "Senaryo simülasyonları (-30% çöküş, flash crash, yüksek volatilite, korelasyon spike)", kind: "Buton", desc: "'Ya piyasa çökerse?' diye kötü senaryoları sahte olarak çalıştırır; portföyün ne kadar kaybedeceğini önceden gösterir (stres testi)." },
      { name: "Toplam Bakiye / Sharpe / Maks Drawdown", kind: "Gösterge", desc: "Toplam para; getirinin ne kadar 'pürüzsüz/risk-verimli' olduğu (Sharpe); en büyük düşüş. Sözlüğe bak." },
      { name: "Korelasyon Risk Skoru + ısı haritası", kind: "Gösterge", desc: "Varlıkların ne kadar 'birlikte hareket ettiğini' gösterir. Hepsi aynı anda düşüyorsa risk yüksektir (çeşitlendirme zayıf)." },
      { name: "VaR %95", kind: "Gösterge", desc: "'Riske Maruz Değer': kötü bir günde (en kötü %5 senaryoda) yaklaşık ne kadar kaybedebileceğinin tahmini." },
      { name: "Strateji ağırlık / performans tabloları", kind: "Gösterge", desc: "Her stratejinin portföydeki payı ve geçmiş başarısı (Sharpe, kazanma oranı, profit factor, vb.)." },
    ],
  },
  {
    id: "strategy-research",
    route: "/strategy-research",
    title: "Araştırma Lab",
    icon: Beaker,
    summary:
      "Yeni alım-satım stratejileri üretir, test eder ve birbiriyle yarıştırır. En iyi fikirleri bir 'lider tablosunda' sıralar.",
    forBeginner:
      "Strateji fabrikası: bilgisayar yeni fikirler dener, hangisi geçmişte iyi çalışmış diye puanlar. Sen en iyilerini görüp seçersin.",
    items: [
      { name: "Sembol / TF (timeframe)", kind: "Alan", desc: "Hangi kripto çiftinde ve hangi mum süresinde (örn. 5m = 5 dakika) araştırma yapılacağını belirler." },
      { name: "Araştırma Turu Çalıştır", kind: "Buton", desc: "Yeni strateji fikirleri üretip test eder ve lider tablosunu günceller." },
      { name: "Feature'ları Hesapla", kind: "Buton", desc: "Stratejilerin kullandığı göstergeleri (sinyalleri) yeniden hesaplar." },
      { name: "Hipotezleri Test Et", kind: "Buton", desc: "'Şu kural kâr ettirir mi?' gibi varsayımları istatistikle sınar." },
      { name: "Overfit gizle", kind: "Onay kutusu", desc: "'Aşırı uydurma' (overfit) stratejileri listeden gizler. Overfit = geçmişe çok iyi uymuş ama gelecekte çökmesi muhtemel strateji. Sözlüğe bak." },
      { name: "Lider tablosu (Detay / Terfi)", kind: "Buton", desc: "Bir stratejinin ayrıntısını açar ('Detay') veya onu bir üst aşamaya yükseltir ('Terfi')." },
      { name: "CSV", kind: "Buton", desc: "Tabloyu Excel'de açabileceğin bir dosya olarak indirir." },
      { name: "Fitness / Sharpe / DD / Stab. / p-değeri", kind: "Gösterge", desc: "Strateji puanları. Fitness = genel başarı puanı; p-değeri = sonucun şans eseri olma ihtimali (küçük = daha güvenilir). Sözlüğe bak." },
    ],
  },
  {
    id: "strategy-health",
    route: "/strategy-health",
    title: "Strateji Sağlık",
    icon: Shield,
    summary:
      "Çalışan bir stratejinin 'formunu' izler: eskisi kadar iyi mi, yoksa bozulmaya mı başladı? Bozulursa uyarır veya durdurur.",
    forBeginner:
      "Stratejinin sağlık check-up'ı. Bir strateji zamanla işe yaramaz hale gelebilir; bu ekran bunu erken yakalar.",
    items: [
      { name: "Strateji Adı", kind: "Alan", desc: "Hangi stratejinin sağlığına bakacağını yazarsın." },
      { name: "Parametreleri Yeniden Hesapla", kind: "Buton", desc: "Sağlık ölçümlerini güncel verilerle yeniden hesaplar." },
      { name: "Stratejiyi Duraklat / Devam Ettir", kind: "Buton", desc: "Stratejiyi elle durdurur veya tekrar başlatır." },
      { name: "Sharpe / Win Rate / Profit Factor / Drawdown sekmeleri", kind: "Sekme", desc: "Hangi başarı ölçütünün grafiğini göreceğini seçer. 'Gerçekleşen' çizgisi 'Beklenen' çizgisinin çok altına düşerse strateji bozuluyor demektir." },
      { name: "Sağlık Skoru / Sapma (Drift) Skoru", kind: "Gösterge", desc: "Sağlık Skoru yüksek = iyi. Drift = stratejinin davranışının zamanla ne kadar 'kaydığı'; yüksekse dikkat." },
      { name: "Hata Teşhisi / Anomali Durumu", kind: "Gösterge", desc: "Bozulmanın türü (yavaş çürüme, ani çöküş, vb.) ve sıra dışı bir durum olup olmadığı." },
    ],
  },
  {
    id: "market-regime",
    route: "/market-regime",
    title: "Piyasa Rejimi",
    icon: Activity,
    summary:
      "Piyasanın şu anki 'havasını' söyler: yükseliş trendi mi, düşüş mü, yatay mı, çok mu oynak? Bota buna göre temkinli/atak olmasını söyler.",
    forBeginner:
      "Hava durumu gibi: 'bugün fırtınalı (oynak)' ya da 'açık ve yükselişte'. Bot havaya göre risk ayarını otomatik kısar veya açar.",
    items: [
      { name: "Modelleri Yeniden Eğit / Hesapla", kind: "Buton", desc: "Yapay zekâ modellerini güncel fiyatlarla yeniden çalıştırıp rejimi günceller." },
      { name: "Yenile", kind: "Buton", desc: "Ekrandaki rejim bilgisini tazeler." },
      { name: "Mevcut Piyasa Rejimi", kind: "Gösterge", desc: "Şu anki durum: Yükseliş/Düşüş Trendi, Yatay, Yüksek/Düşük Volatilite veya Kırılım." },
      { name: "Tahmin Güven Skoru", kind: "Gösterge", desc: "Modelin bu tahmine ne kadar güvendiği (% olarak). Düşükse 'emin değil' demektir." },
      { name: "Regime Bazlı Risk Çarpanı", kind: "Gösterge", desc: "Rejime göre işlem boyutu çarpanı. Örn. 0.50x = riskli ortamda işlemleri yarıya indir; 1.20x = uygun ortamda biraz büyüt." },
      { name: "Rejim performans matrisi", kind: "Gösterge", desc: "Her stratejinin hangi piyasa havasında ne kadar iyi/kötü olduğunu gösterir." },
    ],
  },
  {
    id: "execution-quality",
    route: "/execution-quality",
    title: "İcra Kalitesi",
    icon: Zap,
    summary:
      "Emirlerin ne kadar 'iyi fiyattan' ve ne kadar hızlı gerçekleştiğini ölçer. Beklenenden kötü fiyata dolan emirler (kayma) paranı sızdırır.",
    forBeginner:
      "İşlemlerin 'kalite kontrolü'. İstediğin fiyat 100 ama 100.3'e aldıysan aradaki fark (kayma) gizli bir maliyettir. Burası onu ölçer.",
    items: [
      { name: "Strateji Adı", kind: "Alan", desc: "Hangi stratejinin icra kalitesine bakacağını yazarsın." },
      { name: "Metrikleri Yeniden Hesapla / Yenile", kind: "Buton", desc: "İcra ölçümlerini güncel verilerle yeniden hesaplar/tazeler." },
      { name: "İcra Kalite Skoru", kind: "Gösterge", desc: "0-100 arası genel kalite notu. Yüksek = emirler iyi fiyat ve hızda doluyor." },
      { name: "Ortalama Kayma (Slippage)", kind: "Gösterge", desc: "İstenen fiyat ile gerçekleşen fiyat arasındaki ortalama fark. Küçük olması iyidir. Sözlüğe bak." },
      { name: "Ortalama Latency (Gecikme)", kind: "Gösterge", desc: "Emrin gönderilip dolması arasındaki süre (milisaniye). Düşük = hızlı." },
      { name: "Kayma dağılımı / öneriler tablosu", kind: "Gösterge", desc: "Kaymanın ne kadar sık 'kötü/kritik' olduğunu ve nasıl iyileştirileceğine dair önerileri gösterir." },
    ],
  },
  {
    id: "data-quality",
    route: "/data-quality",
    title: "Veri Kalitesi",
    icon: Database,
    summary:
      "Botun beslendiği fiyat verisinin sağlam olup olmadığını denetler. Bozuk/eksik veriyle iyi karar verilemez.",
    forBeginner:
      "Botun gözü-kulağı fiyat verisidir. Veri bozuksa bot yanlış karar verir. Bu ekran verinin temiz olduğunu garantiler.",
    items: [
      { name: "Sembol / TF", kind: "Alan", desc: "Hangi kripto çiftinin ve zaman diliminin verisini denetleyeceğini seçer." },
      { name: "Yenile", kind: "Buton", desc: "Veri sağlık durumunu tazeler." },
      { name: "Yeniden Doğrula", kind: "Buton", desc: "Geçmiş veriyi baştan tarayıp eksik/bozuk var mı diye yeniden kontrol eder." },
      { name: "Veri Sağlık Skoru / Kategori", kind: "Gösterge", desc: "Verinin genel kalitesi (Mükemmel/İyi/Riskli/Güvenilmez)." },
      { name: "İşlem Durumu", kind: "Gösterge", desc: "Veriye göre bota ne dendiği: 'Temiz-normal işlem', 'Bozuk-risk azaltıldı' veya 'Geçersiz-işlem durduruldu'." },
      { name: "Anomaliler / Eksik Mum / Gecikme", kind: "Gösterge", desc: "Sıra dışı sıçramalar, kayıp veri parçaları ve verinin ne kadar geç geldiği." },
    ],
  },
  {
    id: "backtests",
    route: "/backtests",
    title: "Backtest (Geçmişe Dönük Test)",
    icon: LineChart,
    summary:
      "Bir stratejiyi geçmiş fiyatlar üzerinde çalıştırır: 'Bu strateji son 1 yılda kullanılsaydı ne kazanırdı?' sorusunu yanıtlar.",
    forBeginner:
      "Zaman makinesi: stratejiyi geçmişe götürüp 'olsaydı ne olurdu' diye dener. Gerçek parayla denemeden önceki ilk eleme adımı.",
    items: [
      { name: "+ Yeni", kind: "Buton", desc: "Yeni bir backtest oluşturma formunu açar." },
      { name: "Yenile", kind: "Buton", desc: "Backtest listesini tazeler." },
      { name: "Sembol / Timeframe", kind: "Alan", desc: "Hangi çiftte ve hangi mum süresinde test yapılacağı." },
      { name: "Başlangıç / Bitiş", kind: "Alan", desc: "Testin kapsayacağı geçmiş tarih aralığı." },
      { name: "İlk sermaye", kind: "Alan", desc: "Teste kaç dolarla başlanacağı (sahte)." },
      { name: "Veri kaynağı", kind: "Liste", desc: "Fiyat verisinin nereden alınacağı (önbellek / CSV dosyası / Gate.io)." },
      { name: "Parametreler JSON", kind: "Alan", desc: "Stratejinin ince ayarları (ileri düzey). Boş bırakırsan varsayılanlar kullanılır." },
      { name: "Backtest Başlat", kind: "Buton", desc: "Testi çalıştırır; bitince Net Kâr, Sharpe, Max Drawdown gibi sonuçları gösterir." },
      { name: "Aç / Sil (liste satırı)", kind: "Buton", desc: "Bir testin ayrıntılı sonucunu açar veya kaydı siler." },
    ],
    tips: [
      "Tek bir backtest'in çok iyi çıkması yanıltıcı olabilir (geçmişe uydurma riski). Sağlamlığı 'Walk-Forward' ekranıyla doğrula.",
    ],
  },
  {
    id: "walk-forward",
    route: "/walk-forward",
    title: "Walk-Forward (Sağlamlık Testi)",
    icon: BarChart3,
    summary:
      "Stratejiyi 'gör­mediği' dönemlerde tekrar tekrar test eder. Amaç: strateji sadece geçmişe mi uymuş, yoksa gerçekten işe mi yarıyor?",
    forBeginner:
      "Sınav hilesini ayıklayan yöntem. Bir öğrenci soruları ezberlemiş olabilir; bu test ona hiç görmediği sorular sorar. Strateji burada da kazanıyorsa güvenilirdir.",
    items: [
      { name: "Parametreler", kind: "Buton", desc: "Ayar bölümünü açar/kapatır." },
      { name: "Başlat", kind: "Buton", desc: "Walk-forward analizini çalıştırır." },
      { name: "Sembol / Timeframe / Başlangıç / Bitiş", kind: "Alan", desc: "Test edilecek çift, mum süresi ve tarih aralığı." },
      { name: "Eğitim periyodu (gün)", kind: "Alan", desc: "Stratejinin 'öğrenmek' için kullanacağı geçmiş pencere uzunluğu." },
      { name: "Test periyodu (gün)", kind: "Alan", desc: "Öğrendikten sonra 'sınava girdiği', daha önce görmediği pencere." },
      { name: "Adım (gün)", kind: "Alan", desc: "Pencerenin her turda ne kadar ileri kaydırılacağı." },
      { name: "Deneme sayısı", kind: "Alan", desc: "Kaç farklı ayar kombinasyonunun deneneceği. Çok = daha kapsamlı ama daha yavaş." },
      { name: "Robustness / WFE / Consistency", kind: "Gösterge", desc: "Sağlamlık puanları. WFE (Walk-Forward Verimliliği): görülmeyen dönemdeki başarı, görülen döneme göre ne kadar korunmuş. Yüksek = güvenilir." },
    ],
  },
  {
    id: "learning",
    route: "/learning",
    title: "Otomatik Öğrenme",
    icon: BookOpen,
    summary:
      "Sistemin kendi kendine yeni stratejiler keşfedip test ettiği yer. En iyi adayları senin onayına sunar — insan onayı olmadan canlıya geçmez.",
    forBeginner:
      "Otomatik bir araştırmacı asistan: gece gündüz yeni fikirler dener, en iyilerini 'onaylar mısın?' diye sana getirir. Son söz sende.",
    items: [
      { name: "Onaylayan e-posta", kind: "Alan", desc: "Bir stratejiyi onaylarken/red ederken kimin karar verdiğini kaydetmek için e-postan." },
      { name: "Öğrenme Turu", kind: "Buton", desc: "Yeni bir keşif-test döngüsü başlatır." },
      { name: "Yenile", kind: "Buton", desc: "Öğrenme verilerini tazeler." },
      { name: "Onayla / Reddet (aday satırı)", kind: "Buton", desc: "Terfi bekleyen bir stratejiyi onaylar (bir üst aşamaya geçer) veya reddeder." },
      { name: "Skor / Robust. / WF / Stab.", kind: "Gösterge", desc: "Adayın puanları: genel skor, sağlamlık, walk-forward başarısı ve istikrar." },
      { name: "Keşfedilen feature'lar", kind: "Gösterge", desc: "Sistemin bulduğu yeni sinyaller ve bunların kârla ne kadar ilişkili olduğu." },
    ],
  },
];

export const GLOSSARY: GlossaryTerm[] = [
  { term: "Long (AL) / Short (SAT)", def: "Long = fiyatın yükseleceğine oynamak (önce al, sonra sat). Short = fiyatın düşeceğine oynamak (önce sat, sonra geri al). Short'ta işlem SAT ile açıldığı için 'AL olmadan SAT' görmek normaldir." },
  { term: "PnL (Kâr/Zarar)", def: "Profit and Loss. Bir işlemden veya toplamda kazandığın/kaybettiğin para. Pozitif = kâr, negatif = zarar." },
  { term: "Equity (Öz sermaye)", def: "Hesabının gerçek toplam değeri: nakit + açık pozisyonların güncel piyasa değeri. 'Gerçek paran' budur." },
  { term: "Realized / Unrealized PnL", def: "Realized = pozisyonu kapatınca kesinleşen kâr/zarar. Unrealized = pozisyon hâlâ açıkken kâğıt üstünde görünen, henüz kesinleşmemiş kâr/zarar." },
  { term: "Pozisyon", def: "Piyasada açık olan bir işlemin (long ya da short). Kapatınca kâr/zarar kesinleşir." },
  { term: "Stop-loss (Zarar-durdur)", def: "Önceden belirlenen bir 'pes etme' fiyatı. Fiyat oraya gelirse pozisyon otomatik kapanır; küçük bir zararı büyük bir zarara dönüşmeden keser." },
  { term: "Take-profit (Kâr-al)", def: "Önceden belirlenen kâr hedefi. Fiyat oraya gelince pozisyon otomatik kapanıp kârı cebe koyar." },
  { term: "Trailing stop (İz süren stop)", def: "Fiyat lehine gittikçe peşinden yukarı çekilen stop. Kârı korur ama trend sürerse içeride kalmaya devam eder." },
  { term: "Drawdown (Tepe-dip düşüş)", def: "Hesabın en yüksek noktasından en düşük noktasına olan yüzde düşüş. 'En kötü ne kadar geriledim' sorusunun cevabı. Düşük olması iyidir." },
  { term: "Win rate (Kazanma oranı)", def: "İşlemlerin yüzde kaçının kârla kapandığı. Tek başına yetmez: az ama büyük kazançlar, çok ama küçük kayıpları yenebilir." },
  { term: "Sharpe oranı", def: "Aldığın risk başına ne kadar getiri elde ettiğinin ölçüsü. Yüksek Sharpe = getiri daha 'pürüzsüz' ve risk-verimli. Kabaca 1 iyi, 2 çok iyi sayılır." },
  { term: "Profit factor", def: "Toplam kazançların toplam kayıplara oranı. 1'in üstü kârlı demektir; 1.5+ iyidir." },
  { term: "Expectancy / Edge (Beklenti / Avantaj)", def: "Ortalama bir işlemden beklenen kâr. Pozitifse stratejinin 'matematiksel avantajı' var demektir." },
  { term: "Payoff oranı", def: "Ortalama kazancın ortalama kayba oranı. Yüksekse kazançların kayıplardan büyük demektir." },
  { term: "ATR (Ortalama Gerçek Aralık)", def: "Fiyatın ne kadar oynak olduğunun ölçüsü. Stop-loss mesafesini buna göre ayarlarız: oynak piyasada stop daha geniş tutulur." },
  { term: "RSI", def: "0-100 arası bir gösterge. Çok yüksekse fiyat 'aşırı alınmış' (geri çekilebilir), çok düşükse 'aşırı satılmış' (toparlayabilir) sinyali verir." },
  { term: "EMA (Üssel Hareketli Ortalama)", def: "Fiyatın yumuşatılmış ortalaması. Kısa EMA uzun EMA'yı yukarı keserse yükseliş, aşağı keserse düşüş ipucu sayılır." },
  { term: "Breakout (Kırılım)", def: "Fiyatın bir süredir takıldığı seviyeyi güçlüce aşması. Momentum stratejisi bu kırılımlarda işlem açar." },
  { term: "Volatilite", def: "Fiyatın ne kadar sert ve sık oynadığı. Yüksek volatilite = daha çok fırsat ama daha çok risk." },
  { term: "Slippage (Kayma)", def: "İstediğin fiyat ile gerçekte dolduğun fiyat arasındaki fark. Gizli bir maliyettir; küçük olması iyidir." },
  { term: "Latency (Gecikme)", def: "Emrin gönderilmesi ile gerçekleşmesi arasındaki süre. Düşük gecikme = daha iyi fiyatlar." },
  { term: "Leverage (Kaldıraç)", def: "Borçla pozisyonu büyütmek. 5x kaldıraç, paranın 5 katı büyüklükte işlem demektir: kâr da zarar da 5 katına çıkar. Riski artırır." },
  { term: "Exposure (Maruziyet)", def: "Toplam paranın ne kadarının şu an piyasada açık pozisyonlarda olduğu. Yüksekse risk yüksektir." },
  { term: "VaR (Riske Maruz Değer)", def: "Kötü bir günde (örn. en kötü %5 senaryoda) yaklaşık ne kadar kaybedebileceğinin istatistiksel tahmini." },
  { term: "Korelasyon", def: "İki varlığın ne kadar 'birlikte' hareket ettiği. +1 = hep aynı yönde, 0 = ilgisiz. Hepsi bir arada düşerse çeşitlendirme işe yaramaz." },
  { term: "Backtest", def: "Bir stratejiyi geçmiş veriler üzerinde çalıştırarak 'olsaydı ne olurdu' diye sınamak." },
  { term: "Walk-Forward / Out-of-sample", def: "Stratejiyi, ayarlarını belirlerken kullanmadığı 'görülmemiş' dönemlerde test etmek. Gerçek dünyaya en yakın sınav." },
  { term: "Overfit (Aşırı uydurma)", def: "Geçmişe mükemmel uyan ama gelecekte çöken strateji. Sınav sorularını ezberleyip mantığı öğrenmemek gibidir; en büyük tuzaktır." },
  { term: "p-değeri", def: "Bir sonucun sırf şans eseri olma ihtimali. Küçük (örn. 0.05'in altı) = sonuç muhtemelen gerçek, tesadüf değil." },
  { term: "Piyasa rejimi", def: "Piyasanın genel havası: yükseliş/düşüş trendi, yatay, yüksek/düşük volatilite. Bot rejime göre risk ayarını değiştirir." },
  { term: "Paper trading", def: "Gerçek fiyatlarla ama sahte parayla işlem. Risk almadan stratejiyi denemenin yolu." },
  { term: "Fee (Komisyon/Ücret)", def: "Her işlemde borsaya ödenen küçük ücret. Çok sık işlem yapınca toplamı önemli hale gelir." },
  { term: "Funding (Fonlama maliyeti)", def: "Kaldıraçlı (futures) pozisyonu uzun süre açık tutmanın periyodik maliyeti." },
];

/** Verilen URL yoluna karşılık gelen yardım bölümünün anchor id'sini döndürür. */
export function helpAnchorForPath(pathname: string): string {
  // En uzun eşleşen rotayı seç (örn. "/backtests/create" -> "backtests").
  const match = [...HELP_MODULES]
    .filter((m) => (m.route === "/" ? pathname === "/" : pathname.startsWith(m.route)))
    .sort((a, b) => b.route.length - a.route.length)[0];
  return match ? match.id : "";
}
