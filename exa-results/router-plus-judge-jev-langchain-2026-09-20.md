# Jev ile Router + Judge mimarisi araştırması

Tarih: 2026-09-20
Kapsam: LangChain'in Jev paylaşımı, router + verifier/judge birleşimi ve Codex coding agent uygulaması

## Kısa karar

Router ile Jev judge'ı birleştirmek mantıklı ve yalnız router'dan daha yüksek kalite/maliyet verimi sağlayabilir. Fakat doğru tasarım `her LLM mesajından sonra Jev çağır` değildir. Doğru tasarım:

1. Başlangıçta benchmark-temelli router model ve reasoning seviyesini seçer.
2. Jev yalnız anlamlı karar noktalarında ucuz, typed micro-judge olarak çalışır.
3. Deterministik test/build/lint sonucu Jev kararından üstündür.
4. Jev `stuck`, `scope violation`, `unsafe action`, `not ready` veya `needs escalation` sinyali verirse worker yeniden dener ya da daha güçlü modele yükselir.
5. Jev'nin güveni düşükse veya açıklama gerekiyorsa seyrek bir Sol/Astra rubric reviewer çağrılır.

Bu yapı üç katmanlı olmalı:

```text
Deterministik doğrulayıcılar > Jev micro-judge > seyrek frontier LLM reviewer
```

Jev geniş kapsamlı code correctness oracle değildir. En iyi rolü, küçük ve açıkça tanımlanmış kararları çok ucuza vermek ve pahalı reviewer'ın hangi olaylarda gerekli olduğunu seçmektir.

## Araştırma kapsamı

Exa ile dört araştırma hattında 274 sonuç incelendi. X indeks sonuçları, LangChain resmî blogu, `langchain-typesafe` paketi, Deep Agents RubricMiddleware, LangGraph evaluator-optimizer, LangSmith trajectory evals, NVIDIA Switchyard escalation router, OpenRouter Jev cascade ve bağımsız erken Jev değerlendirmeleri çapraz kontrol edildi. Tekrarlar ve ikincil özetler çıkarıldıktan sonra 12 birincil/uygulayıcı kaynağı ayrıntılı okundu.

Ana kaynaklar:

