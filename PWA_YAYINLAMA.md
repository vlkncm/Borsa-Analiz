# iPhone PWA sürümü

Bu sürüm grafik içermez. Fiyat geçmişini alır; EMA, RSI, MACD, ATR, destek, direnç, hedef ve stop hesaplarını iPhone üzerinde yapar. Takip listesi yalnızca cihazın yerel depolamasında tutulur.

## Cloudflare üzerinde yayımlama

1. Bir Cloudflare hesabıyla terminalde `npx wrangler login` komutunu çalıştırın.
2. Proje klasöründe `npx wrangler deploy` komutunu çalıştırın.
3. Komutun verdiği `https://...workers.dev` adresini iPhone Safari'de açın.
4. Safari'de **Paylaş > Ana Ekrana Ekle** seçeneğine dokunun.

Yerel önizleme için `npx wrangler dev` kullanılabilir.

Yahoo Finance bu projede geçici/yardımcı veri kaynağıdır. Ticari veya yoğun kullanım öncesinde lisanslı BIST veri servisine geçilmelidir.
