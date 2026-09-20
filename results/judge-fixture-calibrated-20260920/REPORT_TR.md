# Jev code judge benchmarkı

- Mod: `fixture`
- Vaka: 40
- Dört-sınıf doğruluk: %100.0
- Unsafe false-pass: 0 (%0.0)
- Riskli/hatalı vakayı reddetme recall: %100.0
- Accept precision: %100.0
- Geçerli değişikliği accept recall: %100.0
- Escalation/block recall: %100.0
- Provider hatası: 0
- Toplam maliyet: $0.001919
- Vaka başı maliyet: $0.000048
- Latency mean / p50 / p95: 198 / 198 / 213 ms

## Yorum

Bu sentetik set pipeline ve ilk Jev kalibrasyonu içindir; gerçek repository doğruluğu iddiası değildir.
Birinci güvenlik metriği, hatalı/riskli değişikliklerin yanlışlıkla `accept` edilmesidir.
Bir sonraki aşamada aynı protokol bağımsız hidden test sonucu bulunan SWE-bench Verified görevlerine uygulanmalıdır.
