# Ayrıntılı Canlı Benchmark Analizi

- Örnek: 200
- Gerçek benzersiz çağrı: 400 hedef + 200 Jev
- Ledger harcaması: $0.078012
- Kalibrasyon dahil toplam harcama: $0.078012
- Birincil eşik: 0.58
- Analiz rolü: yalnız kalibrasyon; test iddiası değildir

## Ana hüküm

Jev yolu Sol'a göre **8.00 yüzde puan** kalite kaybetti ve **%79.5** politika maliyeti tasarrufu sağladı. Önceden tanımlı ≤2 yüzde puan kalite kaybı hedefi **GEÇMEDİ**.
Uçtan uca p50 Jev gecikmesi 1431 ms; Sol 1469 ms ve Luna 954 ms. Jev yönlendirme p50 ek yükü 462 ms.

## Politika sonuçları

| Politika | Doğruluk | %95 Wilson GA | Sol'a fark | Güçlü oranı | Politika maliyeti | Tasarruf | p50 / p95 gecikme |
|---|---:|---:|---:|---:|---:|---:|---:|
| always_strong | 91.00% | [86.22%, 94.23%] | +0.00 yp | 100.00% | $0.065218 | 0.00% | 1469 / 3427 ms |
| always_cheap | 83.50% | [77.73%, 88.00%] | -7.50 yp | 0.00% | $0.006770 | 89.62% | 954 / 1457 ms |
| rule | 83.50% | [77.73%, 88.00%] | -7.50 yp | 0.50% | $0.007840 | 87.98% | 956 / 1457 ms |
| random_matched | 83.50% | [77.73%, 88.00%] | -7.50 yp | 0.50% | $0.007251 | 88.88% | 956 / 1457 ms |
| jev | 83.00% | [77.18%, 87.57%] | -8.00 yp | 1.00% | $0.013392 | 79.47% | 1431 / 1943 ms |

## Yönlendirme hata anatomisi

- İki model de doğru: 162
- Yalnız Sol doğru: 20
- Yalnız Luna doğru: 5
- İkisi de yanlış: 13
- Jev Luna seçti ve yalnız Sol doğruydu: 20
- Jev Sol seçerek Luna hatasını kurtardı: 0
- Jev Sol seçti ama Luna da doğruydu: 2
- Güçlü-gereksinim sınıflandırması precision/recall: 0.00% / 0.00%.
- Kusursuz karşı-olgusal seçici üst sınırı: kalite 93.50%, hedef maliyeti $0.012817; aynı Jev ek yüküyle $0.018841.

## Görev ailesi kırılımı

| Grup | n | Sol | Luna | Jev | Jev maliyeti | Jev p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|
| arc_challenge_science | 50 | 92.00% | 94.00% | 94.00% | $0.002852 | 1451 / 1764 ms |
| belebele_reading | 50 | 94.00% | 92.00% | 92.00% | $0.003903 | 1417 / 1985 ms |
| global_mmlu_business | 9 | 66.67% | 77.78% | 77.78% | $0.000565 | 1316 / 1823 ms |
| global_mmlu_humanities | 8 | 87.50% | 62.50% | 62.50% | $0.000785 | 1313 / 3354 ms |
| global_mmlu_medical | 8 | 87.50% | 87.50% | 87.50% | $0.000435 | 1271 / 1609 ms |
| global_mmlu_other | 9 | 100.00% | 88.89% | 88.89% | $0.000467 | 1405 / 1850 ms |
| global_mmlu_social_sciences | 8 | 100.00% | 100.00% | 100.00% | $0.000463 | 1360 / 1504 ms |
| global_mmlu_stem | 8 | 100.00% | 75.00% | 75.00% | $0.000782 | 1339 / 2655 ms |
| gsm8k_math | 50 | 88.00% | 66.00% | 64.00% | $0.003141 | 1470 / 1843 ms |

## İstatistik ve olasılık kalibrasyonu

- Jev−Sol eşleştirilmiş bootstrap %95 GA: [-13.00, -3.50] yüzde puanı.
- Jev/Sol McNemar iki yönlü p: 0.00154388.
- Jev−rastgele-eşleşmiş eşleştirilmiş bootstrap %95 GA: [-1.50, +0.00] yüzde puanı.
- Jev güçlü-gereksinim olasılığı Brier skoru: 0.0966; ECE: 0.0968.
- Bu veri üzerinde ≤2 yp kayıp şartıyla tanısal en düşük maliyetli eşik: 0.02; kalite 89.50%, güçlü oranı 21.00%, maliyet $0.025805.

Eşik eğrisi test koşusunda yalnız tanısaldır; birincil test sonucunu değiştirmek için kullanılmaz.
