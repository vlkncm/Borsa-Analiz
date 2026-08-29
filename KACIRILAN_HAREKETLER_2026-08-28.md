# 28 Ağustos 2026 — Kaçırılan Hareketler Kök Neden Raporu

## Kanıt sınırı

Bu rapor `2026-08-27` kapanışına kadar olan yerel OHLCV ile `2026-08-28`
gerçekleşmesini birbirinden ayırır. Veritabanında **geçerli bir 27 Ağustos akşam
tahmin snapshot'ı yoktur**. `as_of=2026-08-27` yazan 18 kayıt dahi 28 Ağustos
`10:50–16:02` Türkiye saatinde oluşturulmuştur. Yani hareket başladıktan sonra
üretilmiştir ve geçmiş tahmin başarısı olarak kullanılamaz. `as_of=2026-08-28`
olan 1.248 kayıt da gün içindeki tamamlanmamış 28 Ağustos barlarını içerir.

Bu nedenle aşağıdaki “yeniden yapılandırma” yalnız kök neden teşhisidir; “model
dün biliyordu” iddiası değildir. Düzeltmeden sonra seans açıldıktan sonra önceki
güne snapshot yazılması reddedilir ve tamamlanmamış günlük bar kesilir.

## Sembol doğrulaması

| Kullanıcıdaki ad | Doğrulanan kod | Sınıf |
|---|---:|---|
| Pergamon Status | PSDTC | BIST payı |
| Marmaris Altınyunus | MAALT | BIST payı |
| Prizma Pres | PRZMA | BIST payı |
| Grainturk Holding | GRTHO | BIST payı |
| Çitlekçi Mağazacılık Gıda | **CITAS** | Yeni halka arz BIST payı |
| Türkiye Halk Bankası | HALKB | BIST payı |
| Hidropar Hareket Kontrol | HKTM | BIST payı |
| Hat-San Gemi İnşaa | HATSN | BIST payı |
| Teknika Plast | TKNKA | Yeni halka arz BIST payı |
| Kardemir Çelik Sanayi | KARCL | Yeni halka arz BIST payı |
| Hedef Portföy Yönetimi adıyla verilen 5 satır | Kod güvenle belirlenemedi | Fon/katılma payı; normal BIST şirket payı değil |
| Neo Portföy Yönetimi adıyla verilen satır | Kod güvenle belirlenemedi | Fon/katılma payı; normal BIST şirket payı değil |