- [LangChain: Building a Harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev)
- [Yazarın X paylaşımı](https://x.com/sydneyrunkle/status/2100754364545761643)
- [`langchain-typesafe` PyPI](https://pypi.org/project/langchain-typesafe)
- [Deep Agents RubricMiddleware](https://docs.langchain.com/oss/python/deepagents/rubric)
- [LangChain Rubrics teknik yazısı](https://www.langchain.com/blog/introducing-rubrics-for-deepagents)
- [LangGraph workflows/evaluator-optimizer](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals)
- [NVIDIA Switchyard escalation router](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/docs/routing_algorithms/escalation_router_routing.md)
- [OpenRouter Jev-verified cascade](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-verified-cascade)
- [LangChain/Harvey efficient verifiers](https://www.langchain.com/blog/designing-efficient-verifiers-for-legal-agents)
- [LangChain/Fireworks cheap trace judge](https://www.langchain.com/blog/building-a-100x-cheaper-trace-judge-with-fireworks)
- [Arize: Jev as LLM judge](https://arize.com/blog/typesafe-jev-llm-judge/)

## LangChain'in X'te paylaştığı içerik

İstenen içerik 17 Eylül 2026 tarihli **Building a Harness with Jev** yazısı. X sayfası doğrudan otomatik fetch'e 403 verdi; ancak yazının ortak yazarı Sydney Runkle'ın paylaşımı ve LangChain resmî yazısı bulundu ve içerik birbiriyle eşleşiyor.

Yazı iki hazır kullanım gösteriyor:

### 1. ModelRouterMiddleware

Jev, son kullanıcı mesajını bir `Choice` sorusuyla değerlendirip `fast` veya `powerful` modeli seçiyor. Örnekte:

- Luna: lookup, extraction, localized change;
- Sol: architecture ve high-stakes decisions.

Router son kullanıcı mesajını **agent run başına bir kez** sınıflandırıyor ve seçilen modeli run boyunca kullanıyor. Olasılıklar ve confidence agent state'e yazılıyor.

### 2. AutoModeMiddleware

Jev, açıkça yapılandırılmış tool çağrılarını çalışmadan önce değerlendiriyor. Örneğin `bash`, `delete_file`, publish veya permission değişikliği gibi bir çağrının risk olasılığı threshold'u aşarsa tool çalıştırılmadan engelleniyor.

Önemli düzeltme: LangChain yazısında Jev'nin her üretilen kod adımının doğruluğunu kontrol ettiği tam bir runtime correctness judge örneği yok. Hazır entegrasyon şu an:

- başlangıç model routing;
- tool-call risk classification.

Çıktı doğruluğu ve tamamlanma judge döngüsü için LangChain'in ayrı `RubricMiddleware` yapısını Jev ile birleştirmek gerekir.

## Paket olgunluğu

`langchain-typesafe` araştırma tarihinde `0.0.1a2`; 17 Eylül 2026'da yayımlanmış alpha sürüm. `ModelRouterMiddleware` ve `AutoModeMiddleware` `experimental` namespace altında ve API'nin değişebileceği açıkça belirtiliyor.

Sonuç: Açık kaynak projenin çekirdeğini bu alpha pakete sıkı bağlamamalıyız. Şu ayrım daha güvenli:

```text
router/judge core contracts
        |
        +-- direct OpenRouter/TypeSafe adapter
        +-- optional langchain-typesafe adapter
        +-- fixture/local adapter
```

LangChain entegrasyonu örnek ve uyumluluk katmanı olmalı; ana karar motoru değil.

## LangChain'in judge modeli: RubricMiddleware

Deep Agents `RubricMiddleware`, agent normalde biteceği zaman ayrı bir grader sub-agent çalıştırıyor:

1. Agent bir sonuç üretir.
2. Grader tüm transcript'i ve rubric'i inceler.
3. `satisfied`, `needs_revision` veya `failed` döndürür.
4. `needs_revision` ise kriter bazlı feedback konuşmaya eklenir.
5. Agent tekrar çalışır.
6. Rubric geçene veya `max_iterations` dolana kadar sürer.

Grader test/lint gibi araçları çağırabilir. LangChain'in kendi önerisi, soyut doğruluk tahmini yerine mümkün olduğunda test aracından kanıt toplamaktır.

Bu, bizim hedeflediğimiz son kontrol döngüsüne çok yakın. Ancak Jev'nin önemli bir sınırı var: typed karar verir, açıklama veya hedefli düzeltme metni üretmez. Bu nedenle Jev tek başına RubricMiddleware'in LLM grader'ının tam yerini alamaz.

En iyi kombinasyon:

- Jev: `satisfied / needs_revision / escalate / uncertain` ve kriter olasılıkları;
- deterministik verifier: test/build/lint çıktısı;
- gerekirse Sol/Astra reviewer: neden ve nasıl düzeltileceğine dair açıklama.

## Neden judge'ı her adımda çalıştırmamalıyız?

### 1. Birçok agent adımı değerlendirilecek nihai çıktı değildir

Dosya okuma, grep, planlama ve keşif adımları tek başına “doğru/yanlış” değildir. Her adımda doğruluk judge'ı yanlış sinyal üretebilir.

### 2. Judge çalışma için yeterli kanıta sahip olmayabilir

Kodun doğru olup olmadığını yalnız diff metninden anlamak zordur. Test, build, typecheck ve tool sonuçları olmadan Jev de LLM judge da tahmin yapar.

### 3. Yanlış kabul en tehlikeli hata türüdür

LangChain/Harvey çalışmasında ucuz bir verifier olan Haiku'nun false-pass oranı per-criterion %48,4, batch modunda %34,7 olarak ölçülmüş. Ucuz judge kullanmak otomatik olarak güvenli değildir. DeepSeek'in prompt tuning sonrası false-pass oranı bile per-criterion %9,5, batch %14,2 düzeyindeydi.

### 4. Maliyet ve latency birikir

Jev çok ucuz ve hızlı olsa da uzun transcript her adımda tekrar gönderilirse input token, network ve serialized dependency maliyeti büyür. Ayrıca her judge sonucu beklenirse agent'ın kritik yolu uzar.

### 5. Aynı hata kaynağına bağımlılık oluşabilir

Router ve judge aynı kriterle aynı yanlış varsayımı yaparsa daha fazla çağrı güvenilirliği artırmaz. Router ve verifier sinyalleri mümkün olduğunca farklı olmalı: benchmark predictor, test sonucu, Jev typed judgment ve seyrek LLM review.

## Doğru judge zamanlaması

Önerilen event-driven politika:

| Olay | Judge | Eylem |
| --- | --- | --- |
| İlk görev | benchmark router + opsiyonel Jev | model/reasoning seç |
| Riskli tool çağrısı öncesi | Jev AutoMode | izin ver, engelle veya insan onayı iste |
| Test/build/typecheck sonucu | önce deterministik, sonra gerekirse Jev | devam, düzelt veya yükselt |
| Aynı hata 2 kez tekrarlandı | Jev progress/stuck | güçlü modele yükselt |
| N tool çağrısı boyunca edit/test yok | Jev stage judge | exploration mı spinning mi değerlendir |
| Agent bitirmek istiyor | deterministik rubric + Jev completion | kabul, revision veya strong review |
| Yüksek riskli final diff | Sol/Astra rubric reviewer | zorunlu review |

Varsayılan olarak her tool çağrısı sonrası judge yok. Yalnız `risk`, `error`, `stage boundary`, `finish` ve örneklenmiş telemetry olaylarında çalışır.

## Jev micro-judge sözleşmesi

Tek Jev isteğinde sorular paralel değerlendirilir. Bu yüzden bir event için birden çok dar soru aynı çağrıda sorulmalı:

```json
{
  "state": {
    "task_card": {},
    "selected_route": "terra_balanced",
    "turn_index": 8,
    "agent_stage": "test",
    "recent_actions": [],
    "verifier_results": {},
    "diff_summary": {},
    "acceptance_criteria": []
  },
  "questions": {
    "progress": {
      "type": "choice",
      "criteria": {
        "progressing": "Observable progress toward acceptance criteria",
        "stuck": "Repeated failure or no useful progress",
        "regressing": "New failures or scope damage introduced"
      }
    },
    "scope_aligned": {
      "type": "noul",
      "instructions": "Changes remain within the requested scope"
    },
    "ready_to_finish": {
      "type": "noul",
      "instructions": "All stated acceptance criteria have evidence of completion"
    },
    "needs_stronger_model": {
      "type": "noul",
      "instructions": "Current model is unlikely to finish reliably without escalation"
    },
    "action_risk": {
      "type": "score",
      "criteria": ["read_only", "reversible", "destructive", "critical"]
    }
  }
}
```

Jev'ye tam repo veya tüm transcript gönderilmemeli. `JudgePacketBuilder` şu özetleri üretmeli:

- sanitize görev kartı;
- son birkaç action türü ve kısa sonuç kodları;
- test/build/lint pass/fail sayıları;
- değişen dosya ve satır sayısı;
- hassas path/risk flag'leri;
- acceptance criteria durumları;
- gerekiyorsa çok kısa hata parçaları.

## Karar önceliği

Kuralların önceliği açık olmalı:

```text
1. Safety hard guard
2. Deterministic verifier evidence
3. Jev calibrated decision
4. LLM rubric reviewer
5. Human approval / fail-safe
```

Örnekler:

- Testler başarısızsa Jev `ready_to_finish=0.98` verse bile bitirme.
- Jev riskli tool'u yüksek confidence ile işaretlerse tool'u engelle veya onay iste.
- Testler geçiyor ama acceptance criteria semantik olarak eksikse Jev/LLM rubric review yap.
- Jev düşük confidence verirse ucuz modele otomatik güvenme; fallback/strong review kullan.
- High-risk görevde tek bir Jev `supported` kararı final kabul için yeterli olmasın.

## Escalation politikası

Switchyard'ın iki ardışık escalate onayı fikri yanlış pozitifleri azaltmak için iyi:

```text
needs_stronger_model >= 0.80 bir kez:
    aynı worker'a hedefli bir revision hakkı

iki ardışık eventte >= 0.80:
    bir üst rotaya yükselt

kritik safety ihlali veya hard verifier failure:
    confirmation beklemeden yükselt/engelle
```

Model merdiveni:

```text
Luna → Terra → Sol → Astra
```

Ancak yükseltme her zaman bir basamak olmak zorunda değil. Güvenlik, migration veya geri döndürülemez işlem doğrudan Astra/Sol review'a gidebilir.

Session bir kez güçlü modele latch edildiğinde aynı hata episode'u boyunca aşağı düşürülmemeli. Yeni, mekanik bir stage açıkça başladığında aşağı yönlü routing ileride deneysel olarak açılabilir.

## Router + judge maliyet koşulu

Ucuz worker + Jev + gerektiğinde strong worker cascade'inin always-strong'dan ucuz olması için yaklaşık koşul:

```text
C_weak + C_jev + p_escalate × C_strong < C_strong
```

Yani:

```text
p_escalate < 1 - (C_weak + C_jev) / C_strong
```

Fakat bu yalnız maliyet koşuludur. Kalite için ayrıca judge false-pass oranı kabul sınırının altında olmalı.

OpenRouter'ın 50 soruluk Jev cascade örneğinde:

- Luna draft + Jev verify;
- geçmezse Astra + ikinci Jev verify;
- toplam $0,012;
- always-Astra $0,175;
- cascade yanlış cevap göndermedi.

Bu yaklaşık %93 maliyet azalmasıdır; ancak yalnız 50 RAG sorusu, iki koşu arasında sonuç değişimi var ve gerçek coding-agent benchmark'ı değildir. Tasarım kanıtı olarak değerlidir, ürün iddiası olarak yeterli değildir.

## Jev judge'ın sınırlamaları

Arize'ın erken incelemesi önemli uyarılar içeriyor:

- TypeSafe workflow benchmarklarında Jev ortalama %68, Terra %68, Opus %73 doğruluk bildirmiş;
- Jev Opus'tan yaklaşık beş puan geride olsa da çok daha ucuz;
- Jev schema dışına çıkmaz ama schema içinde yanlış karar verebilir;
- açıklama üretmez;
- confidence kalibrasyonu her kullanım dağılımında yeniden doğrulanmalı.

Sonuç: Jev'yi “gerçeği bilen hakim” değil, ucuz ve kalibre edilebilir bir filtre olarak kullanmalıyız. Fail/pass kriterleri coding verimiz üzerinde ayrıca kalibre edilmeden production threshold belirlenmemeli.

## Açıklama problemi

Jev `needs_revision=0.92` diyebilir fakat agent'a neyi nasıl düzelteceğini açıklayamaz. Üç çözüm:

1. Deterministik test/log çıktısını doğrudan agent'a feedback olarak ver.
2. Jev sorularını criterion bazında kur; başarısız criterion kimliği hedefi daraltsın.
3. Yalnız açıklama gerektiğinde küçük/strong LLM reviewer çağır.

Böylece pahalı reviewer her başarılı görevde değil, yalnız belirsiz veya başarısız örneklerde kullanılır.

## Önerilen mimari

```text
User Task
   |
   v
TaskCard + benchmark router
   |
   +--> hard risk guard ------> Sol/Astra
   |
   v
Selected Codex worker
   |
   +--> before risky tool: Jev AutoMode
   |
   +--> tool/test/build events
   |        |
   |        +--> deterministic verifier
   |        +--> event-triggered Jev micro-judge
   |                    |
   |          continue / revise / escalate
   |
   v
Finish candidate
   |
   +--> tests + lint + typecheck + diff guards
   +--> Jev completion/rubric classification
   |
   +--> clear pass ----------> deliver
   +--> clear failure -------> revise/escalate
   +--> uncertain/high risk -> Sol/Astra rubric reviewer
```

## Mevcut proje için yeni modüller

```text
src/jev_router/
  judge/
    packets.py
    policy.py
    thresholds.py
    events.py
    typesafe.py
    fixture.py
  verifier/
    tests.py
    build.py
    lint.py
    diff_guard.py
  escalation/
    streak.py
    ladder.py
    latch.py
  receipts/
    route_receipt.py
    judge_receipt.py
    escalation_receipt.py
```

Sözleşmeler:

- `RouteDecision`: başlangıç model/reasoning seçimi;
- `JudgeEvent`: judge'ı tetikleyen olay;
- `JudgePacket`: sanitize edilmiş evidence;
- `JudgeDecision`: continue/revise/escalate/block/uncertain;
- `VerifierEvidence`: test/build/lint/diff sonuçları;
- `EscalationState`: streak, latch ve route geçmişi.

## Benchmark tasarımı

Karşılaştırma kolları:

1. Always Sol
2. Always Astra
3. Router only
4. Router + deterministic verifier
5. Router + Jev at every turn
6. Router + event-driven Jev judge
7. Router + Jev + selective Sol reviewer
8. Switchyard escalation baseline
9. Oracle

Bu karşılaştırma özellikle “her adımda judge” ile “event-driven judge” arasındaki farkı gösterecek.

Ana metrikler:

- final resolved/pass rate;
- always-Sol/Astra kalite farkı;
- toplam token, API-equivalent maliyet ve duvar saati;
- judge çağrı sayısı ve judge overhead;
- escalation rate;
- false-pass: judge kabul etti ama görev başarısız;
- false-fail: judge reddetti ama görev aslında başarılı;
- correction yield: revision isteyenlerin kaçının sonraki denemede düzeldiği;
- strong-review rate;
- wasted weak work before escalation;
- calibration: Brier/ECE/reliability;
- kritik tool block precision/recall.

Judge başarısının birincil metriği accuracy değil, **false-pass oranı** olmalı. Yanlış red ek maliyet yaratır; yanlış kabul bozuk kod teslim eder.

## Geliştirme sırası

### Aşama 1 — Router çekirdeği

- Önceki plandaki TaskCard, registry, benchmark predictor, hard guard ve dry-run.

### Aşama 2 — Judge offline replay

- Mevcut benchmark trajectory'lerinden JudgePacket üret.
- Jev verdict'lerini canlı karar vermeden logla.
- Test sonuçlarına göre Jev calibration, false-pass ve false-fail ölç.

### Aşama 3 — Shadow judge

- Gerçek Codex görevlerinde Jev karar üretir fakat akışı değiştirmez.
- Hangi event ve threshold'ların güvenilir olduğu belirlenir.

### Aşama 4 — Safe intervention

- Önce yalnız riskli tool block ve final completion gate aktif edilir.
- Düşük riskli revision/escalation daha sonra açılır.

### Aşama 5 — Selective frontier reviewer

- Jev uncertain/failure durumunda Sol/Astra rubric reviewer.
- Reviewer'ın feedback'i worker'a verilir; iteration cap zorunlu olur.

Bu sıra önemlidir: Jev'nin coding workload'umuzdaki kalibrasyonunu ölçmeden gerçek agent akışını otomatik değiştirmemeliyiz.

## Nihai öneri

Router + judge projenin doğru uzun vadeli mimarisi. Ancak iki ayrı kullanım moduna bölünmeli:

- `router-only`: önce güvenilir model seçimini izole edip ölçmek;
- `router-judge`: event-driven Jev micro-judge + deterministic verifier + selective strong reviewer.

Ürün iddiası şu olabilir:

> Benchmark-temelli model routing ile görevi en uygun Codex profiline gönderir; deterministic kanıt ve Jev'nin kalibre edilmiş micro-judgments'ı ile ilerlemeyi izler; yalnız belirsiz, başarısız veya riskli örnekleri güçlü modele yükseltir.

Bu yaklaşım, LangChain'in yeni Jev middleware'ini kopyalamaktan daha güçlüdür: onların model router ve tool-risk guard örneklerini, Deep Agents rubric correction loop'u ve Switchyard escalation mantığıyla tek, ölçülebilir bir Codex-native sistemde birleştirir.
