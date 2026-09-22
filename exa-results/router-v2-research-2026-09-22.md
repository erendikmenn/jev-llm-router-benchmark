# Router v2 araştırması: Jev ile çözüm-duyarlı cascade

Tarih: 2026-09-22  
Araştırma aralığı: 2025-09-22–2026-09-22  
Yöntem: Exa üzerinde dört geniş ve dört hedefli arama (toplam 100 sonuç kapasiteli), birincil kaynakların tam metin incelemesi ve Harrison Chase/LangChain gönderilerinin yerel X API ile doğrulanması.

## Kısa karar

Sadece kullanıcı istemine bakıp tek seferde model seçmek, kodlama ajanları için yeterince güçlü değil. En iyi yapı iki aşamalı olmalı:

1. Ucuz bir ön yönlendirme; açıkça zor veya riskli işleri baştan güçlü modele verir.
2. Diğer işlerde Luna kısa bir çözüm/keşif üretir; Jev problem, aday kod ve ilerleme kanıtını dar ve tipli sorularla inceler. Hata riski kalibre edilmiş eşiği geçerse aynı işi Sol/Astra temiz bağlamla yeniden çözer.

Jev doğruluğu onaylayan nihai kapı değildir. Gizli test, bağımsız test veya depo doğrulaması gerçek doğruluk etiketidir. Jev yalnızca **escalation kararı** verir. Bu ayrım, modelin kendi yazdığı testleri değerlendirerek kendisini onaylaması sorununu azaltır.

## Kaynakların ortak söylediği şey

### LangChain ve Harrison Chase

