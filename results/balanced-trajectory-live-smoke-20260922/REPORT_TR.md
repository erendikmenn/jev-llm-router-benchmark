# Balanced trajectory — gerçek Codex + Jev smoke

Tarih: 2026-09-22

## Basit sonuç

Akış gerçek servislerle çalıştı ve kolay görevi Sol'a gitmeden tamamladı:

```text
sentetik Git görevi
  → Luna (yerel Codex kimliği)
  → 2/2 bağımsız unittest geçti
  → Jev accept
  → tamamlandı; Sol çağrısı yok
```

| Ölçüm | Sonuç |
|---|---:|
| Görev | 1 |
| Son durum | `accepted` |
| Worker | Luna, 1 tur |
| Sol çağrısı | 0 |
| Task öncesi Jev router | çağrılmadı |
| Bağımsız test | 2/2 geçti |
| Luna süresi | 19,39 sn |
| Jev review süresi | 1,23 sn |
| Toplam süre | 20,72 sn |
| Jev/OpenRouter maliyeti | $0,00006279 |
| Luna token | 71.727 input; 54.272 cached; 534 output |

Luna `safe_divide` fonksiyonuna sıfır bölen için `None` davranışını ekledi, normal
bölmeyi korudu ve teste dokunmadı. Yerel verifier iki testi geçirdi. Jev
`requirements_complete=0,97`, `scope_aligned=0,96`, `behavior_supported=0,82` ile
`accept` kararı verdi.

Worker yerel Codex hesabını kullandı; yukarıdaki USD yalnız Jev'nin OpenRouter
çağrısıdır. Codex worker'ı için sahte bir API maliyeti yazılmamıştır.

## İlk denemede bulunan gerçek hata

İlk koşuda Luna'nın çözümü doğruydu ve testler geçti. Ancak testin ürettiği
`__pycache__/*.pyc` dosyaları progress collector tarafından scope değişikliği sayıldı.
Jev `scope_misaligned` dedi, pipeline gereksiz yere Sol'a gitti ve ikinci review de
fazla muhafazakâr kaldı. Sonuç `needs_human_review`, süre 84,46 sn ve Jev maliyeti
$0,000126 oldu.

Collector düzeltildi: generated cache, binary artefakt ve benzeri non-source path'ler
diff/progress/review paketinden çıkarılıyor; receipt yalnız kaç tanesinin dışlandığını
tutuyor. Aynı görev temiz bir workspace'te yeniden çalıştırıldığında yukarıdaki tek
tur kabul sonucu alındı.

Bu bulgu yaklaşımın ana fikrini de doğruluyor: model kararından önce evidence kalitesi
doğru olmalı; gürültülü dosya listesi iyi bir worker sonucunu gereksiz escalation'a
dönüştürebilir.

## Sınır

Bu `n=1` sentetik entegrasyon smoke'udur. Balanced profilin V0.01'den daha kaliteli,
ucuz veya hızlı olduğunu kanıtlamaz; always-Sol paired kolu da çalıştırılmadı. Ürün
iddiası için planlanan yeni held-out LiveCodeBench ve repository benchmarkları gerekir.

Makine özeti: [`summary.json`](summary.json).
