# Router ve cascade araştırması: %30–40 tasarrufa giden yol

Tarih: 2026-09-22

## Araştırma kapsamı

Exa üzerinde dokuz geniş ve beş hedefli arama yapıldı; toplam arama kapasitesi 132 sonuçtu. URL tekrarları, ikincil özetler ve ölçümsüz tanıtımlar elendi. Southbridge, OpenRouter, LangChain, NVIDIA Switchyard, Not Diamond Code, LiteLLM, SWE-Router, RouteLLM, Microsoft Foundry, AWS Bedrock ve vLLM Semantic Router'ın birincil kaynakları incelendi. Harrison Chase ve LangChain'in güncel paylaşımları yerel X API ile doğrulandı.

## Kısa karar

Southbridge bizim prompt-öncesi router'ımızı yapmadı. Kullandığı yapı seçici inceleme cascade'idir:

1. Jev dar ve kaynakla sınırlandırılmış kararları neredeyse bütün veri üzerinde verir.
2. Seçilmiş beş aile Luna'ya inceleme için gider; yayımlanan sonuçta Jev-only kolunda dört abstention vardır, dolayısıyla beş review'ün tamamını yalnız abstention diye yorumlamak doğru değildir.
3. Güçlü/üretken model bütün trafiğin yalnız %2,5'ini görür.

Bizim sistemimizde ise Jev yalnız isteme bakar ve görevlerin %68'ini doğrudan Sol'a gönderir. Southbridge'in büyük ekonomik farkının ana nedeni Jev'in daha ucuz olması değil, pahalı incelemenin çok seyrek ve kanıta dayalı tetiklenmesidir.

## Southbridge gerçekte ne yaptı?

