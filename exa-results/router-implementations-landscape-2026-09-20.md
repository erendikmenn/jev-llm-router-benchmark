# LLM router uygulamaları ve rekabet karşılaştırması

Tarih: 2026-09-20
Amaç: ErenAILab Codex router yönünün, gerçek ürün ve açık kaynak uygulamalara göre doğrulanması

## Araştırma özeti

Exa ile altı araştırma hattında toplam 336 arama sonucu incelendi. URL ve ürün tekrarları, ikincil içerikler ve yalnız pazarlama özeti veren sayfalar elendikten sonra 14 gerçek sistem/ürün ve bunlara ait resmî doküman, depo veya birincil teknik yazı derinlemesine karşılaştırıldı.

İncelenen ana sistemler:

1. LangChain / LangGraph / LangSmith
2. NVIDIA NeMo Switchyard
3. Not Diamond Code
4. LiteLLM Auto Router
5. vLLM Semantic Router
6. RouteLLM
7. OpenRouter Auto Router
8. Microsoft Foundry Model Router
9. Amazon Bedrock Intelligent Prompt Routing
10. Martian / RouterBench
11. Aurelio Semantic Router
12. Portkey Conditional Routing
13. Cloudflare AI Gateway Dynamic Routing
14. Google Cloud API Gateway Model Routing

## En kısa sonuç

Bizim yönümüz doğru, ancak mimariyi iki önemli açıdan güncellemeliyiz:

1. **Task-level router ile başlamalıyız ama veri sözleşmesini session/turn routing'e hazır kurmalıyız.** Modern coding router'ları yalnız ilk promptu değil, oturum evresini, cache durumunu, tool sonuçlarını ve önceki hataları kullanıyor.
2. **Benchmark outcome verisi merkezde kalmalı.** LangChain branch'leri, gateway kuralları veya sıfır-atış LLM classifier tek başına yeterli değil. Her aday `model + reasoning effort` için gerçek başarı/maliyet/süre tahmini öğrenmemiz gerekiyor.

En yakın üç referans:

- Açık kaynak entegrasyon ve Codex/Claude Code proxy'si için **NVIDIA Switchyard**.
- Kodlama ajanı için cache-aware, turn-level karar tasarımı bakımından **Not Diamond Code**.
- Benchmarktan öğrenilen kalibre edilmiş başarı olasılığı bakımından **RouteLLM + Microsoft Foundry Model Router**.

Tek bir projeyi kopyalamak yerine bu üç yönü birleştirmek en mantıklı yaklaşım.

## Sistem karşılaştırması

| Sistem | Gerçekte ne yapıyor? | Karar sinyali | Açık kaynak / lokal | Bizim için anlamı |
| --- | --- | --- | --- | --- |
| LangChain/LangGraph | Query'yi uzman agent/prompt/graph branch'ine yollar | Kullanıcının yazdığı classifier veya LLM structured output | Açık kaynak | Orchestration sağlar; model seçme zekâsını sağlamaz |
| NVIDIA Switchyard | Coding agent çağrılarını weak/strong modellere route eder | LLM classifier, workflow-stage heuristiği, escalation | Apache-2.0; proxy veya library; pre-alpha | Codex uyumlu dispatch, session affinity ve stage sinyalleri için en iyi açık referans |
| Not Diamond Code | Her agent adımında model + reasoning effort seçer | Gelecek reward/cost, session state, token/cache, intermediate/final feedback | Ticari, gated; lokal proxy metadata yollar | En yakın doğrudan rakip; task-only routing'in uzun vadede yetersiz olduğunu gösteriyor |
| LiteLLM Auto Router | İstekleri complexity tier'larına böler | Heuristic, küçük LLM veya keyword; session pinning | Açık kaynak gateway; Auto Router early access | Gateway ve baseline olarak iyi; benchmarktan öğrenilmiş per-model success varsayılan değil |
| vLLM Semantic Router | Çok sinyalli programlanabilir mixture-of-models kontrol katmanı | 16 sinyal ailesi, projection ve policy kuralları | Açık kaynak, self-hosted | Güvenlik, domain, risk ve preference sinyalleri için güçlü mimari; capability policy'yi yine bizim eğitmemiz gerekir |
| RouteLLM | Strong/weak arasında query-only routing | Preference verisinden strong-win olasılığı + threshold | Açık kaynak | Kalibrasyon ve cost-quality eğrisi için temel akademik referans |
| OpenRouter Auto Router | Task tipine göre modelleri market harcama payıyla sıralar | ~30 task tipi + son 7 gün aggregate spend + cost tier | Harici servis | Güncel ve kolay; fakat harcama payı doğruluk etiketi değildir |
| Microsoft Foundry Model Router | Prompt için en uygun modeli seçen küçük ML router | Yüz binlerce örnek, full request/history/tools, cost/quality/latency mode | Managed, kapalı | Bizim benchmark-supervised per-model predictor fikrimizin güçlü endüstri doğrulaması |
| AWS Bedrock Intelligent Prompt Routing | Aynı ailede iki model arasında quality/cost routing | Her modelin tahmini response quality'si + threshold | Managed, aynı model ailesiyle sınırlı | İki-model MVP ve quality threshold fikrini doğruluyor |
| Martian / RouterBench | Router araştırması ve 405K outcome benchmark; güncel public ürün daha çok gateway/ARES | Precomputed outcome matrix | RouterBench açık; ürün kapalı/kısıtlı | Outcome matrisi, oracle ve benchmark metodolojisi için kaynak |
| Aurelio Semantic Router | Intent/domain route seçer | Lokal embedding benzerliği + route threshold | Açık kaynak/lokal | Task taxonomy için iyi; “hangi model bu örneği çözer?” sorusunu doğrudan çözmez |
| Portkey | Metadata/request parametreleriyle condition/fallback/load-balance | Kullanıcı tanımlı kurallar | Gateway açık kaynak seçenekleri | Dispatch altyapısı; öğrenilmiş router değil |
| Cloudflare AI Gateway | Görsel/JSON condition, budget, rate-limit, A/B ve fallback akışı | Kullanıcı tanımlı rule graph | Managed gateway | Politika ve rollout altyapısı; capability predictor değil |
| Google API Gateway | Payload/model parametresine göre managed gateway dispatch | OpenAPI config ve request parametreleri | Managed | Şu an intelligent task-quality router değil |

