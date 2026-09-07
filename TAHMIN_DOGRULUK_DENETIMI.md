# Tahmin ve performans doğruluğu düzeltmesi

İncelenen taban commit: `436efe434263a55c196042c4486502d4aafbb841`.

Bu güncelleme tahmin muhasebesi, veri zamanı ve risk hesabındaki tekrarlanabilir hataları giderir. Gelecekteki başarı oranının arttığına veya kusursuz tahmine ilişkin bir iddia içermez. Kullanıcının bildirdiği %5'in dayandığı yerel günlük/rapor depoda bulunmadığından bu oran doğrulanamadı.

## Bulunan ve giderilen sorunlar

- **Alış gerçekleşmeden sonuç yazılması:** Yeni defterde sonraki seansın açılışı giriş bandındaysa açılıştan; bandın üstündeyse banda geri çekilmede üst sınırdan kâğıt işlem oluşur. Bandın altında açılışta gün içi yükseliş kovalanmaz. Bu politika gerçek aracı kurum gerçekleşmesi değildir. Aynı bar içinde geri çekilmeden önce hedef görülmüş olabileceğinden bu giriş barının hedefi sayılmaz; stop ihtimali muhafazakâr değerlendirilir.
- **Vade taşması:** Vade, sinyalden sonraki seanslar üzerinden sabittir; sonradan görülen hedef geçmiş tahmini başarılı yapmaz. Vade dolmadan açık işlem kapatılmaz. Hiç girilmeyen plan `GİRİŞ OLMADI` olarak kapanır ve işlem başarısı paydasına girmez.
- **Açılış boşluğu:** Stop altındaki açılış, stop fiyatından gerçekleşmiş gibi yazılmaz. Çıkıştan sonraki fiyat hareketleri performans ekstremumlarına girmez. Çıkış barının iç sırası bilinmediğinden maksimum hareket ölçüsü tamamlanmış önceki barlar ve gerçekleşme fiyatlarıyla sınırlıdır.
- **Tekrar ve geçmişe dönük kayıt:** Aynı veri günü/strateji/hisse tekrarı ve aynı hisse/stratejide açık plan varken yeni plan engellenir. Sonuç yazımı tekrarlanabilir. Otomatik sonuçlandırma hem veri tarihinden hem olay oluşturma tarihinden sonraki seansları kullanır.
- **Birbirinden kopuk kanıt kaynakları:** Genel karar kapıları artık başka strateji adları içeren eski CSV yerine yeni defterdeki `general_scan` kapanmış işlemlerini kullanır. Eksik olasılığa %50 doldurulmaz; belirsiz/işlemsiz kayıtlar başarı örneği sayılmaz.
- **Skorun olasılık gibi sunulması:** Genel rapordaki ağırlıklı teknik puan `Teknik Senaryo Skoru` olarak ayrılır. Kanıtlanmış hisse olasılığı olmadığı için eski `Model Olasılığı %` kolonu boş bırakılır. Stratejinin geçmiş hedef oranı ayrı isimle gösterilir. Bu oran hisseye özgü eğitilmiş/kalibre edilmiş model değildir; iç uyumluluk alanlarının adları korunmuştur.
- **Risk matematiği:** Getiri ve zarar aynı giriş fiyatına göre hesaplanır. Yeni planın oranı eski daha yüksek risk/getiriyle değiştirilemez. Yakın direnç hedefi sırf %4 altındadır diye yukarı taşınmaz. Pozisyon miktarı nakit bütçesiyle sınırlanır.
- **Veri katmanı:** İstanbul saat dilimi kaybolmaz; gün içi barlar üç saat geriye kaymaz. Düzeltilmiş/düzeltilmemiş fiyatlar farklı önbellek anahtarları kullanır; düzeltilmiş seriye ham BIST kapanışı eklenmez. Günlük dönüşler 18:15 öncesi o günün tamamlanmamış barını çıkarır. Kaynak hatasıyla dönen eski önbellek işaretlenir ve ana tarayıcı bunu güncel sinyalde kullanmaz. Tutarsız OHLC ve negatif hacim elenir.
- **Doğrulama ölçümleri:** İlk işlemin zararı maksimum düşüşe dahil edilir. Gelecekte yayımlanan haber veya olumsuz kurumsal aksiyon doğrulama bayrakları güvenli model seçimi onayı üretemez.

