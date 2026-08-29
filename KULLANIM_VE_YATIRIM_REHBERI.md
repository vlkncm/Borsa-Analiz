# Borsa Analiz Pro MAX — Kullanım ve Yatırım Kontrol Rehberi

## Sade ekrandaki kararlar

- **AL:** Bütün zorunlu güvenlik kontrollerini geçen, güncel fiyatı alım bölgesinde olan adaydır; emir veya garanti değildir.
- **BEKLE:** Görünüm olumlu olabilir ancak uygun fiyat, teyit veya hedef süresi beklenmelidir.
- **ALMA:** Yeni yatırım için risk, geç giriş, likidite veya risk/getiri koşulu uygun değildir.
- **KÂR AL / SAT:** Yalnız portföye gerçek alış fiyatı ve tarihiyle kaydedilmiş hisselerde kullanılır.
- **VERİ YETERSİZ:** Güncel ve güvenilir karar üretilememiştir.

Ana listede en fazla beş sonuç gösterilir. Listeyi doldurmak için şartlar gevşetilmez. Teknik hesaplar arka planda korunur ve **Teknik Ayrıntıları Göster** düğmesinden incelenebilir.

Bu rehber, programın ürettiği sonuçları bir işlem planına dönüştürürken hangi
kontrollerin yapılması gerektiğini açıklar. Program bir karar destek aracıdır;
kişiye özel yatırım tavsiyesi, emir veya getiri garantisi vermez.

## Hızlı kullanım akışı

1. Taramayı çalıştırın ve tamamlanmasını bekleyin.
2. Kullanacağınız vadeyi seçin: Günlük Trade, Kısa Vade veya Orta Vade.
3. Adayın **Veri Tarihi** ve **Veri Durumu** alanlarını kontrol edin.
4. Kararı, alış bandını, hedefi, stopu ve risk/getiri oranını birlikte okuyun.
5. Satın almadan hemen önce güncel fiyatı aracı kurum ekranından doğrulayın.
6. KAP'ta veya şirkette kararı değiştirecek yeni bir gelişme olup olmadığını kontrol edin.
7. Kaybetmeyi göze aldığınız tutara göre adet belirleyin; plansız işlem açmayın.

## Kararlar ne anlama gelir?

- **BUGÜN AL:** Programın zorunlu filtreleri mevcut veride geçilmiştir. Bu ifade
  doğrudan emir değildir; güncel fiyat, veri, KAP ve kişisel risk kontrolü yine yapılır.
- **ALIM BÖLGESİNİ BEKLE / İZLE:** Fiyat uygun bantta değildir veya teyit henüz
  tamamlanmamıştır. Yükselişi kovalamak yerine koşulun oluşması beklenir.
- **ALMA / RİSKLİ / VERİ KONTROLÜ GEREKLİ:** Yeni pozisyon açılmaz. Veri veya piyasa
  koşulları düzelmeden aday yeniden değerlendirilmez.

## İşlemden önce yedi kontrol

### 1. Veri güncel ve güvenilir mi?

Veri tarihi bugüne veya son işlem gününe ait olmalıdır. Eski, eksik ya da güvenilmez
veriyle işlem açılmaz. Uygulamadaki fiyat gecikmeli olabilir; emir fiyatı aracı kurum
ekranından doğrulanır.

### 2. Fiyat hâlâ alış bandında mı?

Güncel fiyat **Önerilen Alış Alt–Üst** bandının dışına çıktıysa eski sinyal takip
edilmez ve yükseliş kovalanmaz. Fiyatın banda dönmesi yeni verilerle tekrar değerlendirilir.

### 3. Stop nerede?

Stop, işlemin yanlış çıktığının kabul edileceği seviyedir. İşlemden önce belirlenir.
Zararı büyütmek amacıyla stop aşağı taşınmaz. Gap ve likidite nedeniyle gerçekleşen
zararın planlanandan büyük olabileceği unutulmaz.

### 4. Risk/getiri yeterli mi?

Hedef potansiyeli tek başına yeterli değildir. Olası kazanç ile stop mesafesi birlikte
karşılaştırılır. Program güçlü onay listesinde `1,8` ve üzeri risk/getiri oranını daha
seçici bir referans olarak kullanır; bu oran başarı garantisi değildir.

### 5. Pozisyon büyüklüğü uygun mu?

Koruyucu bir örnek olarak tek işlemde toplam portföyün en fazla `%0,5–%1`'i riske atılır:

```text
Risk tutarı = Portföy değeri × Risk yüzdesi
Hisse başına risk = Alış fiyatı − Stop fiyatı
Azami adet = Risk tutarı ÷ Hisse başına risk
```

Örnek: 100.000 TL portföyde `%0,5` risk, 50 TL alış ve 48 TL stop için risk tutarı
500 TL, hisse başına risk 2 TL ve azami adet 250'dir. Komisyon, fiyat kayması, toplam
nakit ve hissenin likiditesi ayrıca dikkate alınır.

### 6. Birden fazla kanıt aynı yönde mi?

Trend, momentum, hacim, piyasa ve sektör yönü, temel görünüm ve KAP birlikte okunur.
Tek bir gösterge veya yüksek bir hedef işlem gerekçesi değildir. Model olasılığı
geçmiş örneklere dayalı tahmindir; kesin gerçekleşme ihtimali değildir. Yeterli örnek
yoksa programın “bilinmiyor” göstermesi güvenlik davranışıdır.

### 7. Vade ve çıkış planı belli mi?

Günlük Trade aynı gün yakın takip ister. Kısa ve orta vadenin hedefleri, stopları ve
bekleme süreleri birbirine karıştırılmaz. İşlemden önce şu üç cevap yazılı olmalıdır:

- Neden alıyorum?
- Hangi koşulda zarar kesiyorum?
- Hangi hedefte veya hangi koşul bozulduğunda çıkıyorum?

## İşlem açmamanız gereken durumlar

- Borçla veya kısa sürede ihtiyaç duyulacak parayla yatırım yapmak
- Eski, eksik ya da güvenilmez veriye dayanmak
- Stop belirlemeden yalnız hedef fiyata bakmak
- Sosyal medya söylentisini doğrulamadan karar vermek
- Zarar eden pozisyona plansız biçimde ekleme yapmak
- Aynı sektörde çok sayıda hisse alarak riski tek yere yığmak
- Fiyat alış bandından uzaklaştığı hâlde yükselişi kovalamak
- Panik, acele veya “kaçırma korkusu” ile planı bozmak

## Her işlem için kısa kayıt

İşlem günlüğüne tarih, hisse, vade, alış, stop, hedef, adet, işlem nedeni ve sonucu
yazılması önerilir. Sonuçlar en az 20–30 işlemden sonra birlikte incelenmeli; tek bir
kazanç veya kayıp sistemin başarısı olarak yorumlanmamalıdır.

## Son uyarı

Yatırım kararının uygunluğu; gelir, borç, likidite ihtiyacı, vade ve kayıp toleransına
göre kişiden kişiye değişir. Gerektiğinde SPK lisanslı bir yatırım danışmanından destek alın.
