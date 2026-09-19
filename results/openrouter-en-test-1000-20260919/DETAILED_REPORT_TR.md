# Ayrıntılı Canlı Benchmark Analizi

- Örnek: 1000
- Gerçek benzersiz çağrı: 2000 hedef + 1000 Jev
- Ledger harcaması: $0.380064
- Kalibrasyon dahil toplam harcama: $0.458076
- Birincil eşik: 0.02
- Analiz rolü: kilitli test

## Ana hüküm

Jev yolu Sol'a göre **4.50 yüzde puan** kalite kaybetti ve **%62.3** politika maliyeti tasarrufu sağladı. Önceden tanımlı ≤2 yüzde puan kalite kaybı hedefi **GEÇMEDİ**.
Uçtan uca p50 Jev gecikmesi 1516 ms; Sol 1336 ms ve Luna 1026 ms. Jev yönlendirme p50 ek yükü 439 ms.

## Politika sonuçları

| Politika | Doğruluk | %95 Wilson GA | Sol'a fark | Güçlü oranı | Politika maliyeti | Tasarruf | p50 / p95 gecikme |
|---|---:|---:|---:|---:|---:|---:|---:|
| always_strong | 94.20% | [92.58%, 95.49%] | +0.00 yp | 100.00% | $0.317286 | 0.00% | 1336 / 2186 ms |
| always_cheap | 83.90% | [81.49%, 86.05%] | -10.30 yp | 0.00% | $0.032876 | 89.64% | 1026 / 1539 ms |
| rule | 83.90% | [81.49%, 86.05%] | -10.30 yp | 0.20% | $0.033547 | 89.43% | 1027 / 1539 ms |
| random_matched | 85.80% | [83.50%, 87.83%] | -8.40 yp | 19.40% | $0.087420 | 72.45% | 1056 / 1688 ms |
| jev | 89.70% | [87.66%, 91.43%] | -4.50 yp | 19.20% | $0.119628 | 62.30% | 1516 / 2198 ms |

## Yönlendirme hata anatomisi

- İki model de doğru: 832
- Yalnız Sol doğru: 110
- Yalnız Luna doğru: 7
- İkisi de yanlış: 51
- Jev Luna seçti ve yalnız Sol doğruydu: 47
- Jev Sol seçerek Luna hatasını kurtardı: 63
- Jev Sol seçti ama Luna da doğruydu: 96
- Jev servis hatası sonrası güvenli Sol fallback: 1
- Güçlü-gereksinim sınıflandırması precision/recall: 32.81% / 57.27%.
- Kusursuz karşı-olgusal seçici üst sınırı: kalite 94.90%, hedef maliyeti $0.061908; aynı Jev ek yüküyle $0.091811.

## Görev ailesi kırılımı

| Grup | n | Sol | Luna | Jev | Jev maliyeti | Jev p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|
| arc_challenge_science | 250 | 99.20% | 96.00% | 96.00% | $0.014983 | 1471 / 1917 ms |
| belebele_reading | 250 | 96.80% | 94.40% | 94.80% | $0.020716 | 1471 / 2049 ms |
| global_mmlu_business | 41 | 95.12% | 80.49% | 92.68% | $0.006880 | 1544 / 2535 ms |
| global_mmlu_humanities | 42 | 88.10% | 83.33% | 88.10% | $0.014124 | 1614 / 2209 ms |
| global_mmlu_medical | 42 | 92.86% | 83.33% | 83.33% | $0.005724 | 1495 / 2380 ms |
| global_mmlu_other | 41 | 92.68% | 87.80% | 90.24% | $0.003319 | 1487 / 1976 ms |
| global_mmlu_social_sciences | 42 | 90.48% | 88.10% | 88.10% | $0.004777 | 1466 / 3056 ms |
| global_mmlu_stem | 42 | 95.24% | 78.57% | 80.95% | $0.006171 | 1474 / 1970 ms |
| gsm8k_math | 250 | 88.40% | 61.60% | 80.80% | $0.042932 | 1672 / 2459 ms |

## İstatistik ve olasılık kalibrasyonu

- Jev−Sol eşleştirilmiş bootstrap %95 GA: [-5.90, -3.20] yüzde puanı.
- Jev/Sol McNemar iki yönlü p: 4.35563e-12.
- Jev−rastgele-eşleşmiş eşleştirilmiş bootstrap %95 GA: [+2.40, +5.50] yüzde puanı.
- Jev güçlü-gereksinim olasılığı Brier skoru: 0.1013; ECE: 0.0955.
- Bu veri üzerinde ≤2 yp kayıp şartıyla tanısal en düşük maliyetli eşik: 0.00; kalite 94.20%, güçlü oranı 100.00%, maliyet $0.347188.

Eşik eğrisi test koşusunda yalnız tanısaldır; birincil test sonucunu değiştirmek için kullanılmaz.

## Ayrı kalibrasyon koşusu

200 dev sorusunda seçilen eşik 0.02; dev kalitesi 89.50%, Sol'a kayıp 1.50 yp, güçlü kullanım 21.00%. Bu eşik kilitli test başlamadan önce donduruldu.