## LangChain tarafında durum

### Eski router sınıfları artık ana yaklaşım değil

LangChain'in eski `LLMRouterChain` ve `MultiPromptChain` sınıfları deprecated. Resmî dokümanlar routing mantığının LangGraph state graph, `RunnableLambda`, structured output veya agent middleware ile kurulmasını öneriyor.

Kaynaklar:

- [Deprecated LLMRouterChain](https://reference.langchain.com/python/langchain-classic/chains/router/llm_router/LLMRouterChain)
- [Deprecated MultiPromptChain](https://reference.langchain.com/python/langchain-classic/chains/router/multi_prompt/MultiPromptChain)
- [Güncel LangChain router pattern](https://docs.langchain.com/oss/python/langchain/multi-agent/router)
- [LangGraph multi-source router örneği](https://docs.langchain.com/oss/python/langchain/multi-agent/router-knowledge-base)

Güncel router pattern daha çok şu problem için:

```text
Soru GitHub mı, Notion mı, Slack mı gerektiriyor?
```

Bu bir **agent/vertical routing** problemidir. Bizim problemimiz ise:

```text
Bu coding görevini Luna, Terra, Sol veya Astra'dan hangisi
istenen kaliteyle en düşük kaynakta çözer?
```

LangGraph bu kararı çalıştırmak için iyi bir graph altyapısıdır; kararın kendisini öğretmez.

### Dynamic model selection mümkün fakat policy kullanıcıya ait

LangChain v1 middleware, her model çağrısını `wrap_model_call` ile sarmaya ve request/state'e göre modeli değiştirmeye izin veriyor. Built-in middleware içinde retry, fallback, tool selection ve call limit var; ancak genel amaçlı, benchmarktan öğrenen hazır bir coding model selector yok.

Bu nedenle LangChain ekosistemindeki doğru entegrasyon biçimi:

```text
Bizim RouterPolicy
      ↓
LangChain middleware / LangGraph branch
      ↓
Seçilen model
```

RouterPolicy'yi LangChain'e bırakmak değil.

### LangChain'in güncel Switchyard deneyi

LangChain ekibi 11 Ağustos 2026'da NVIDIA NeMo Switchyard'ı Deep Agents evaluation suite üzerinde denedi. Nemotron 3.5 Lightning ile Claude Opus 4.8 arasında routing yaptılar:

- çağrıların %7'si frontier modele gitti;
- bu %7 toplam frontier-only faturanın %68'ini oluşturuyordu;
- toplam maliyet %74 azaldı;
- aynı çağrılarda Opus kalitesinin yaklaşık %93'ü korundu; yani yaklaşık 6-7 puan kayıp oluştu.

Kaynak: [LangChain Switchyard benchmark](https://www.langchain.com/blog/switchyard-agent-routing-benchmark)

Bu sonuç ekonomik potansiyeli doğruluyor fakat bizim hedeflediğimiz `≤3 puan kalite kaybı` standardından daha gevşek. Dolayısıyla “LangChain yaptı, aynı sonucu kabul edelim” dememeliyiz; kendi kalite eşiğimizi korumalıyız.

## NVIDIA NeMo Switchyard

[Switchyard](https://github.com/NVIDIA-NeMo/Switchyard), Codex CLI ve Claude Code gibi coding agent'ların OpenAI/Anthropic protokollerini proxy üzerinden farklı modellere yönlendirebiliyor. OpenAI Responses formatını desteklemesi bizim kullanımımız için özellikle önemli.

Üç ana stratejisi var:

1. **LLM classifier:** Weak modelin görevi çözme olasılığı `p_solve`, capability boundary, crux ve confidence üretir. Düşük confidence veya parse hatasında strong modele düşer.
2. **Stage router:** Tool-result history'den exploration, error recovery, spinning ve production intensity sinyalleri çıkarır. Zor/kararsız evrede capable, mekanik üretim evresinde efficient model kullanır.
3. **Escalation router:** Weak modeli çalıştırır; judge tekrarlanan hata/drift görürse session'ı strong modele latch eder.

Kaynaklar:

- [Routing overview](https://docs.nvidia.com/nemo/switchyard/routing/overview)
- [LLM classifier routing](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/docs/routing_algorithms/llm_classifier_routing.md)
- [Stage routing](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/docs/routing_algorithms/stage_router_routing.md)
- [Escalation routing](https://github.com/NVIDIA-NeMo/Switchyard/blob/main/docs/routing_algorithms/escalation_router_routing.md)

Alınması gereken fikirler:

- OpenAI/Anthropic protocol-compatible stable endpoint;
- explicit session ID ve session affinity;
- `p_solve`, `uncertain`, `unsupported`, `unmatched` gibi açık karar sözleşmesi;
- classifier hatasında strong fail-safe;
- route metadata ve Prometheus tarzı telemetry;
- turn stage sinyallerinin ayrı modül olması.

Doğrudan bağımlılık yapmama nedeni: proje resmî README'de pre-alpha ve production için hazır değil olarak işaretli. Ayrıca built-in capability classifier, bizim modellerimizin benchmark outcome matrisinden öğrenmiyor.

## Not Diamond Code

[Not Diamond Code](https://code.notdiamond.ai/docs/) şu anda bizim hedefimize en yakın ticari sistem.

Öne çıkan mimari:

- her agent adımında model ve reasoning effort seçiyor;
- yalnız bugünkü çağrının değil, gelecekteki adımların beklenen reward ve maliyetini tahmin ediyor;
- session state, message/token sayısı, task complexity ve KV cache durumunu kullanıyor;
- intermediate ve final feedback ile sürekli güncelleniyor;
- lokal proxy raw prompt, kod, input ve output göndermediğini; yalnız derived metadata gönderdiğini belirtiyor.

Vendor'ın kendi benchmark iddiaları:

- Poly-SWE-bench Verified'da Opus 4.8 Xhigh'a yakın kalite, %39 düşük maliyet;
- LongCodeQA'da %61 düşük maliyet;
- açık modeller eklenince Poly-SWE performansında +%3,6 ve tasarrufta %66'ya çıkış;
- genel early-access iddiası %20+ tasarruf.

Kaynaklar:

- [Teknik duyuru](https://www.notdiamond.ai/blog/not-diamond-code-intelligent-model-routing-for-coding-agents)
- [Interactive benchmark metodolojisi](https://www.notdiamond.ai/blog/interactive-benchmarks-a-new-methodology-for-evaluating-model-routing)
- [Code router dokümantasyonu](https://code.notdiamond.ai/docs/)
- [Custom router training](https://docs.notdiamond.ai/docs/router-training-quickstart)

Bu değerler bağımsız doğrulanmış sonuçlar değil, vendor tarafından raporlanıyor. Yine de mimari yön çok önemli: uzun coding session'larında cache-aware turn routing ekonomik sonucu task-only routing'den tamamen farklılaştırabilir.

Bizim çıkarımımız: İlk sürüm task-level/session-pinned kalabilir; fakat schema şimdiden `session_id`, `turn_index`, `current_model`, `cache_state`, `agent_stage` ve `recent_tool_outcomes` alanlarını desteklemeli.

## LiteLLM Auto Router

[LiteLLM Auto Router](https://docs.litellm.ai/docs/auto_router/) üç classifier tipi sunuyor:

- sub-millisecond heuristic;
- küçük LLM;
- keyword rules.

Complexity tier'larını farklı modellere veya Thompson-sampled pool'lara eşleyebiliyor. Context-window escalation, prompt caching ve session pinning içeriyor.

Raporladığı sonuçlardan bazıları:

- RouterArena'da %74,5 daha ucuz, frontier kalitesinin %87,3'ü;
- 21 Terminal-Bench görevinin ortak çözülen 16'sında Opus solve rate, %27 daha düşük maliyet;
- bir production kullanıcısında 272.876 istekte %51,1 maliyet tasarrufu.

Kaynak: [production case study](https://docs.litellm.ai/blog/auto-router-production-savings).

Bizim için gateway/benchmark baseline'ı olarak güçlü. Ancak tier mapping'in elle ayarlanması ve classifier'ın doğrudan bizim model-outcome verimizden öğrenmemesi nedeniyle nihai karar motorumuz olmamalı.

## vLLM Semantic Router

[vLLM Semantic Router](https://github.com/vllm-project/semantic-router), genel ve güçlü bir programlanabilir kontrol katmanı. 16 sinyal ailesini destekliyor:

- heuristic: authz, context, keyword, language, structure;
- learned: complexity, domain, embedding, KB, modality, fact-check, jailbreak, PII, preference, re-ask, user feedback.

Sinyalleri projection katmanında birleştirip rule/decision katmanında model veya recipe seçiyor. Self-hosted/private inference için uygun.

Kaynak: [Semantic Router overview](https://vllm-sr.ai/docs/overview/semantic-router-overview).

Bizim mimarimiz için çıkarım:

- `FeaturePipeline → Projection → Decision` ayrımı doğru;
- risk/privacy/domain sinyalleri capability tahmininden ayrı tutulmalı;
- policy açıklanabilir ve YAML/JSON ile düzenlenebilir olmalı;
- fakat karar kurallarının elle yazılması yerine capability projection'ı benchmarktan öğrenilmeli.

## Managed cloud router'ları

### Microsoft Foundry Model Router

[Microsoft Model Router](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-router-how-it-works), LLM değil, yüz binlerce örnek üzerinde eğitilmiş hafif bir ML model. System prompt, user messages, conversation history ve tool definitions dahil tam isteği analiz ediyor; Balanced, Cost ve Quality modlarına göre model seçiyor. Seçilen model response içinde açıklanıyor.

Microsoft ayrıca kullanıcıların kendi representative workload'u, kalite sınırı, maliyet ve p95 latency kriteriyle router'ı doğrudan baseline modele karşı değerlendirmesini öneriyor: [evaluation guide](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/evaluate-model-router).

Bu, bizim şu kararlarımızı güçlü biçimde doğruluyor:

- router küçük/ucuz bir predictor olmalı;
- eğitim verisi model outcome kayıtları olmalı;
- tek bir genel benchmark skoruna güvenilmemeli;
- kullanıcı workload'una özel acceptance criteria tanımlanmalı.

### Amazon Bedrock Intelligent Prompt Routing

[Amazon Bedrock Intelligent Prompt Routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html), aynı model ailesindeki iki adayın tahmini response quality'sine göre routing yapıyor. Varsayılan ve kullanıcı tarafından yapılandırılmış threshold'lar sunuyor. Anthropic, Llama ve Nova aileleri için destek veriyor.

AWS'nin [GA teknik yazısı](https://aws.amazon.com/blogs/machine-learning/use-amazon-bedrock-intelligent-prompt-routing-for-cost-and-latency-benefits/) bunu “kolay promptları ucuz modele, gerekli olanları güçlü modele” şeklinde tanımlıyor.

Bu sistem RouteLLM'e yakın ama model havuzu aynı aile ve iki modelle sınırlı. Bizim ilk MVP'yi iki-model olarak doğrulayıp sonra dört rotaya genişletmemiz için iyi bir emsal.

## OpenRouter Auto Router

[OpenRouter Auto Router](https://openrouter.ai/docs/guides/routing/routers/auto-router) yaklaşık 30 task tipine hızlı classification yapıyor. Daha sonra son yedi gündeki aggregate ve anonymized “share of spend” dağılımına göre modelleri sıralıyor ve kullanıcının `cost_tier` filtresini uyguluyor.

Avantajları:

- yeni modellere günler içinde uyum;
- training gerektirmeyen geniş model kataloğu;
- kolay fallback ve policy kısıtları.

Sınırı:

- harcama payı, başarı/kalite etiketi değildir;
- genel OpenRouter kullanıcılarının davranışı bizim Codex coding workload'umuzu temsil etmeyebilir;
- karar harici serviste verilir.

Bu nedenle comparison baseline olarak değerlidir ama ana policy olmamalı.

## Rule/gateway ürünleri neden farklı?

[Cloudflare Dynamic Routing](https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/) ve [Portkey Conditional Routing](https://portkey.ai/docs/product/ai-gateway/conditional-routing) condition, metadata, budget, rate limit, A/B, load balance ve fallback akışları oluşturuyor. [Google API Gateway Model Routing](https://docs.cloud.google.com/api-gateway/docs/model-routing-overview) da OpenAPI/payload parametreleriyle managed dispatch sağlıyor.

Bunlar iyi serving altyapılarıdır fakat şu soruyu kendileri öğrenmez:

```text
Bu görevde Luna başarısız olurken Terra veya Sol başarılı olur mu?
```

Bizim router predictor'ımız bu gateway'lerden birinin önünde veya içinde çalışabilir; onlarla rekabet etmek zorunda değil.

## Bizim tasarımımıza etkisi

### Korunacak kararlar

- Benchmark outcome matrisi merkezde kalacak.
- Her `model + reasoning effort` için ayrı başarı olasılığı üretilecek.
- Quality threshold'u geçen en ucuz/hızlı rota seçilecek.
- OOD veya düşük güven durumunda güçlü modele abstain/fallback yapılacak.
- Jev opsiyonel structured feature/baseline olacak.
- Router ve dispatcher birbirinden ayrılacak.

### Değiştirilecek kararlar

Önceki tasarımın `TaskCard` sözleşmesine session alanları eklenmeli:

```json
{
  "session_id": "...",
  "turn_index": 0,
  "routing_scope": "session",
  "current_route": null,
  "agent_stage": "initial",
  "cache_state": "cold",
  "recent_tool_outcomes": [],
  "recent_error_count": 0
}
```

v0.1 yalnız `turn_index = 0` için karar verip session'ı seçilen route'a pinleyebilir. Böylece ilk sürüm basit ve güvenli olur; veri sözleşmesi kırılmadan v0.2'de turn-level routing eklenebilir.

### Eklenecek baseline'lar

- Switchyard `coding_agent` LLM classifier profili;
- Switchyard stage-router;
- LiteLLM heuristic router;
- OpenRouter Auto Router;
- first-turn session-pinned learned router;
- ileride cache-aware turn router.

Bu baseline'lar açık ve çalıştırılabilir olduğunda bizim yaklaşımımızın gerçekten yenilik getirip getirmediğini gösterecek.

## Tavsiye edilen uygulama yönü

### v0.1 — Session-pinned benchmark router

- İlk kullanıcı mesajında route seç.
- Tüm Codex oturumunu o modele pinle.
- Yerel, benchmark-supervised predictor kullan.
- Hard guard ve abstention uygula.
- Kararı dry-run ve receipt ile açıkla.
- Switchyard/LiteLLM/OpenRouter baselines ile karşılaştır.

### v0.2 — Stage-aware router

- Read/search/planning/error/edit/test sinyallerini çıkar.
- Switchyard benzeri stage router baseline ekle.
- Cache kırılmasının gerçek token maliyetini ölç.
- Yalnız net ekonomik kazanç varsa turn-level model değiştirmeye izin ver.

### v0.3 — Feedback ve online adaptation

- Final test sonucu, re-open, human correction ve tool error'ları reward olarak kaydet.
- Drift ve yeni model sürümleri için shadow evaluation.
- Önce offline retraining; yeterli güven olmadan online policy update yok.

## Son hüküm

Gidişat doğru. Hatta Microsoft, AWS, RouteLLM ve Not Diamond'ın birbirinden bağımsız tasarımları aynı temel fikri doğruluyor: karar, model başarısı ve maliyet verisinden öğrenilmeli; statik task label tek başına yeterli değil.

Fakat açık kaynak projenin farkı net tanımlanmalı:

> Codex-native coding görevleri için, public ve yerel benchmark outcome matrisinden öğrenen; model + reasoning effort seçen; yerelde çalışan; kalibre edilmiş, açıklanabilir ve OOD durumunda abstain eden router.

LangChain bunun orchestration katmanını, Switchyard proxy/turn sinyallerini, vLLM policy mimarisini sağlıyor. Hiçbiri bizim özel Codex model havuzumuz için benchmark-supervised ve tamamen yerel policy'yi hazır olarak vermiyor. Dolayısıyla projeyi geliştirmek tekrar icat etmek değil; mevcut sistemlerde eksik kalan parçaları hedefli biçimde birleştirmek olacak.
