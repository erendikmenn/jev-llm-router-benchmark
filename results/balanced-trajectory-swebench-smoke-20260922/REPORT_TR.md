# Balanced trajectory — SWE-bench Verified test katmanı

Tarih: 2026-09-22

Kapsam: 2 geliştirme görevi

Truth source: resmî SWE-bench evaluator

## Kısa hüküm

Kalite iyi, routing ekonomisi başarısız çıktı.

- Nihai balanced patch'ler resmî evaluator'da **2/2 resolved**.
- İki görev de Luna ile başladı fakat ikisi de Sol'a yükseltildi: **Sol oranı %100**.
- Jev hiçbir son patch'e otomatik accept vermedi: **accept 0/2**.
- Kaydedilmiş ilk Luna patch'leri ayrıca değerlendirildi ve onlar da **2/2 resolved**.
- Dolayısıyla bu iki görevde iki Sol turu da gereksizdi.

Bu sonuç “balanced başarılı” demek değildir. Worker kalitesi bu örnekte yeterliydi;
darboğaz Jev'nin doğru Luna patch'ini güvenle kabul edememesidir.

## Ana tablo

| Kol | Resolved | Sol'a giden görev | Ort. süre | Input token | Output token | Jev maliyeti |
|---|---:|---:|---:|---:|---:|---:|
| Always Luna, eski bağımsız koşu | 0/2 | 0/2 | 4,00 dk | 2.521.790 | 16.218 | $0 |
| Always Sol, eski bağımsız koşu | 1/2 | 2/2 | 7,05 dk | 3.222.345 | 32.197 | $0 |
| Eski router + judge | 2/2 | 2/2 | 11,22 dk | 4.376.610 | 41.011 | $0,003729 |
| Yeni balanced final | 2/2 | 2/2 | 8,64 dk | 3.778.507 | 27.853 | $0,002831 |
| İlk Luna patch'i — oracle karşı-olgusu | 2/2 | 0/2 | 2,91 dk | 2.239.997 | 11.376 | $0,001263 |

Yeni balanced, eski router+judge'a göre aynı 2/2 kaliteyle yaklaşık `%23` daha kısa
ve `%13,7` daha az input token kullandı. Ancak asıl hedef always-Sol'a göre tasarruftu;
bu kapıyı geçmedi: süre `%22,6`, input token `%17,3` daha yüksek oldu.

İlk Luna patch'lerini doğru biçimde kabul edebilen bir oracle politika ise 2/2 kaliteyi
korurken always-Sol'a göre yaklaşık `%58,6` daha kısa, `%30,5` daha az input ve `%64,7`
daha az output token kullanmış olacaktı. Bu yalnız karşı-olgusal üst sınırdır; online
router bu etiketi önceden bilmiyordu.

## Görev bazında

### `sphinx-doc__sphinx-10323`

- Luna ilk patch: resmî evaluator `resolved`.
- Jev: `needs_deep_review=0,85`; `deep_review_requested` ile Sol'a yükseltti.
- Sol final patch: resmî evaluator `resolved`.
- Sonuç: kalite korundu, Sol turu gereksizdi.

### `sympy__sympy-21379`

- Luna ilk patch: resmî evaluator `resolved`.
- Jev: `requirements_complete=0,54`; `clearly_incomplete_requirements` ile revise dedi.
- Sol final patch: resmî evaluator `resolved`; Jev yine accept vermedi.
- Sonuç: judge'ın requirements sinyali resmî sonuçla ters düştü, Sol turu gereksizdi.

## Neyi doğruladık?

- Balanced arm task-router çağırmadan Luna ile başlayabiliyor.
- Her tur patch'i ayrı kaydediliyor ve sonradan resmî evaluator ile karşı-olgusal olarak
  ölçülebiliyor.
- Gold patch, test patch ve FAIL_TO_PASS alanları worker'a verilmedi.
- Gizli evaluator sonucu model turları arasında kullanılmadı.
- İki final patch ve iki ilk-tur patch için evaluator/infra hatası sıfırdı.

## Ne yapmamalıyız?

Bu iki örneğe bakıp Jev eşiklerini doğrudan gevşetmemeliyiz. İki görev istatistiksel
kalibrasyon için yetersizdir ve eski fixed-model kolları bağımsız stochastic koşulardır.
Doğru sonraki adım, 20 görevlik dev katmanında bütün Luna round-one patch'lerini shadow
olarak puanlayıp şu sinyalleri gerçek resolved etiketiyle kalibre etmektir:

- `requirements_complete`;
- `behavior_supported`;
- `needs_deep_review`;
- diff/test değişikliği ve external-verifier bulunup bulunmaması;
- revise/escalate kararının gerçekten Sol ile kurtarıp kurtarmadığı.

Balanced profil ancak dev'de eşik dondurulduktan sonra kilitli test setine geçmelidir.

Makine özetleri: [`summary.json`](summary.json) ve [`analysis.json`](analysis.json).