Kaynak: [Southbridge Jev entity resolution](https://www.southbridge.ai/blog/jev-entity-resolution)

| Sistem | Sonuç | Pahalı inceleme | Maliyet | Birikmiş çağrı süresi |
|---|---:|---:|---:|---:|
| Jev only | 195/200 aile eşleşti; 1 hata + 4 abstain | 0 | $0,0337 | 56 sn |
| Jev + 5 Luna review | 199/200; 1 hata, 0 abstain | 5/200 = %2,5 | $0,0435 | 115 sn |
| Luna + Gemini | 199/200 | 10/52 batch ikinci modele sevk | $0,3012 (8 çağrı fiyatlanmamış) | 715 sn |
| Fable | 200/200 | Her şeyi frontier çözüyor | $9,83 | 845 sn |

Jev + beş Luna incelemesi Fable'dan yalnız 0,5 yüzde puan düşük kaldı; model maliyeti %99,56 azaldı ve ölçülen çağrı-zamanı throughput'u 7,35 kat arttı.

Bu sonuç bizimkinden üç açıdan farklıdır:

- Görev açık uçlu kod üretimi değil, yapılandırılmış entity-resolution kararıdır.
- Jev yalnız route etmiyor; ana karar işinin kendisini yapıyor.
- Luna tüm belirsiz görünen işleri değil, yalnız beş abstention/review ailesini görüyor.

Southbridge'in en önemli hata bulgusu da bizim için değerlidir: tek kalan yanlış cevapta Jev'in seçtiği etiket olasılığı 0,53'tü ve pipeline probability gate kullanmadan etiketi kabul etti. Yani karar modeli kullanmak yetmiyor; düşük marj ve düşük güven ayrıca abstain/escalate üretmelidir.

## Bizim yaklaşımımıza benzeyen sistemler

| Sistem | Mimari | Yayımlanan sonuç | Bizim için alınacak fikir | Kanıt niteliği |
|---|---|---|---|---|
| [OpenRouter Jev cascade](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-verified-cascade) | Luna cevaplar → Jev kanıt desteğini kontrol eder → gerekirse Astra | 50 RAG sorusunda 2/50 escalation; $0,012 vs Astra $0,175; iki koşuda cascade 0 yanlış | Çözümü gördükten sonra verify/escalate | Resmî worked example; küçük ve gürültülü. Son koşuda Luna-only de 0 yanlış ve $0,004 olduğu için ekonomik üstünlük kanıtı zayıf |
| [NVIDIA Switchyard + LangChain](https://www.langchain.com/blog/switchyard-agent-routing-benchmark) | Coding-agent çağrılarını turn/stage düzeyinde weak/strong modele yollar | Çağrıların %7'si Opus; %74 maliyet azalması; Opus doğruluğunun %93'ü | İlk prompt yerine agent evresi, tool sonucu ve hata sinyali | Açık kaynak sistem üzerinde üretici/entegrasyon ekibinin benchmark'ı; yaklaşık 6 puan kalite kaybı var |
| [Switchyard stage/escalation](https://github.com/NVIDIA-NeMo/Switchyard) | Routine edit/write → efficient; exploration/error/spinning → capable; weak turn sonrası judge ve strong latch | Üstteki LangChain sonucu; algoritmalar ayrıca açık | Tool geçmişi, iki ardışık hata, session latch, fail-safe | Apache-2.0 ve uygulanabilir; proje pre-alpha |
| [Not Diamond Code](https://www.notdiamond.ai/blog/not-diamond-code-intelligent-model-routing-for-coding-agents) | Her agent adımında model + reasoning effort; gelecekteki reward/cost ve KV cache hesaba katılır | Poly-SWE'de Opus'a yakın kalite ve %39 düşük maliyet; LongCodeQA %61; açık modellerle +%3,6 kalite ve %66 tasarruf | Turn-level, cache-aware, outcome-supervised politika | Vendor iddiası; router kapalı/gated, bağımsız tekrar yok |
| [LiteLLM Auto Router](https://docs.litellm.ai/docs/auto_router/) | Heuristic/küçük LLM/keyword ile complexity tier; session pinning ve context escalation | 272.876 üretim isteğinde %51,1 tasarruf; RouterArena'da %74,5 ucuz ama frontier kalitesinin %87,3'ü; Terminal-Bench ortak 16 görevde %27 ucuz | Üç tier, shadow rollout, per-request cost accounting | Büyük üretim maliyet örneği var; üretim kalite ground-truth'u yayımlanmamış; Terminal-Bench ortak-solved seçimi iyimser |
| [SWE-Router](https://arxiv.org/html/2607.00053) | Ucuz model 1–4 keşif turu yapar; partial trajectory'den devam/escalate kararı | SWE-Bench Verified held-out'ta prompt-only router'a göre Route-AUC +12 ila +15,3 puan | Bizim en yakın akademik referansımız: kısa Luna keşfi + kanıtla escalation | Birincil araştırma ve trajectory verisi açık; gerçek held-out yalnız 100 task ve distribution shift raporlanıyor |
| [RouteLLM](https://arxiv.org/html/2406.18665v4) | Preference/outcome verisinden strong-win olasılığı öğrenir; threshold süpürür | MT-Bench'te GPT-4 kalitesinin %95'i, maliyette 3,66× düşüş; geliştirilmiş router yaklaşık %14 GPT-4 çağrısı kullanıyor | Tek task label yerine pairwise outcome verisi ve cost-quality curve | Açık kaynak akademik çalışma; coding-agent/trajectory testi değil |
| [AWS Bedrock prompt routing](https://aws.amazon.com/blogs/machine-learning/use-amazon-bedrock-intelligent-prompt-routing-for-cost-and-latency-benefits/) | Aynı ailede weak/strong response-quality tahmini | Güçlü kalite eşleşmesinde Nova %35, Anthropic %56, Meta %16 tasarruf; RAG'de isteklerin %87'si Haiku'ya gidince %63,6 | %30–40 mümkündür, fakat ucuz tier oranı çok yükselmelidir | AWS iç testi; görev ve reward-model ayrıntıları sınırlı |
| [Microsoft Foundry Model Router](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-router-how-it-works) | Full request, history ve tools; yüz binlerce outcome; Balanced/Cost/Quality | Resmî belgede coding'e özgü karşılaştırılabilir tek oran yok | Outcome-supervised predictor, quality band ve per-turn karar | Tasarım güçlü, sonuç bizim benchmark'la doğrudan karşılaştırılamıyor |
| [vLLM Semantic Router](https://vllm-sr.ai/docs/overview/semantic-router-overview) | Complexity, domain, context, safety, preference ve feedback sinyallerini projection/policy ile birleştirir | Genel reasoning testlerinde token/latency kazançları var; coding-agent kalite sonucu yok | Risk/capability/cost sinyallerini ayrı tutmak | Açık kaynak serving/control plane; capability predictor'ı ayrıca kalibre etmek gerekir |

## X araştırmasının sonucu

Yerel X API ile Harrison Chase ve LangChain'in 15–22 Eylül 2026 paylaşımları doğrulandı:

- Harrison Chase, Jev'i metin üreticisi değil hızlı ve ucuz bir decision model olarak konumluyor: [paylaşım](https://x.com/hwchase17/status/2100773130041950570).
- Jev-as-a-judge kullanımını özellikle yüksek hacimli trace scoring için öneriyor: [paylaşım](https://x.com/hwchase17/status/2101671063272796549).
- Jev'e yakın açık kaynak SemIf gibi decision-model alternatiflerini vurguluyor: [paylaşım](https://x.com/hwchase17/status/2102065131202945152).
- LangChain'in yüksek etkileşim alan paylaşımı judge benchmark'ıdır; coding router benchmark'ı değildir: [paylaşım](https://x.com/LangChain/status/2101454284927959080).

X'teki geniş Jev araması çok sayıda ölçümsüz demo ve yeniden anlatım üretti. Ölçülebilir coding-router sonucu veren yüksek sinyalli kaynaklar hâlâ Switchyard, Not Diamond, LiteLLM ve SWE-Router'dır. X gönderileri mimari yönü destekliyor ama bağımsız benchmark yerine geçmiyor.

## Yerel sonuçların yeni karşı-olgusal analizi

Mevcut 200 paired LiveCodeBench kaydında router skorları, Luna/Sol sonuçları ve gerçek provider maliyetleri yeniden birleştirildi.

| İzin verilen toplam başarı | En ucuz bulunan prompt-only eşik | Sol çağrısı | Tasarruf |
|---:|---:|---:|---:|
| 193/200 (Sol ile aynı) | Mevcut kalite-first bölgesi | 134 | %12,90 |
| 192/200 | Daha agresif | 121 | %17,24 |
| 191/200 | Daha agresif | 108 | %22,48 |

Bu threshold sweep test sonuçlarına bakılarak yapıldığı için yeni bir ürün eşiği değildir; yalnız mevcut sinyalin kapasitesini gösterir. Mevcut prompt-only skoru aynı veri üzerinde %30–40 tasarrufa ulaşırken Sol kalitesini koruyamıyor.

Oracle karşı-olgusu önemlidir: Her görevde Luna'nın geçip geçmeyeceğini önceden bilseydik, yalnız Luna'nın kaldığı ve Sol'un geçtiği 17 görevi Sol'a vermek 193/200 sonucu korur ve yaklaşık %70,9 tasarruf sağlardı. Dolayısıyla model tamamlayıcılığı ve ekonomik alan var; darboğaz Jev'in yalnız prompttan doğru 17 görevi seçememesi.

Dokunulmamış ikinci 100 üzerinde yapılan post-hoc keşif de trade-off'u gösterir:

| Held-out başarı | Sol çağrısı | Tasarruf |
|---:|---:|---:|
| 94/100 | 63 | %15,08 |
| 93/100 | 55 | %21,34 |
| 92/100 | 40 | %31,79 |

Son satır hedeflenen %30 bandının mümkün olabileceğini gösterir, fakat eşik held-out sonuçları görüldükten sonra bulunduğu için kanıt değildir. Aynı politika yeni ve hiç görülmemiş bir sette dondurularak doğrulanmalıdır.

## %30–40 tasarruf için önerilen v3

Mevcut quality-first router korunmalı; onun yerine geçmeden ikinci bir `balanced` politika eklenmelidir.

```text
İstek
  ├─ deterministik hard guard / açık zor görev → Sol
  └─ diğerleri → Luna ile kısa çözüm veya 1–3 keşif turu
                  └─ bağımsız kanıt paketi
                       task + diff/code + tool sonuçları + test stderr + değişen dosyalar
                         └─ Jev atomik risk kararları
                              ├─ güvenli → Luna ile devam/kabul
                              └─ riskli/belirsiz → Sol temiz bağlamla yeniden başlar
```

Ana değişiklikler:

1. **Prompt-only kararı tek sinyal olmaktan çıkar.** SWE-Router gibi Luna'nın kısa trajectory'si görülür.
2. **Sol oranı değil cost-weighted Sol payı optimize edilir.** Şu an Luna'ya giden kolay görevler zaten ucuz; pahalı token üreten Sol görevleri faturayı domine ediyor.
3. **Jev soruları darlaştırılır.** `fully_correct?` yerine acceptance-criterion coverage, concrete counterexample, repeated error, missing evidence, unsupported assumption ve escalation benefit ayrı sorulur.
4. **Abstention gerçek rota olur.** Düşük probability margin, OOD, parse hatası veya çelişkili sinyal Sol'a gider.
5. **Session/stage bilgisi kullanılır.** Exploration, error recovery ve spinning Sol lehine; mekanik edit/write ve başarılı test ilerlemesi Luna lehine sinyal olur.
6. **Ara tier denenir.** Luna → Terra → Sol üçlüsü, pahalı fakat Sol gerektirmeyen görevleri Terra'da tutabilir.
7. **Cache maliyeti hesaba katılır.** Turn başına model değiştirmek KV cache'i bozuyorsa beklenen toplam oturum maliyetiyle karar verilir.

## Deney planı ve kabul kapısı

1. Mevcut 200 kayıtta yeni politika tamamen offline/shadow değerlendirilir; yeni worker harcaması yapılmaz.
2. Eşik yalnız geliştirme bölümünde seçilir. Hedefler: en az %30 tasarruf, Sol'a göre en fazla 2 yüzde puan başarı kaybı, false-accept için ayrı üst sınır.
3. Politika dondurulur ve en az 300 yeni paired görevde çalıştırılır. Aynı görevde Luna, Sol ve cascade sonuçları saklanır.
4. Sonra SWE-Bench Verified/Pro ve Terminal-Bench 2'de trajectory-aware varyant değerlendirilir. LiveCodeBench sonucu repository-agent genellemesi sayılmaz.
5. Switchyard classifier, stage router ve escalation router çalıştırılabilir baseline olarak aynı veri üzerinde karşılaştırılır.
6. Rapor: pass@1/resolved, paired fark, bootstrap CI, cost-weighted strong share, gerçek USD, p50/p95 latency, escalation precision/recall, false accept ve OOD oranı.

İlk ekonomik hedef olarak Sol çağrı oranı yaklaşık %40–50 bandına indirilmelidir; ancak kabul kararı çağrı sayısıyla değil gerçek maliyet ve kaliteyle verilmelidir. Kalite-first mod değişmeden kalmalı, balanced mod ancak yeni held-out kapısını geçerse varsayılan adayı olmalıdır.

## Son hüküm

Bizim temelimiz yanlış değil; yalnız ilk nesil ve prompt-only. Southbridge'in büyük kazancı Jev'i asıl karar işçisi yapıp Luna'yı yalnız %2,5'lik inceleme kuyruğuna koymasından geliyor. Coding tarafındaki en güçlü ortak desen ise Switchyard, Not Diamond ve SWE-Router'da aynı: ucuz model önce çalışır, sistem gerçek ilerleme/hata kanıtını görür, pahalı model ancak gerektiğinde devreye girer.

Bu nedenle sıradaki adım eşiği rastgele gevşetmek değil, **Luna-first + trajectory-aware Jev verification + selective Sol escalation** politikasını ekleyip yeni held-out veri üzerinde %30–40 tasarruf kapısını test etmektir.
