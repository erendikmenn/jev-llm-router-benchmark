# Codex için benchmark-temelli model router araştırması

Durum: araştırma ve tasarım kararı
Tarih: 2026-09-20
Kapsam: yalnızca **pre-routing**; worker doğrulama, cevap-sonrası cascade ve otomatik yeniden deneme bu sürümün dışında

## Kısa karar

İlk ürün bir “LLM, başka bir LLM seçsin” sistemi olmamalı. Gelen görevi yerelde yapılandırılmış bir görev kartına dönüştüren, daha önce aynı aday modeller üzerinde ölçülmüş başarı/maliyet/süre sonuçlarından her rota için başarı olasılığı çıkaran ve hedef kalite eşiğini karşılayan en ucuz rotayı seçen kalibre edilmiş bir karar motoru olmalı.

Jev faydalı fakat tek başına router olmamalı. Jev hızlı, ucuz ve yapılandırılmış olasılıklar üretmek için uygun; ancak bizim önceki 1.000 soruluk deneyimizde Jev politikasının zor görev seçme precision'ı %32,81, recall'ı %57,27 idi ve Sol'a göre kalite kaybı 4,5 yüzde puandı. Bu sonuç Jev'nin doğrudan karar verici olarak henüz güvenilir olmadığını, buna karşılık ek bir özellik ve güçlü bir baseline olarak değerli olduğunu gösteriyor.

Önerilen karar sırası:

1. Yerel hard guard: güvenlik, veri kaybı, migration, belirsiz kabul kriteri ve çok geniş kapsam gibi durumları doğrudan güçlü rotaya gönder.
2. Yerel görev kartı ve özellik çıkarımı: görev metni + depodan salt-okunur, kod dışına çıkmayan metadata.
3. Her model/efor rotası için kalibre edilmiş `P(success | task)` tahmini.
4. Kalite eşiğini güvenle karşılayan en düşük maliyetli/hızlı rotayı seç.
5. Veri dağılımının dışında veya kararsız örneklerde `abstain` ederek Sol/Astra'ya dön.
6. Yalnız karar ve sonuç metadata'sını kaydet; cevap-sonrası doğrulama daha sonraki sürüme bırak.

## Araştırma kapsamı

Exa ile 26 ayrı aramada 208 sonuç incelendi. Tekrarlanan, ikincil ve pazarlama ağırlıklı sonuçlar elendikten sonra çalışma seti 18 benzersiz birincil/official kaynağa indirildi. Bunların içinde RouteLLM, RouterBench, LLMRouterBench, Agent-as-a-Router, SWE-Router, RouterEval, Arch-Router, Semantic Router, LiteLLM Auto Router, Not Diamond, Jev/OpenRouter ve ana kodlama benchmarklarının resmi kaynakları yer alıyor.

En önemli kaynaklar:

