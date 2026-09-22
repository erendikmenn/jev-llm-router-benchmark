# Balanced v2 — 100 görevlik SWE-bench Verified kapısı

Tarih: 2026-09-22

Politika commit'i: `5c56cff`

Truth source: resmî SWE-bench evaluator

## Kısa hüküm

Yeni senaryo gerçekten denendi. Sistem artık Jev'nin yalnız “daha fazla inceleme iyi
olur” demesiyle Sol'a gitmiyor. Önce Luna çalışıyor; Sol yalnız somut worker/verifier
hatası, yüksek risk kapısı veya çok güçlü görünür kusur sinyalinde çağrılıyor.

100 kilitli görevde nihai sonuç **74/100 resolved** oldu. 87 görev yalnız Luna ile,
13 görev Luna + Sol ile tamamlandı. İki görevlik smoke'taki `%100` Sol oranı `%13`'e
indi; ortalama süre `8,64 dk`dan bağımsız 100 görev örneğinde `3,88 dk`ya indi.

Ancak router henüz “wow” seviyesinde değildir. Kaydedilmiş ilk Luna patch'leri de
resmî evaluator ile puanlandığında Sol'un 13 çağrıdan yalnız birinde başarısız patch'i
başarılı hale getirdiği görüldü. On bir Luna patch'i zaten doğruydu; bir başarısız
patch'i de Sol kurtaramadı. Balanced politika bu nedenle Luna-only karşı-olgusuna göre
yalnız `+1` puan kalite sağladı (`73% -> 74%`) fakat 13 ek güçlü-model turu satın aldı.

## Ana sonuçlar

| Ölçüm | Sonuç |
|---|---:|
| Resmî olarak değerlendirilen görev | 100 |
| Resolved | **74** |
| Unresolved | 26 |
| Evaluator / altyapı hatası | **0** |
| Boş patch | **0** |
| Luna-only görev | 87 |
| Sol'a yükselen görev | 13 |
| Worker turu | 113 |
| Ortalama uçtan uca worker süresi | **3,88 dk** |
| Medyan | **3,05 dk** |
| p95 | **10,95 dk** |
| Seri toplam worker süresi | 6,46 saat |
| Input token | 76.498.957 |
| Cached input token | 70.379.520 |
| Output token | 647.113 |
| Reasoning output token | 237.091 |
| OpenRouter Jev maliyeti | **$0,056379** |

Codex worker turları kullanıcının yerel Codex oturumuyla çalıştı; bunlar OpenRouter API
faturası değildir. OpenRouter'a bu koşuda yalnız Jev review istekleri gitti.

## İki kere model neden çağrılıyor?

Eski davranışta Luna patch ürettikten sonra Jev `accept` dışındaki hemen her kararda
pipeline Sol'a geçiyordu. Bu nedenle iki görevlik smoke'ta iki görev de iki tam worker
turu yaptı ve ortalama `8,64 dk` sürdü.

Balanced v2'de belirsizlik tek başına escalation değildir. Buna rağmen 100 görevde 13
ikinci tur oluştu:

- 11 görev statik `high_stakes_change` kapısına takıldı;
- 2 görevde Jev görünür eksikliği çok güçlü işaretledi;
- kalan 87 görev tek turda kapandı.

Tek Luna turu ortalama `3,02 dk`, Sol'a çıkan görev ise ortalama `9,60 dk` sürdü.
Yani yüksek ortalamanın ana nedeni Jev latency'si değil, ikinci modelin repository'yi
yeniden inceleyip test çalıştırdığı tam kodlama turudur.

## Luna ve Sol katkısı

| Grup | Resolved | Ortalama süre | Input token | Output token |
|---|---:|---:|---:|---:|
| Luna-only final | 62/87 (`%71,3`) | 3,02 dk | 53.464.260 | 470.002 |
| Sol'a yükselen final | 12/13 (`%92,3`) | 9,60 dk | 23.034.697 | 177.111 |
| Sol'a yükselenlerin ilk Luna patch'i | 11/13 (`%84,6`) | — | — | — |

13 yükseltmenin görev bazlı karşı-olgusu:

- `astropy__astropy-13236`: Luna başarısız, Sol başarılı — **gerçek kurtarma**;
- `django__django-15732`: Luna başarısız, Sol da başarısız;
- diğer 11 görev: Luna zaten başarılı, Sol final de başarılı;
- Luna'nın doğru patch'ini bozan Sol örneği yok.

Sonuç: risk kapısı zor/önemli görevleri ayırıyor, fakat “Sol kaliteyi artıracak mı?”
sorusunu iyi ayırmıyor. 13 çağrının yalnız `1/13`ü (`%7,7`) gözlenen kalite artışı
üretti; `11/13` çağrı resmî sonuca göre gereksizdi.

## Luna-only karşı-olgusu

Bütün görevlerde yalnız kaydedilmiş ilk Luna patch'i kullanılsaydı:

