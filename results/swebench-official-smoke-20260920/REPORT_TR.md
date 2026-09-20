# SWE-bench Verified Codex router + judge smoke sonucu

Tarih: 20 Eylül 2026  
Kapsam: 2 geliştirme görevi × 6 deney kolu  
Durum: altyapı ve ürün davranışı smoke testi; genel başarı oranı değildir

## Kısa sonuç

Router mimarisi teknik olarak çalışıyor: resmî görevleri sabit commit'te checkout ediyor, yalnız problem metnini Codex'e veriyor, patch'i yakalıyor ve resmî SWE-bench evaluator ile bağımsız olarak puanlıyor. Gold patch doğrulaması 1/1 geçti; 12 model/pipeline sonucu boyunca evaluator veya altyapı hatası olmadı.

İki görevde gözlenen en ucuz başarılı model Terra oldu. Jev bir görevde Terra'yı doğru seçti, diğerinde gereksiz biçimde Sol'u seçti. Under-routing görülmedi. Router-only iki görevin birini çözdü. Router+judge iki görevi de çözdü; ancak geçen iki son patch'in ikisini de `needs_human_review` durumunda bıraktı. Dolayısıyla judge küçük örnekte kaliteyi düşürmedi, fakat otomatik kabul verimliliği kötü ve ek tur maliyeti yüksek.

Bu sonuçlarla “router başarıyla kanıtlandı” denemez. `n=2` yalnız gerçek repository, gerçek patch ve resmî gizli test zincirinin doğru çalıştığını ve hangi hata türlerini ölçmemiz gerektiğini gösterir.

## Resmî sonuçlar

| Kol | Resolved | Ortalama süre | Input / output token | Jev maliyeti |
|---|---:|---:|---:|---:|
| Always Luna | 0/2 | 4.00 dk | 2,521,790 / 16,218 | $0 |
| Always Terra | 2/2 | 8.82 dk | 2,706,120 / 23,513 | $0 |
| Always Sol | 1/2 | 7.05 dk | 3,222,345 / 32,197 | $0 |
| Always Astra | 2/2 | 2.62 dk | 893,080 / 6,887 | $0 |
| Jev router-only | 1/2 | 6.66 dk | 3,011,063 / 22,890 | $0.000129 |
| Jev router + judge | 2/2 | 11.22 dk | 4,376,610 / 41,011 | $0.003729 |

Süre ve token sayıları gerçek Codex CLI receipt'leridir. Codex çağrıları kullanıcının mevcut Codex kimliği/kullanım hakkıyla çalıştı; OpenRouter hedef-model API çağrısı yapılmadı ve bunlara hayalî API USD fiyatı yazılmadı. USD sütunu yalnız OpenRouter'a giden Jev route/review kararlarını içerir.

## Görev bazında

### `sphinx-doc__sphinx-10323`

- Gold evaluator smoke: resolved, 0 infra/evaluator hatası.
- Luna: başarısız.
- Terra: başarılı.
- Sol: başarısız.
- Astra: başarılı.
- Gözlenen en ucuz başarılı tier: Terra.
- Jev seçimi: Terra; `exact`.
- Router-only'nin bağımsız Terra koşusu: başarısız.
- Router+judge: Terra → Sol escalation; son patch başarılı.
- Ayrı tek-tur kontrolünde ilk Terra patch'i de başarılıydı; judge yine escalation istedi. Bu görevde ikinci tur gereksizdi.

Agent'ın kendi raporladığı testler burada güvenilir oracle olmadı: router-only “41 passed” bildirdiği halde resmî FAIL_TO_PASS testi başarısız oldu. Bu, bağımsız evaluator'ın neden zorunlu olduğunu doğrudan gösterir.

### `sympy__sympy-21379`

- Luna: başarısız.
- Terra, Sol ve Astra: başarılı.
- Gözlenen en ucuz başarılı tier: Terra.
- Jev seçimi: Sol; `over_routed`.
- Router-only Sol koşusu: başarılı.
- Router+judge: Sol → Astra escalation; son patch başarılı, fakat yine insan incelemesi istedi.

## Routing ölçümü

Router-only kararları üzerinden:

- Oracle kapsamı: 2/2 görev.
- Exact: 1/2.
- Under-routing: 0/2.
- Over-routing: 1/2.
- Uçtan uca resolved: 1/2.

Router'ın “hangi tier?” kararı ile seçilen model çalışmasının başarısı ayrı kavramlardır. İlk görevde tier doğru seçildiği halde bağımsız Terra üretimi başarısız oldu. Agentik modeller stokastik olduğu için daha büyük koşuda tekrarlar veya belirsizlik aralığı gerekir.

## Judge ölçümü

- Son patch resolved: 2/2.
- Unsafe false accept: 0.
- Otomatik accept: 0/2.
- Resolved olduğu halde accept edilmeyen patch: 2/2.
- İki görevde de bir üst modele escalation yapıldı.

Bu aşamada judge güvenli tarafta fakat fazla muhafazakâr. Merge'i tek başına bloklayan kapı olarak kullanmak yerine shadow/advisory modda kalmalı. Resmî evaluator sonucuyla judge kalibrasyonu büyütülmeden otomatik kabul veya otomatik red yetkisi verilmemeli.

## Maliyet

Ana iki-görev matrisinde Jev toplamı `$0.003858` oldu: router-only `$0.000129`, router+judge `$0.003729`. İlk turu ayrıca ölçmek için yapılan tanısal judge tekrarı dahil bu çalışma turundaki Jev harcaması yaklaşık `$0.004536`; `$5` sınırının `%0.1`inden azdır.

Asıl maliyet USD değil Codex kullanım hakkı ve zamandır. Router+judge, router-only'ye göre bu iki görevde yaklaşık `%69` daha yavaş ve yaklaşık `%45` daha fazla input token kullandı. Bu yüzden judge her değişiklikte zorunlu çalışmamalı; risk, belirsizlik veya verifier sinyaline göre seçici olmalı.

## Gizlilik ve sızıntı kontrolü

- Codex'e yalnız `instance_id`, repo, base commit ve problem statement verildi.
- Dataset'teki gold patch, test patch, FAIL_TO_PASS/PASS_TO_PASS alanları plan yüklenirken düşürüldü.
- Resmî evaluator model çalışması bittikten sonra ayrı Docker container'ında koştu.
- Agent'ın yazdığı testler başarı etiketi sayılmadı.
- Jev route isteği problem metnini; judge isteği temizlenmiş, sınırlandırılmış diff ve ilgili kodu OpenRouter'a gönderdi.

## Sabitlenen kaynaklar

- Dataset: `SWE-bench/SWE-bench_Verified` @ `78f471bf655a3137b2e8a75af1501690ec009ec3`
- Harness: [SWE-bench](https://github.com/SWE-bench/SWE-bench) @ `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`
- ARM local task images: [swe-bench-tasks](https://github.com/SWE-bench/swe-bench-tasks) @ `3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d`
- Plan seed: `20260920`; 20 dev + 100 kilitli test hazırlandı.

## Sonraki güvenilir eşik

Bu smoke'tan sonra doğru adım yüzdelere güvenmek değil, aynı protokolü önce 20 dev görevinde çalıştırmaktır. Dev'de routing/judge eşikleri dondurulduktan sonra 100 test görevi bir kez açılmalıdır. Protokolün ürün hedefi: always-Sol'a göre en fazla 3 puan resolved kaybı, en az %40 token azalması, sıfır kritik yanlış kabul ve p50 sürede en fazla %10 kötüleşme. İki görev bu hedeflerin hiçbirini istatistiksel olarak doğrulamaz.