- [Building a harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev), Jev'i serbest metin üreten bir LLM yerine tipli olasılıklar döndüren hızlı bir “System One” karar modeli olarak konumluyor. Aynı istekte birden fazla sorunun bağımsız ve paralel sorulması; model seçimi ve risk kapıları için doğrudan uygun.
- [How to build a custom agent harness](https://www.langchain.com/blog/how-to-build-a-custom-agent-harness), başarının yalnız modelden değil model etrafındaki harness'ten geldiğini; model/tool öncesi ve sonrası middleware, deterministik politika, bağlam yönetimi ve model değiştirme noktalarını vurguluyor.
- [Jev is now available in LangSmith evals](https://www.langchain.com/blog/jev-is-now-available-in-langsmith-evals), dar ve tipli kriterlerle Jev'in judge olarak kullanımını gösteriyor. Raporlanan hız/istikrar umut verici olsa da çalışma tek bir ajan testine dayanıyor; bu nedenle bizim kabul ölçümüz olamaz.
- [TypeSafe model routing belgeleri](https://docs.langchain.com/oss/python/integrations/providers/typesafe#model-routing), `Choice`, `Noul` ve `Score` gibi tipli kararları ve birden fazla sorunun paralel değerlendirilmesini gösteriyor. Güncel middleware örneği hâlâ son kullanıcı mesajına bakıp çalışma boyunca tek model seçiyor; bizim çözüm-duyarlı ikinci aşamamız bundan daha zengin.
- [LangSmith decision models](https://docs.langchain.com/langsmith/llm-gateway-decision-models), Jev'e sağlayıcı bağımlılığı oluşturmamamız gerektiğini gösteriyor: açık kaynak SemIf gibi karar modelleri aynı arayüzün arkasına takılabilmeli.

Yerel X API ile doğrulanan önemli gönderiler:

- [Harrison Chase: custom agent harness](https://x.com/hwchase17/status/2098866608785473858)
- [Harrison Chase: constrained output ile Jev harness](https://x.com/hwchase17/status/2100773130041950570)
- [Harrison Chase: “Jev as a judge”](https://x.com/hwchase17/status/2101671063272796549)
- [Harrison Chase: ajan geliştirmek harness geliştirmektir](https://x.com/hwchase17/status/2097720484431360365)
- [Harrison Chase: açık kaynak karar modelleri/SemIf](https://x.com/hwchase17/status/2102065131202945152)
- [LangChain: Jev as a Judge](https://x.com/LangChain/status/2101454284927959080)
- [LangChain: LangSmith Jev entegrasyonu](https://x.com/LangChain/status/2102081155277246532)

### Router literatürü

- [SWE-Router](https://arxiv.org/html/2607.00053), yazılım görevlerinde sadece prompt'a dayalı yönlendirmenin bilgi sınırı olduğunu gösteriyor. Ucuz modelin birkaç adım ilerlemesini görmek, kısmi trajectory üzerinden yükseltme kararı vermek ve güçlü modeli gerekirse temiz başlatmak Route-AUC'yi 12–15,3 puan artırıyor.
- [The Routing Plateau](https://arxiv.org/html/2606.07587), 21 router ve beş benchmark üzerinde karmaşık router'ların sık sık basit kNN taban çizgisini geçemediğini; zor örneklerin küçük bir bölümünün oracle boşluğunun çoğunu oluşturduğunu buluyor. Bu, karmaşıklık yerine ölçülen ek sinyal istememiz gerektiğini doğruluyor.
- [Oracle gap and label noise](https://arxiv.org/html/2607.03436v2), tek örneklemli model etiketlerinin stochastic olduğunu ve raporlanan oracle boşluğunun yüzde 12–36'sının ölçüm gürültüsü olabileceğini gösteriyor. Sonuçlar tekrar örnekleme ve güven aralıklarıyla raporlanmalı.
- [RouteLLM](https://arxiv.org/html/2406.18665v4), model tercihini öğrenip eşik kalibrasyonu yaparak kendi deneylerinde kaliteyi büyük ölçüde korurken iki kattan fazla maliyet azalması raporluyor.
- [RouteNLP](https://arxiv.org/html/2604.23577), kapalı çevrim ve hata kümelerine göre yeniden kalibrasyon yaklaşımını savunuyor.
- [LLMRouterBench](https://aclanthology.org/2026.findings-acl.1881.pdf), 400 bin örnek, 21 veri seti ve 33 modelle model havuzu seçiminin router algoritması kadar önemli olduğunu; sofistike router'ların basit taban çizgilerini her zaman geçmediğini gösteriyor.

### Jev cascade ve judge riski

- [Southbridge Jev entity resolution](https://www.southbridge.ai/blog/jev-entity-resolution), Jev'i tek başına kullanınca doğruluk kaybı olduğunu; dar sorular, belirsiz örnekleri güçlü modele sevk etme ve cascade ile kaliteye yaklaşırken çok büyük maliyet/throughput kazancı elde edilebildiğini raporluyor.
- Kod judge araştırmaları ([JudgeBench-Code](https://arxiv.org/abs/2609.02246), [arXiv:2604.16790](https://arxiv.org/abs/2604.16790), [EACL 2026 finding](https://aclanthology.org/anthology-files/anthology-files/pdf/findings/2026.findings-eacl.70.pdf)) serbest biçimli LLM judge'ların kod doğruluğunda yanlı ve kırılgan olabildiğini gösteriyor. Sonuç: judge sinyali doğruluk etiketi değil, yalnız kaynak ayırma sinyalidir.

## Bu projeye uygulanan mimari

```text
İstek
  └─ deterministik risk kuralları + Jev ön-yönlendirme
       ├─ açıkça zor/riskli → Sol veya Astra
       └─ belirsiz/ucuz uygun → Luna çözümü
                                └─ Jev çözüm denetimi
                                     ├─ risk < sabit eşik → Luna çıktısı
                                     └─ risk ≥ sabit eşik → Sol temiz yeniden çözüm
                                                           └─ bağımsız gizli test
```

Jev'e şu dar sinyaller soruluyor: tam doğruluk olasılığı, somut edge-case riski, karmaşıklık riski, güçlü modelin fayda olasılığı ve en olası hata sınıfı. Escalation skoru bu sinyallerin muhafazakâr maksimumudur. Eşik geliştirme/calibration bölmesinde seçilir ve dokunulmamış test bölmesinde dondurulur.

## Kabul ölçütleri

Router'ın “başarılı” sayılması için aynı dokunulmamış örneklerde şu değerler birlikte raporlanmalı:

- Luna, Sol ve cascade `pass@1`;
- model-birliği oracle'ı (`Luna OR Sol`) ve cascade-oracle boşluğu;
- güçlü model çağrı oranı ve sağlayıcının gerçek USD maliyeti;
- uçtan uca latency dağılımı;
- Luna hatalarını yakalama oranı ve gereksiz escalation oranı;
- en az üç tekrar veya bootstrap güven aralığı;
- eşik seçiminin test etiketlerinden tamamen ayrı olduğuna dair manifest.

Ana hedef yalnız “Sol'dan ucuz” değildir: cascade, Sol kalitesini korumalı ya da model tamamlayıcılığı sayesinde geçmeli; bunu daha az Sol çağrısıyla yapmalıdır.

## Sonraki teknik iterasyon

LiveCodeBench kısa çözüm üretiminde işe yarayan yapıyı repo görevlerine taşırken Luna'ya 1–2 tur dosya/trace keşfi yaptırılmalı. Jev istem, diff, test kanıtı, hata çıktısı ve trajectory üzerinden tipli risk üretmeli. Escalation olduğunda güçlü modele Luna'nın serbest muhakemesi değil, orijinal görev ve doğrulanmış kanıt paketi verilmelidir. Böylece yanlış reasoning miras alınmaz. SWE-bench Verified/Pro ve Terminal-Bench 2 bu agentic varyantın kabul testleri olmalıdır.