- [RouteLLM makalesi](https://arxiv.org/html/2406.18665v4) ve [resmî açık kaynak deposu](https://github.com/lm-sys/RouteLLM)
- [RouterBench](https://arxiv.org/html/2403.12031v2) ve [resmî deposu](https://github.com/withmartian/routerbench)
- [LLMRouterBench](https://arxiv.org/html/2601.07206v1) ve [resmî deposu](https://github.com/ynulihao/LLMRouterBench)
- [Agent-as-a-Router / CodeRouterBench](https://arxiv.org/html/2606.22902v2) ve [resmî deposu](https://github.com/LanceZPF/agent-as-a-router)
- [SWE-Router](https://arxiv.org/html/2607.00053)
- [RouterEval](https://aclanthology.org/2025.findings-emnlp.208/)
- [Arch-Router](https://arxiv.org/html/2506.16655v1) ve [model kartı](https://huggingface.co/katanemo/Arch-Router-1.5B)
- [Semantic Router threshold optimizasyonu](https://docs.aurelio.ai/semantic-router/user-guide/features/threshold-optimization)
- [LiteLLM Auto Router](https://docs.litellm.ai/docs/auto_router/)
- [Not Diamond custom router eğitimi](https://docs.notdiamond.ai/docs/router-training-quickstart)
- [OpenRouter TypeSafe/Jev entegrasyonu](https://openrouter.ai/docs/guides/community/typesafe-sdk)
- [Jev doğrulamalı cascade örneği](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-verified-cascade)
- [Southbridge Jev entity-resolution deneyi](https://www.southbridge.ai/blog/jev-entity-resolution)
- [SWE-bench Verified](https://www.swebench.com/verified) ve [resmî depo](https://github.com/SWE-bench/SWE-bench/)
- [Terminal-Bench 2](https://github.com/harbor-framework/terminal-bench-2)
- [LiveCodeBench](https://arxiv.org/html/2403.07974v2) ve [resmî depo](https://github.com/LiveCodeBench/LiveCodeBench/)

## Araştırmadan çıkan dersler

### 1. Soru zorluğunu serbestçe tahmin etmek yeterli değil

RouteLLM, router'ı güçlü modelin zayıf modeli yenme olasılığını tahmin eden bir model ve bu olasılığı karara çeviren kalibre edilmiş maliyet eşiği olarak kuruyor. En önemli ders, eşiğin üretim trafiğine benzeyen veride ayarlanması gerektiği; genel bir benchmark eşiğinin yeni dağılımda aynı güçlü-model oranını vermeyeceği.

Agent-as-a-Router'ın kodlama deneyinde güçlü bir LLM'nin yalnız prompta bakarak yaptığı sıfır-atış routing skoru 41,41 iken, aday modellerin görev boyutlarındaki geçmiş başarı istatistikleri eklenince 47,74'e çıkıyor. Makalenin yorumu bizim durumumuzla uyumlu: darboğaz yalnız reasoning kapasitesi değil, aday modeller hakkında görev-özel performans bilgisinin eksikliği.

Sonuç: Router'a “hangi model daha iyi?” diye sormak yerine, ona benchmarklardan ölçülmüş model başarı kayıtlarını öğretmeliyiz.

### 2. Basit router'lar güçlü baseline'dır; karmaşık yöntem otomatik üstün değildir

LLMRouterBench 400 binden fazla model-görev sonucunu, 21 veri setini ve 33 modeli ortak protokolde karşılaştırıyor. Birçok modern ve ticari router'ın basit `Best Single` baseline'ını güvenilir biçimde aşamadığını; farklı yöntemlerin birleşik değerlendirmede birbirine çok yaklaştığını bildiriyor. Embedding backbone'unu büyütmek de sınırlı fark yaratıyor. Aday model sayısı arttıkça kazançlar azalıyor; dikkatli model havuzu seçimi bazen router yönteminden daha önemli.

Sonuç: İlk sürümde ağır bir router LLM eğitmek yerine, TF-IDF/karakter n-gram + yapılandırılmış özelliklerle lojistik regresyon, kNN ve gradient boosting gibi ucuz baseline'ları geçmek zorunlu olmalı. Karmaşıklık ancak kilitli testte ölçülebilir kazanç verirse eklenmeli.

### 3. Kodlama görevinde prompt-only routing'in doğal tavanı var

SWE-Router, aynı issue metninin gerçekte tek satırlık bir typo veya çok modüllü bir refactor çıkabileceğini gösteriyor. Kısmi agent trajectory'si eklendiğinde prompt-only baseline'lardan belirgin biçimde daha iyi sonuç alıyor. Bu araştırma, ileride “birkaç ucuz keşif adımından sonra yeniden route etme” seçeneğini güçlü biçimde destekliyor.

Ancak kullanıcının mevcut kapsamı yalnız ilk router. Bu nedenle v0.1'de model çalıştırmadan elde edilebilen yerel depo sinyallerini kullanacağız: dil, depo büyüklüğü, issue uzunluğu, test altyapısı, stack trace, hedef dosyalar, public API/security/migration kelimeleri ve istenen eylem türü. Kısmi trajectory routing v0.2+ araştırma konusu olarak kalacak.

### 4. “Intent route” ile “en başarılı model route” aynı şey değil

Semantic Router ve Arch-Router, görevi `code_generation`, `debugging`, `security_review` gibi açıklanabilir politikalara ayırmakta güçlü. Arch-Router'ın model eşlemesini politika sınıflandırmasından ayırması iyi bir mühendislik deseni: yeni model geldiğinde sınıflandırıcıyı baştan eğitmeden route→model tablosu değişebilir.

Fakat doğru görev tipini bulmak, o örnekte Luna mı Terra mı Sol mu başarılı olur sorusunu tek başına cevaplamaz. Aynı `bugfix` sınıfında hem kolay hem zor işler vardır.

Sonuç: İki ayrı katman olmalı:

- açıklanabilir `task taxonomy`: görev ne istiyor ve risk nedir;
- benchmark-temelli `capability policy`: bu görev kartında her aday rotanın çözme olasılığı nedir.

### 5. Jev'nin doğru rolü yapılandırılmış sinyal üretmek

Jev/OpenRouter System One API, serbest metin cevap yerine tanımlı `choice`, `score` ve olasılıklar döndürüyor. Hızlı, ucuz ve typed olması router sinyali üretmek için uygun. Southbridge deneyi de Jev'nin dar, iyi tanımlanmış karar sorularında etkili olduğunu; fakat tek başına kullanıldığında doğruluğun belirgin düştüğünü ve seyrek güçlü inceleme ile toparlandığını gösteriyor.

Bizim router'da Jev için doğru soru “model seç” olmaktan ziyade paralel, dar sinyaller olmalı:

- görev türü ve kapsamı;
- belirsizlik/risk olasılığı;
- repository exploration gereksinimi;
- tek dosya/mekanik değişiklik olasılığı;
- her rota için uygunluk skoru.

Bu değerler yerel classifier'a özellik olabilir veya ayrı bir `jev-zero-shot` baseline'ı oluşturabilir. Üretim varsayılanı yerel olmalı. Jev modu açılırsa yalnız küçültülmüş/sanitize edilmiş görev kartı OpenRouter'a gider; kod, secret, tam konuşma ve repository içeriği varsayılan olarak gönderilmez.

## Önerilen router tanımı

### Aday birimi: model değil, model + reasoning profili

Routing kolu yalnız `Luna` veya `Sol` olmamalı; reasoning seviyesi sonucu, süreyi ve tüketimi değiştirir. İlk deney havuzu küçük tutulmalı:

| Route ID | Amaç | Başlangıç profili |
| --- | --- | --- |
| `luna_standard` | Dar, mekanik ve düşük riskli işler | Luna medium |
| `terra_balanced` | Gündelik uygulama, orta kapsam | Terra high |
| `sol_complex` | Karmaşık debug/refactor | Sol high |
| `astra_frontier` | Belirsiz, uzun ufuklu, yüksek riskli iş | Astra high |

Model isimleri kodda hard-code edilmemeli. Bir `ModelRegistry` route kimliğini o an mevcut Codex modeli ve reasoning ayarına bağlamalı. Böylece sürüm değişimi yalnız registry ve yeni benchmark çalışması gerektirir.

### Görev kartı

Router'ın girdisi sürümlü ve loglanabilir bir JSON olmalı:

```json
{
  "schema_version": "1",
  "intent": "bugfix",
  "risk_flags": ["public_api"],
  "languages": ["python"],
  "repo_size_bucket": "medium",
  "scope_hint": "multi_file",
  "has_stack_trace": true,
  "has_acceptance_tests": true,
  "test_frameworks": ["pytest"],
  "requires_web": false,
  "requires_ui": false,
  "ambiguity": "low",
  "prompt_redacted": "Fix cache invalidation after ..."
}
```

Kart yalnız karar anında mevcut bilgi kullanır. Test sonucu, model cevabı veya gelecekteki başarı bilgisi feature leakage yaratacağı için kullanılmaz.

### Özellik katmanları

1. **Deterministik metadata:** task intent, dil, dosya/depo ölçeği, test varlığı, stack trace, istenen araçlar, risk bayrakları.
2. **Yerel metin sinyali:** kelime + karakter n-gram TF-IDF; gerekirse SVD. İlk sürüm için internet/API gerekmez.
3. **Benzer görev hafızası:** benchmark outcome matrisindeki en yakın görevlerin model bazlı sonuçları. Repo ve zaman ayrımı korunur.
4. **Opsiyonel Jev sinyali:** sanitize görev kartından gelen yapılandırılmış olasılıklar. Ablation ile gerçekten katkı sağladığı kanıtlanmadan varsayılan policy'ye alınmaz.

Yerel embedding modeli bir seçenek olarak tutulmalı fakat ilk zorunlu bağımlılık olmamalı. Büyük birleşik değerlendirmeler embedding seçiminin sınırlı etki gösterebildiğini söylüyor; bu nedenle önce daha basit, hızlı ve açıklanabilir özellikler denenmeli.

### Öğrenme hedefi

Her rota için ayrı bir başarı olasılığı öğrenilir:

```text
p_m(x) = P(route m görevi kabul kriterleriyle çözer | görev kartı x)
```

Eğitim tablosunun her satırı `(task_id, route_id, success, score, tokens, wall_time)` olur. Bir görevin birden çok model tarafından çözülebilmesi doğal olduğu için tek-sınıflı “doğru model” etiketi yerine çok-etiketli/per-route başarı hedefi kullanılır.

Başlangıç modelleri:

- `TF-IDF + LogisticRegression` per route;
- yapılandırılmış özelliklerle `HistGradientBoosting` veya eşdeğeri;
- kNN outcome retrieval;
- bunların validation üzerinde kalibre edilmiş küçük ensemble'ı.

Olasılıklar isotonic regression veya Platt scaling ile yalnız calibration split'inde kalibre edilir. Brier score, ECE ve reliability diagram raporlanır.

### Karar kuralı

Basit ağırlıklı ortalama yerine kalite kısıtlı optimizasyon kullanılmalı:

```text
uygun(m) = lower_confidence_bound(p_m(x)) >= tau(risk)

seçilen = argmin_m [ expected_tokens(m,x) + λ_time * expected_time(m,x) ]
          yalnız uygun(m) olan rotalar içinde
```

Hiçbir rota eşiği karşılamıyorsa veya örnek OOD ise `astra_frontier` ya da yapılandırılabilir güvenli fallback seçilir.

Başlangıç kalite eşikleri geliştirme setinde ayarlanmalı ve kilitli testten önce dondurulmalı. Örnek politika:

- düşük risk: hedef başarı olasılığı ≥ 0,85;
- orta risk: ≥ 0,92;
- yüksek risk/hard guard: doğrudan Sol/Astra;
- kritik: Astra ve ileride zorunlu review.

Bu sayılar ürün gerçeği değil, doğrulanacak başlangıç hipotezidir.

### OOD ve abstention

Router'ın “bilmiyorum” diyebilmesi zorunlu. Aşağıdakilerden biri oluşursa ucuz rota seçilmez:

- en yakın benchmark görevine benzerlik alt sınırın altında;
- kalibre edilmiş model olasılıkları birbirine çok yakın;
- ensemble modelleri route konusunda anlaşmıyor;
- dil/framework eğitim dağılımında yok;
- risk hard guard var;
- prompt çok kısa, çelişkili veya kabul kriteri belirsiz.

Bu mekanizma başarısız routing'i tamamen çözmez; fakat yanlış bir güvenle Luna'ya gönderilen kritik işlerin oranını ölçülebilir biçimde sınırlar.

## Benchmark veri tasarımı

### Public setlerin rolleri

- **LiveCodeBench:** İzole algoritmik kod üretimi ve execution için ucuz/tekrarlanabilir veri. Repository agent davranışını temsil etmez.
- **Terminal-Bench 2:** Terminal kullanan, çok adımlı ve gerçekçi görevler için ana public kaynaklardan biri.
- **SWE-bench Verified:** Gerçek issue→patch davranışı ve container değerlendirmesi için yararlı; tek başına ürün iddiası yapılmamalı.
- **SWE-bench Pro/audit edilmiş alt küme:** Uzun ufuklu görevler için deneysel kaynak; determinacy audit sonucu dikkate alınmalı.
- **Yerel/rolling görev seti:** Bizim Codex kullanım dağılımımızı temsil eden asıl kalibrasyon kaynağı. Secret ve kullanıcı kodu yayınlanmaz; yalnız izinli/sentetik görevler open-source sete girer.

### Önerilen ilk outcome matrisi

İlk tam araştırma koşusu için 400 görev önerisi:

| Dilim | Görev |
| --- | ---: |
| LiveCodeBench güncel/time-safe alt küme | 120 |
| Terminal-Bench 2 çeşitli kategori | 80 |
| SWE-bench Verified repo-disjoint | 80 |
| Audit edilmiş SWE-bench Pro | 40 |
| Sentetik mutation + izinli yerel görev | 80 |

Dört route ile bu 1.600 Codex çalışması demektir. Önce 40 görev × 4 route pilot koşusu yapılmalı; harness doğru ölçmüyorsa büyük matrise geçilmemeli.

Split rastgele prompt seviyesinde yapılmamalı:

- aynı repository yalnız tek split'te;
- mümkün olduğunda zaman tabanlı train/dev/test;
- benzer mutation ailesi aynı split'te;
- kilitli test çözüm artefaktları router eğitiminden ve workspace'ten uzak;
- eşikler yalnız dev/calibration setinde ayarlanır.

### Skorlama

Kodlama görevlerinde ana başarı sinyali yürütülebilir olmalı:

- hidden/public test sonucu;
- build, typecheck ve lint gerektiğinde yardımcı sinyal;
- patch'in uygulanabilirliği;
- görev-özel acceptance testleri;
- güvenlik veya veri kaybı ihlali için sıfırlayıcı ceza.

LLM judge yalnız yürütülemeyen görevlerde ikincil olmalı ve körlenmiş çift değerlendirme ile kullanılmalı. Router'ın eğitim etiketi, seçimi yapan aynı modelin öznel “bence çözerim” cevabı olmamalı.

## Değerlendirme kolları

Her kilitli testte aynı outcome matrisi üzerinde şu politikalar karşılaştırılmalı:

1. Always Luna
2. Always Terra
3. Always Sol
4. Always Astra
5. En iyi tek model (`Best Single`)
6. Eşleşmiş random; router ile aynı model seçim oranları
7. Statik intent/risk kuralları
8. Jev zero-shot
9. TF-IDF lojistik router
10. kNN outcome router
11. Önerilen kalibre edilmiş hibrit router
12. Karşı-olgusal oracle

Jev özellikli ve Jev'siz hibrit aynı testte bir ablation olmalı. Jev ek maliyet/latans getirip kaliteyi artırmıyorsa production policy'den çıkarılır.

## Raporlanacak metrikler

Yalnız “routing accuracy” yeterli değil. Aşağıdaki panel birlikte raporlanmalı:

- seçilen rotanın resolved/pass oranı;
- Always Sol ve Best Single'a göre kalite kaybı;
- toplam ve görev başı input/cached/output/reasoning token;
- p50/p95 duvar saati;
- çözülen görev başına token ve süre;
- route dağılımı ve güçlü model çağrı oranı;
- PGR/APGR ve cost-performance curve;
- Best Single'a eşit kalitede `CostSave`;
- oracle'a regret / `Gap@Oracle`;
- matched-random'a göre eşleştirilmiş kazanç;
- zor görev recall'ı ve yanlış-ucuz-route oranı;
- Brier, ECE ve reliability diagram;
- risk–coverage eğrisi/AURC;
- OOD abstention oranı ve OOD false-safe oranı;
- dil, framework, görev türü, repo ve risk dilimlerinde ayrı sonuçlar.

İstatistik:

- resolved sonucu için paired bootstrap güven aralığı;
- aynı görevlerde iki politikanın başarı farkı için McNemar;
- cost/time için paired bootstrap;
- stochastic görevlerin bir alt kümesinde en az 3 tekrar.

## Başarı kapısı

Router başarılı sayılmak için kilitli, repo/time-disjoint testte aynı anda şunları sağlamalı:

- Always Sol'a göre resolved-rate kaybı en fazla 3 yüzde puan;
- token veya ölçülen kaynak tüketiminde en az %35 azalma;
- çözülen görev başına kaynakta en az 1,5× iyileşme;
- matched-random router'a karşı pozitif ve güven aralığı sıfırın üzerinde kazanç;
- yüksek riskli görevlerde yanlış-ucuz-route yok veya önceden belirlenmiş çok düşük üst sınır;
- kalibrasyonun kabul edilebilir olması ve testte ciddi eşik sapması göstermemesi;
- p50 sürenin Always Sol'a göre anlamlı biçimde kötüleşmemesi.

Bu kapı, önceki “Jev %89,7, Sol %94,2 ve router iki kat ucuz” sonucunu otomatik olarak başarılı kabul etmez. O sonuç ekonomik açıdan ilginçtir fakat 4,5 puan kalite kaybı ve zayıf zor-görev recall'ı nedeniyle güvenilir production router eşiğini geçmez.

## Router-only v0.1 mimarisi

```text
User task
   |
   v
Local TaskCardBuilder
   |-- prompt sanitization
   |-- read-only repo metadata
   v
HardGuardPolicy --------------------> forced Sol/Astra
   |
   v
FeaturePipeline
   |-- sparse local text features
   |-- structured metadata
   |-- nearest benchmark outcomes
   |-- optional Jev features
   v
PerRouteSuccessPredictor
   |-- calibrated P(success) for each route
   |-- OOD/uncertainty
   v
ConstrainedPolicy
   |-- quality threshold by risk
   |-- minimize expected tokens/time
   v
RouteReceipt
   |-- selected route + confidence bounds
   |-- reason codes + policy/model versions
   v
Codex native dispatcher
```

Bu sürüm model cevabını değerlendirmez ve ikinci model çağırmaz. Yalnız görevi uygun Codex model/efor profiline gönderir ve daha sonra benchmark öğrenimi için kullanım/sonuç metadata'sı toplanmasına izin verir.

## Mevcut projede yapılacak değişiklikler

Mevcut kod ikili `cheap/strong` rollerine ve Jev'nin tek `strong_probability` eşiğine bağlı. Router-only dönüşüm şu sırayla yapılmalı:

### Aşama 1 — veri sözleşmeleri ve dry-run

- `ModelRole = cheap|strong` yerine açık uçlu `route_id`.
- `TaskCard`, `RouteProfile`, `RoutePrediction`, `RouteReceipt` şemaları.
- `ModelRegistry`; Codex model/efor eşlemesi config'te.
- Salt-okunur `TaskCardBuilder` ve redaction.
- Hard guard ve açıklanabilir reason code'lar.
- `route --dry-run` komutu; hiçbir model çağrısı yapmadan kararı gösterir.

### Aşama 2 — outcome matrisi ve baseline'lar

- Benchmark sonuçlarını `task × route` tablosuna normalize et.
- Always-model, matched-random, static-rule, Jev ve oracle baseline'ları.
- Repo/time-disjoint split manifesti.
- TF-IDF lojistik, kNN ve gradient baseline'ları.

### Aşama 3 — kalibrasyon ve policy

- Per-route probability calibration.
- Risk-temelli kalite eşikleri.
- OOD/abstention.
- Maliyet/süre tahminleri ve constrained policy.
- Kilitli testte threshold sweep, Pareto ve calibration raporu.

### Aşama 4 — Codex native dispatch

- Dry-run receipt'i Codex custom agent/model seçimine bağla.
- `codex exec --json` ile token ve duvar saati topla.
- Ayrı API anahtarı gerektirmeyen native çalışma modu.
- Jev yalnız `--router-features jev` ile açılan opsiyonel dış çağrı.

### Bu aşamada özellikle yapılmayacaklar

- worker cevabını Jev ile doğrulama;
- Luna→Sol/Astra cascade;
- birden fazla modelden cevap alıp en iyisini seçme;
- otomatik reviewer/fixer;
- kullanıcı kodunu OpenRouter'a gönderme;
- public benchmark skoruna bakıp elle sabit model seçme.

## Önerilen açık kaynak modül sınırları

```text
src/jev_router/
  task_card.py
  registry.py
  receipts.py
  guards.py
  features/
    sparse_text.py
    repo_metadata.py
    neighbors.py
    jev_optional.py
  predictors/
    logistic.py
    knn.py
    ensemble.py
    calibration.py
  policies/
    constrained.py
    static_rules.py
  codex/
    dispatch.py
    usage.py
  benchmark/
    matrix.py
    splits.py
    metrics.py
    statistics.py
schemas/
  task-card.schema.json
  route-receipt.schema.json
```

## Gizlilik ve “lokal” ifadesi

İki kavram ayrı tutulmalı:

- **Yerel router:** Task card, özellik çıkarımı ve model seçimi bilgisayarda çalışır; üçüncü taraf router API çağrısı yoktur.
- **Codex-native target:** Seçilen Luna/Terra/Sol/Astra görevi mevcut Codex oturumu üzerinden çözer. Ayrı OpenRouter çağrısı yapılmaz, fakat model inference fiziksel olarak bilgisayarda değildir.

Jev modu açılırsa görev kartı OpenRouter/TypeSafe'a giden ücretli harici çağrıdır. Bu nedenle varsayılan açık kaynak profili `native-local`, karşılaştırma/opsiyonel profil `jev-assisted` olmalı.

## Nihai öneri

İlk geliştirme sprinti yalnız Aşama 1'i tamamlamalı: çok-model route registry, görev kartı, hard guard, receipt ve dry-run. İkinci sprint küçük tam outcome matrisiyle baseline'ları kurmalı. Öğrenilmiş router ancak bu baseline veri hattı doğrulandıktan sonra eklenmeli.

Bu sıralama ile ilk günden “akıllı görünüp rastgele davranan” bir router yerine, her kararının hangi benchmark verisine, risk kuralına ve kalibre edilmiş olasılığa dayandığı denetlenebilir bir sistem elde ederiz.
