# Terminal-Bench 2 resmi Codex smoke sonucu

Bu koşu, Harbor'ın resmi Terminal-Bench 2 görevlerinden `adaptive-rejection-sampler`
üzerinde yapıldı. Jev görevi önce Terra olarak sınıflandırdı; yüksek belirsizlik koruması
seçimi Sol'e yükseltti. İşçi model `gpt-5.6-sol`, kullanıcının yerel Codex
`auth.json` oturumuyla Harbor container'ında çalıştı. OpenRouter'a işçi model çağrısı
gönderilmedi.

- Resmi Harbor sonucu: **1.0 / geçti**
- Tamamlanan görev: **1/1**
- İstisna: **0**
- Süre: **10 dakika 2 saniye**
- Codex giriş tokenı: **513.628**
- Önbellekten gelen giriş tokenı: **480.000**
- Codex çıkış tokenı: **15.455**
- Jev yönlendirme maliyeti: **$0.000058758**

Harbor'ın sonuç dosyasındaki `$0.635612`, model tarifesinden hesaplanan karşılaştırmalı
bir maliyet alanıdır; çağrı Codex abonelik kimliğiyle yapıldığı için OpenRouter/API
faturası değildir. Bu tek görev router zincirinin uçtan uca çalıştığını kanıtlar, fakat
89 görevlik Terminal-Bench 2 başarı oranını tahmin etmek için tek başına yeterli değildir.
