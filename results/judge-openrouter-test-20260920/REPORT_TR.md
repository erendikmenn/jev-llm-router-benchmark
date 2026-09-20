# Jev code judge benchmarkı

- Mod: `live`
- Vaka: 28
- Dört-sınıf doğruluk: %71.4
- Unsafe false-pass: 0 (%0.0)
- Riskli/hatalı vakayı reddetme recall: %100.0
- Accept precision: %100.0
- Geçerli değişikliği accept recall: %28.6
- Escalation/block recall: %78.6
- Provider hatası: 0
- Toplam maliyet: $0.001196
- Vaka başı maliyet: $0.000043
- Latency mean / p50 / p95: 513 / 521 / 648 ms

## Yorum

Bu sentetik set pipeline ve ilk Jev kalibrasyonu içindir; gerçek repository doğruluğu iddiası değildir.
Birinci güvenlik metriği, hatalı/riskli değişikliklerin yanlışlıkla `accept` edilmesidir.
Bir sonraki aşamada aynı protokol bağımsız hidden test sonucu bulunan SWE-bench Verified görevlerine uygulanmalıdır.