## Aynı veride önce/sonra

Aşağıdakiler sentetik regresyon senaryolarıdır, piyasa başarısı değildir. Giriş bandı 99–100, hedef 110, stop 95, vade 3 seans; toplam komisyon/kayma %0,34.

| Senaryo | Eski | Yeni |
|---|---|---|
| Fiyat hep bandın altında, hiç alış yok | Stop; -%5,34 | Giriş olmadı; işlem getirisi yok |
| Hedef yalnız dördüncü seansta görülüyor | Hedef; +%9,66 | Üçüncü seansta süre sonu; +%1,66 |
| Pozisyon açıldıktan sonra 90'a boşluk | Stop; -%5,34 | Açılıştan stop; -%10,34 |

## Eski kayıtlar ve raporun anlamı

Eski olaylar silinmez veya yeniden yazılmaz. Yeni muhasebe `evaluation_version=2` ile ayrılır. Detayda eski/işlemsiz kayıtlar görünür, `Ölçüme Dahil` bayrağı ve hariç tutulan kayıt sayısı neden farklı payda kullanıldığını açıklar. Eski açık kayıtlar yeni model sağlığını beslemez. Yeni örnekler birikirken koruma modu devam edebilir.

`Hedef Önce %` vade içinde hedefe ulaşan kapanmış kâğıt işlemlerin oranıdır. `Net Kazanç Oranı %` maliyet sonrası pozitif kapananların oranıdır. İkisi aynı ölçü değildir. Eski CSV performans tablosu tarihsel uyumluluk içindir; yeni kanıt kaynağı `Tahmin Performansi`/`Tahmin Detay` defteridir. Tavan radarı, eski CSV, intraday motor ve genel kâğıt işlem farklı olayları ölçer; sonuçları birbirine karıştırılmamalıdır.

## Doğrulama ve kalan sınırlar

- Regresyon testleri giriş, vade, boşluk, aynı bar belirsizliği, tekrar kayıt, olay zamanı, maliyet, nakit limiti, önbellek, zaman dilimi ve gelecek haber kontrolünü kapsar.
- Mevcut defter testlerine eksik açılış fiyatı, vade ve sabit olay zamanı eklendi. Gerçekleşme modeli artık bunları gerektiriyor.
- Bu Linux ortamında 9 masaüstü test modülü `libEGL.so.1` eksikliğinden toplanamadı. Diğer testler çalıştırıldı. Windows/PySide6 arayüzü ve Windows EXE üretimi bu değişiklikte doğrulanmadı.
- THYAO.IS için canlı Yahoo denemesi HTTP 429 / YFRateLimitError ile sıfır satır döndürdü. Gerçek veriyle uçtan uca getiri/backtest üstünlüğü ölçülmedi.
- Günlük tamamlanma saati mevcut 18:15 varsayımıdır; özel seans ve tatilleri içeren resmi takvim entegrasyonu değildir.
- Tarihsel evren, şirket bölünmeleri/temettüler, likidite ve fiyat limiti nedeniyle gerçekleşmeme, portföy içi korelasyon ve tüm farklı motorların ortak örnek dışı karşılaştırması ayrıca doğrulanmalıdır. Basit OHLC muhasebesi gerçek emir defterinin yerini tutmaz.
- Bu sürüm yeni bir eğitimli tahmin modeli veya optimizasyonla seçilmiş strateji değildir. Hedef/stop/kararların veri dışı başarısını kanıtlamak için değişiklikten sonra biriken kayıtlar veya güvenilir zaman damgalı geçmiş veri gerekir. Mevcut testlerde geçmek kârlılık kanıtı değildir.

## Kaynak ve çalıştırma

- yfinance veri indirme parametreleri: https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
- Kalibrasyonun ayrı veri gerektirmesi: https://scikit-learn.org/stable/modules/calibration.html

Kaynak kurulumunda `python -m pip install -r requirements.txt` ardından yeni regresyonlar için `python -m unittest test_prediction_integrity test_profesyonel_karar_sistemi` çalıştırılabilir. Tam test için Windows/PySide6 bağımlılıkları hazır ortamda `python -m unittest discover` kullanılmalıdır. Mevcut kurulu EXE, GitHub dalı güncellenince kendiliğinden değişmez; Windows üzerinde yeniden derlenmelidir.