| Ölçüm | Luna ilk tur | Balanced final | Fark |
|---|---:|---:|---:|
| Resolved | 73/100 | 74/100 | **+1 puan** |
| Ortalama süre | 2,94 dk | 3,88 dk | +0,94 dk |
| Input token | 60.584.163 | 76.498.957 | +15.914.794 |
| Output token | 528.869 | 647.113 | +118.244 |
| Jev maliyeti | $0,049694 | $0,056379 | +$0,006685 |

Balanced finalden Sol turları çıkarıldığında aynı örnekte süre yaklaşık `%24,2`, input
`%20,8`, output `%18,3` azalır; kalite ise yalnız bir puan düşer. Bu, mevcut escalation
kapısının ekonomik olarak hâlâ fazla geniş olduğunu gösterir.

## Jev sinyali kaliteyi ayırıyor mu?

İlk Luna patch'inin resmî sonucu ile Jev'nin ilk kararı karşılaştırıldı:

| İlk Jev kararı | Görev | Luna patch resolved |
|---|---:|---:|
| `accept` | 26 | 19 (`%73,1`) |
| `escalate` | 42 | 31 (`%73,8`) |
| `revise` | 32 | 23 (`%71,9`) |

Üç grup neredeyse aynı. Dolayısıyla Jev'nin mevcut semantik `accept/revise/escalate`
çıktısı bu veri üzerinde patch doğruluğunu ayırmıyor. Balanced v2'nin iyileşmesi Jev
skor kalibrasyonundan değil, belirsizlik sinyallerini ikinci worker çağrısından ayıran
deterministik politikadan geldi.

## Repository dağılımı

| Repository | Görev | Resolved | Sol |
|---|---:|---:|---:|
| astropy | 5 | 4 | 1 |
| django | 48 | 35 | 12 |
| matplotlib | 9 | 4 | 0 |
| pydata/xarray | 3 | 2 | 0 |
| pytest | 3 | 3 | 0 |
| scikit-learn | 9 | 9 | 0 |
| sphinx | 11 | 7 | 0 |
| sympy | 12 | 10 | 0 |

`high_stakes_change` kuralı özellikle Django `auth` yolları nedeniyle 12/13 Sol
çağrısını Django'ya yoğunlaştırdı. Matplotlib'deki `4/9` sonuç ise kalite kaybının başka
bir kaynağı olduğunu, mevcut router'ın bu zorluk tipini yakalamadığını gösteriyor.

## Protokol ve dürüst sınırlamalar

- Plan önceden kilitlenmiş SWE-bench Verified test bölümündeki 100 görevi kullandı.
- Worker'a gold patch, test patch, FAIL_TO_PASS veya evaluator sonucu verilmedi.
- Modelin kendi yazdığı testler truth source sayılmadı; final etiket resmî evaluator'dır.
- Resmî registry evaluator image'ları `linux/amd64` olarak çekildi. Yerel task-repo
  rebuild denemesi tek image'da 13,2 GB cache ürettiği ve diski dolduracağı için
  durduruldu; yarım sonuç nihai rapora katılmadı.
- Nihai evaluator koşusunda 100/100 tamamlandı, hata ve belirsiz altyapı sonucu sıfır.
- Bu tek bir stochastic model koşusudur. Aynı 100 görev üzerinde eşik ayarlayıp tekrar
  puanlamak test setine overfit olur; bu sonuç bundan sonra kilitli tutulmalıdır.
- Paired always-Sol 100 koşusu yapılmadığı için “Sol'a göre X dolar ucuz” iddiası bu
  rapordan çıkarılamaz. Ölçülen gerçek kazanım 87 Sol çağrısının hiç yapılmamasıdır.

## Karar

Test kapısı teknik olarak geçti: sistem 100 görevi eksiksiz üretti, resmî evaluator
100'ünü de hatasız puanladı ve routing davranışı ölçülebildi. Ürün kapısı ise henüz
geçmedi:

- `%74` kalite güçlü bir başlangıçtır ama hedeflenen kalite-first seviye için yeterli
  olduğuna dair paired güçlü-model baseline yoktur;
- Sol oranı `%13` ile ekonomik açıdan makuldür;
- buna rağmen Sol'un gözlenen kalite katkısı yalnız `+1` puandır;
- Jev kararları doğru/yanlış patch'i ayırmıyor;
- 25 Luna-only yanlış sonuç, mevcut sistemin görünmeyen hataları yakalayamadığını
  gösteriyor.

Sonraki sürüm aynı test setine göre ayarlanmamalı. Yeni bir dev/kalibrasyon kümesinde
şunlar yapılmalı: Jev için “görünür somut kusur” etiketi kalibre edilmeli, statik
`high_stakes_change` kalite escalation'ından operasyonel review'a ayrılmalı ve bağımsız
verifier/trajectory kanıtı eklenmeli. Eşikler dondurulduktan sonra yeni bir held-out
kapıda veya paired always-Sol örneğinde doğrulanmalıdır.

Makine çıktıları: [`summary.json`](summary.json), [`generation-summary.json`](generation-summary.json),
[`evaluation.json`](evaluation.json), [`analysis.json`](analysis.json) ve ilk-tur
karşı-olgusu [`round1-luna/evaluation.json`](round1-luna/evaluation.json).