Çitlekçi için isimden kod tahmin edilmemiştir: halka arz kaynağı işlem kodunu
`CITAS` olarak bildirir. Yerel aktif evrende de `CITAS.IS` vardır ve 27 Ağustos
kesiminde 8 seans verisi bulunur. Kaynaklar:
[Anadolu Ajansı](https://www.aa.com.tr/tr/ekonomi/citlekci-halka-arz-geliriyle-2030da-99-magazaya-ulasma-yi-hedefliyor/4030368),
[Tera Yatırım halka arz duyurusu](https://www.terayatirim.com/duyurular/citlekci-magazacilik-gida-a-s-halka-arz-ediliyor/269).

Hedef/Neo satırlarında yalnız yönetici şirket adı ve fiyat verilmiştir; aynı
yöneticiye ait çok sayıda fon vardır. Yanlış fon kodu uydurulmamıştır. KAP örneği
Neo Portföy'ün `NRG` kodlu ürününün bir para piyasası fonu olduğunu doğrular:
[KAP NRG](https://www.kap.org.tr/tr/fon-bilgileri/ozet/nrg-neo-portfoy-birinci-para-piyasasi-fonu).

## 27 Ağustos kesimiyle teşhis tablosu

Tüm fiyat serilerinde son bar `2026-08-27`, veri sağlayıcı kodu `.IS` eşlemesiyle
doğrudur. “Sıra” ve olasılıklar, donmuş `t1t2-reference-v2` artefaktıyla yapılan
sonradan teşhistir. Geçerli eski snapshot olmadığı için geçmiş performans kanıtı
değildir.

| Sembol | Evrende | Gün | Menkul türü / yol | T+1 / T+2 sıra | T+1 P7 / P8 / Tavan | Referans | Net EV | Teşhis kararı ve kapı |
|---|---:|---:|---|---:|---:|---:|---:|---|
| PSDTC | Evet | 504 | NORMAL_PAY / standart | 25 / 24 | 27,03 / 19,59 / 6,07 | 20,91 | -5,62 | Geniş radar; `SLIPPAGE_RISK`, `NET_EV_NOT_POSITIVE` |
| MAALT | Evet | 504 | NORMAL_PAY / standart | 500 / 484 | 2,68 / 2,22 / 0,73 | 2,20 | -4,01 | Model düşük sıraladı; `OUTSIDE_TOP_PERCENTILE`, P7/P8 düşük |
| PRZMA | Evet | 504 | NORMAL_PAY / standart | 21 / 21 | 28,77 / 20,25 / 7,29 | 22,14 | -6,28 | Geniş radar; `LEVELS_NOT_VALIDATED`, Net EV negatif |
| GRTHO | Evet | 504 | NORMAL_PAY / standart | 489 / 490 | 2,82 / 2,20 / 0,68 | 2,25 | -5,27 | Model düşük sıraladı; `OUTSIDE_TOP_PERCENTILE`, P7/P8 düşük |
| CITAS | Evet | 8 | NORMAL_PAY / yeni halka arz | kalibre dışı / 616 | — / — / — | yüzde değil | — | Ayrı IPO radarı; `SHORT_HISTORY`, hareket 4,6 ATR ilerlemiş |
| HALKB | Evet | 504 | **BELIRSIZ** / standart | 22 / 26 | 28,04 / 20,21 / 7,33 | 21,80 | -2,82 | Geniş radar; `SECURITY_TYPE_UNVERIFIED`, eski KAP cache'inde kod yok |
| HKTM | Evet | 504 | NORMAL_PAY / standart | 36 / 37 | 17,01 / 11,45 / 4,20 | 12,87 | -7,67 | Geniş radar; ilk %5 dışında, P7 düşük, seviye/kayma riski |
| HATSN | Evet | 504 | NORMAL_PAY / standart | 18 / 16 | 30,96 / 22,94 / 7,18 | 24,18 | -3,86 | Geniş radar; `MOVE_ALREADY_EXTENDED`, Net EV negatif |
| TKNKA | Evet | 6 | NORMAL_PAY / yeni halka arz | kalibre dışı / 610 | — / — / — | yüzde değil | — | Ayrı IPO radarı; `SHORT_HISTORY`, geç giriş riski |
| KARCL | Evet | 20 | NORMAL_PAY / yeni halka arz | kalibre dışı / 625 | — / — / — | yüzde değil | — | Ayrı IPO radarı; `SHORT_HISTORY`, geç giriş riski |

T+1 feature hashleri sırasıyla:

- PSDTC `299709ca…b9dbf4`, MAALT `c029594d…0f10a1`, PRZMA `65f5353c…fee63b`
- GRTHO `99a22286…a47ae`, CITAS `2d1b042e…7fc051`, HALKB `d13b4078…678895`
- HKTM `81deb098…0ca02`, HATSN `b724e61a…025194`, TKNKA `c9c1e0c6…392e2ac`
- KARCL `7acc01e2…fef183`

Tarama anındaki eski worker bütün hisselere `Piyasa rejimi=VERİ YETERSİZ`,
`Sektör puanı=None`, `KAP=None` gönderiyordu. Yerel `XU100.IS` serisi 27 Ağustos'a
kadar 499 bar içerdiği için piyasa bilgisinin yokluğu veri yokluğundan değil,
worker bağlantı hatasından kaynaklanmıştır. Yeniden teşhiste rejim `POZİTİF`tir.
Sektör eşleme/endeks verisi yerelde doğrulanamadığından `None` bırakılmış ve
otomatik olumsuz sayılmamıştır. KAP bulunmaması da negatif KAP sayılmamıştır.

## Kesin kök nedenler

1. **Kesim/snapshot zamanı hatası:** Gün içi oluşmakta olan bar “tamamlanmış”
   kabul edilip aynı gün akşam tahmini gibi yazılıyordu. Aynı kesitsel sıralamada
   27 ve 28 Ağustos tarihli semboller karışabiliyordu.
2. **Karar bölünmesi:** Teknik erken aday motoru, eğitimli T+1/T+2 modeli ve
   dashboard birbirinden bağımsız karar üretiyordu. Dashboard ikinci kez eşik
   uyguluyor ve ortak sonucu göstermiyordu.
3. **Net EV kapısı:** Sabit %7 hedef, ATR stop ve %0,4 maliyetle 625 hissenin
   hiçbirinde pozitif EV çıkmadı. Bu koşul seçkin listeyi sistematik olarak boşalttı.
4. **KAP/menkul türü:** KAP tür cache'i başarısız veya eksik olduğunda `BELIRSIZ`
   hisseler geniş radardan da gizleniyordu. HALKB yerel cache'te bu nedenle
   `BELIRSIZ` kaldı.
5. **Kilitli bar NaN hatası:** `High=Low` olan tavan/tek fiyat barları CMF ve
   bazı MFI girdilerini NaN yapıyor, kalibre olasılıkların tümünü boşaltabiliyordu.
6. **Piyasa bağlamı bağlanmamıştı:** XU100 yerelde mevcut olmasına rağmen worker
   benchmark'ı modele iletmiyor ve rejimi sabit `VERİ YETERSİZ` yapıyordu.
7. **Yeni halka arz görünürlüğü:** 60 seans altındaki CITAS/TKNKA/KARCL standart
   modelde kalibre edilmemişti; geniş sıralamanın sonuna düşüyorlardı. Ayrı risk
   sınıfı zorunluydu.
8. **Sessiz eleme:** Her satırın hangi kapıda elendiğini taşıyan ortak bir sözleşme
   yoktu.

## Veri hatası / model / filtre ayrımı

- **Veri ve entegrasyon:** Geçerli tahmin snapshot'ı yok; gün içi snapshot'lar
  yanlış tarihsel kanıt gibi görünebiliyordu. HALKB menkul türü cache'te eksikti.
  XU100 mevcut olduğu halde bağlanmamıştı.
- **Modelin düşük sıraladığı:** MAALT ve GRTHO. Bunlar için eşik düşürülmedi ve
  bugünkü sonuç modele ezberletilmedi.
- **Modelde üst/geniş radar bölgesinde olup filtreye takılacaklar:** PSDTC, PRZMA,
  HALKB, HKTM, HATSN. Ana nedenler Net EV, seviye doğrulaması, kayma, ilerlemiş
  hareket ve HALKB için menkul türü belirsizliği.
- **Standart model kapsamı dışında:** CITAS, TKNKA, KARCL. Yüzde olasılık
  üretilmemelidir; yeni halka arz radarında görünmelidir.
- **Fon satırları:** Normal BIST şirket payı evreninin parçası değildir; fon
  analizinde, kesin fon koduyla değerlendirilmelidir.

## Net EV denetimi

| Ölçüm | T+1 |
|---|---:|
| Taranan | 625 |
| Net EV hesaplanan | 607 |
| Pozitif | **0** |
| Sıfır/negatif | 607 |
| Diğer güvenlik koşullarını geçip yalnız EV teyidi bekleyen | 5 |
| İlk 20 ortalama / medyan | -%4,56 / -%3,35 |
| İlk 20 aralık | -%14,23 … -%0,39 |

Net EV formülü walk-forward ile yeni bir alternatife karşı doğrulanmadan
değiştirilmemiştir. Negatif EV artık sessiz kesin eleme değildir: diğer şartlar
uygunsa `İZLE – RİSK/GETİRİ TEYİDİ`; pozitifse `AL ADAYI – CANLI TEYİT BEKLE`;
hesaplanamıyorsa `VERİ YETERSİZ` gösterilir.

## Model ve örnek dışı metrikler

Aktif model artefaktı değiştirilmedi; bugünkü kazananlara göre yeniden eğitim
yapılmadı. Bu nedenle “yeni” model metriği uydurulmamıştır. Mevcut dokunulmamış
T+1 test dönemi `2025-08-28–2026-08-25`, 56.410 satır / 514 semboldür.

| Hedef | Precision@1 | Precision@3 | Precision@5 | Recall@5 | Recall@10 | Recall@20 |
|---|---:|---:|---:|---:|---:|---:|
| T+1 %7+ | 0,447 | 0,383 | 0,342 | 0,235 | 0,364 | 0,532 |
| T+1 %8+ | 0,383 | 0,319 | 0,270 | 0,245 | 0,385 | 0,548 |
| T+1 tavan | 0,166 | 0,140 | 0,125 | 0,300 | 0,445 | **0,594** |
| T+2 %7+ | 0,535 | 0,459 | 0,417 | 0,159 | 0,267 | 0,432 |
| T+2 %8+ | 0,478 | 0,406 | 0,357 | 0,175 | 0,296 | 0,458 |
| T+2 tavan | 0,239 | 0,200 | 0,183 | 0,251 | 0,381 | **0,539** |

Mevcut özelliklerde göreceli hacim, CLV/kapanış konumu, OBV eğimi, CMF, MFI,
hacim sürekliliği, getiri ivmesi, ATR, sıkışma ve dirence uzaklık zaten vardır;
aynı anlamdaki özellikler ikinci kez eklenmemiştir. EMA5/EMA20, üst Bollinger,
üç günlük hacim ivmesi, yükselen dipler, yakın tavan davranışı ve ATR gecikme
cezası henüz zaman sıralı örnek dışı katkı testiyle Recall@20 veya Precision@3
artışı kanıtlanmadığı için aktif modele alınmamıştır.

## Uygulanan karar ve kayıt düzeltmeleri

- Tek `CandidateDecision` sözleşmesi worker, snapshot ve dashboard için ortaklaştırıldı.
- Geniş radar T+1/T+2 ilk 50 kalibre sırayı kapsar; menkul türü belirsiz yüksek
  sıralı hisseler uyarıyla görünür, fakat `AL` olamaz.
- Yeni halka arzlar kalibre yüzde uydurulmadan ayrı radarda kalır.
- Her sonuç `gate_codes`, `rejected_by`, “neden aday” ve “neden AL değil” taşır.
- Eksik KAP nötr belirsizliktir; yalnız doğrulanmış negatif KAP risk kapısıdır.
- KAP cache kaynak, zaman ve eskilik bilgisi karara eklenir.
- BIST 100 yalnız bir kez alınır; başarısızsa sahte rejim üretilmez.
- Snapshot yalnız uygun seans sonrası penceresinde yazılır; gerçekleşme ayrı
  tabloda kalır ve eski snapshot üzerine yazılmaz.
- Günlük `missed_moves_report` Precision@1/3/5, Recall@5/10/20, tavan ve %7+
  Recall@20 ile her kaçırmanın neden kodunu üretir.
