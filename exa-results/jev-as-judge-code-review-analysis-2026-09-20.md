# Jev-as-a-Judge + Router: Kodlama Ajanı İçin Uygulanabilir Tasarım

Tarih: 2026-09-20

## Yönetici özeti

LangChain'in X paylaşımındaki çalışma, önceki `Building a Harness with Jev` yazısından ayrıdır. Yeni çalışma, Jev'i bir **agent evaluator / judge** olarak deniyor. Ancak deney canlı agent döngüsünde her adımı durdurup düzeltmiyor; beş adet dondurulmuş weather-agent çıktısını tekrar tekrar puanlıyor. Bu nedenle çalışma, Jev'in düşük maliyetli ve kararlı bir sınıflandırıcı/judge olabileceğini gösteriyor, fakat kod değişikliklerinin doğruluğunu tek başına kanıtlamıyor.

Bizim proje için doğru sonuç şudur:

- Jev ilk istekte **router** olarak model seçer.
- Kod üretildikten sonra task + diff + ilgili kaynak kodu + çağıran kod + mevcut test/CI kanıtlarını içeren bir `ReviewPacket` Jev'e verilir.
- Jev, tek ve geniş bir "doğru mu?" sorusu yerine birden çok dar ölçütü paralel değerlendirir.
- Yüksek güvenli, düşük riskli değişiklikler tamamlanabilir.
- Belirsiz, riskli veya eksik görünen değişiklikler, repository'yi araçlarla okuyabilen Sol/Astra reviewer'a yükseltilir.
- Test/lint/type-check kanıt olarak tutulur ama nihai doğruluk kanıtı sayılmaz.
- Kritik güvenlik, veri, migration ve auth değişikliklerinde Jev nihai otorite olmaz.

Bu tasarım, ucuz modelleri daha agresif kullanmamıza izin verirken yanlış kabul edilen çözümleri sınırlamayı hedefler.

## Paylaşımdaki LangChain deneyi gerçekte ne yaptı?

Bir Deep Agents weather agent'ı için beş görev hazırlandı. Her görevde agent yalnızca bir kere çalıştırıldı ve tam çıktı donduruldu. Aynı beş sabit çıktı her judge tarafından 100 kez değerlendirildi. Judge'a verilen state şu alanlardan oluşuyordu:

- kullanıcı sorusu,
- beklenen davranış,
- final cevap,
- tool çağrılarının adları,
- arama sonucundan gelen kanıtlar.

Jev şu sinyalleri üretti:

- cevap kanıta dayanıyor mu,
- arama davranışı beklenen davranışa uyuyor mu,
- cevap yararlı mı,
- genel olarak geçti mi,
- sonuç `answered`, `clarification_needed` veya `poor` sınıflarından hangisi?

Yayımlanan sonuçta Jev, beş vakanın 100 tekrarındaki 500 ikili kararda insan etiketine tamamen uydu; ortalama 0.44 saniye ve çağrı başına 0.00035 dolar ölçüldü. Sürekli kalite puanı varyansı Luna, Terra ve Claude'a göre çok daha düşüktü.

Bu sonuç **500 bağımsız görevde yüzde 100 doğruluk** demek değildir. Beş benzersiz vaka, tek insan reviewer ve aynı çıktıların 100 tekrarı vardır. Güçlü kanıt, tekrar edilebilirlik ve maliyet üzerinedir; farklı alanlara genelleme henüz gösterilmemiştir.

Kaynaklar:

- [LangChain: Jev-as-a-Judge for Agent Evals](https://www.langchain.com/blog/jev-agent-evals-langsmith)
- [Deneyin açık kaynak kodu](https://github.com/danielgshea/jev-as-a-judge)
- [X paylaşımı](https://x.com/LangChain/status/2101454284927959080?s=20)

## Jev kodun kendisini görebilir mi?

Evet. Jev state olarak string veya yapılandırılmış JSON alır; kaynak kod ve git diff metin olduğu için doğrudan gönderilebilir. Jev 1.13 için belgelenen sınır, state + en uzun soru için 32 bin token; bütün sorularla toplamda 64 bin tokendir. Bu, orta büyüklükte bir diff ve ilgili kod parçaları için yeterli olabilir ama büyük bir repository'nin tamamını göndermek için yeterli değildir.

Önemli sınırlama: Jev kendi başına repository'yi gezmez, dosya açmaz, sembol aramaz, test çalıştırmaz ve açıklamalı hata raporu üretmez. Yalnızca kendisine verilen metin/JSON'u sınıflandırır. TypeSafe'ın kendi kılavuzu da Jev sorularının, gerekli bağlam verildiğinde bir uzmanın hızlıca verebileceği dar ve odaklı kararlar olmasını önerir. Yavaş ve çok aşamalı muhakeme gerektiren geniş soruların küçük sorulara bölünmesi gerekir.

Kaynaklar:

- [TypeSafe: State](https://docs.typesafe.ai/concepts/state)
- [TypeSafe: Jev modelleri ve bağlam sınırları](https://docs.typesafe.ai/models)
- [TypeSafe: Primitives](https://docs.typesafe.ai/primitives)

## Test bias endişesi doğru mu?

Evet. Aynı agent hem gereksinimi yorumlayıp hem uygulamayı hem de testi yazarsa, aynı yanlış varsayım üçüne de yansıyabilir. Testlerin geçmesi şu durumları tek başına yakalamaz:

- gereksinimin eksik veya yanlış yorumlanması,
- yalnızca mutlu yolun test edilmesi,
- testin uygulamanın ayrıntısını tekrar etmesi,
- repository'nin örtük sözleşmelerinin kaçırılması,
- çağıran kod veya geriye dönük uyumluluk regresyonları,
- güvenlik ve veri sınırı hataları.

Lint ve type-check de esas olarak biçimsel/yapısal kanıttır; ürün davranışının doğru olduğunu ispatlamaz. Buna rağmen self-generated testler tamamen değersiz değildir. Özellikle test eski kodda başarısız olup yeni kodda geçiyorsa iyi bir sinyal üretir; ancak tek kabul ölçütü olmamalıdır. SWE-bench'in temel doğrulaması, agent'ın görmediği/golden PR'dan türetilmiş bağımsız fail-to-pass testlerine dayanır.

Kaynaklar:

- [SWE-bench değerlendirme yöntemi](https://www.swebench.com/original.html)
- [SWT-Bench: agent tarafından üretilen testlerin bağımsız golden patch ile doğrulanması](https://arxiv.org/abs/2406.12952)

## Önerilen birleşik mimari

```text
Kullanıcı isteği
    |
    v
Task normalizer: sabit acceptance contract
    |
    v
Jev Router: Luna / Terra / Sol / Astra + reasoning seviyesi
    |
    v
Kodlama agent'ı: kod + test + açıklama
    |
    v
Yerel Evidence Collector
  - git diff ve diff istatistikleri
  - değişen fonksiyonların tam gövdeleri
  - caller/callee ve interface bağlamı
  - mevcut insan-yazımı regresyon testleri
  - agent-yazımı testler ayrı etiketli
  - lint/typecheck/build/test sonuçları
    |
    v
Jev Code Judge: dar, paralel kararlar
    |
    +--> PASS: düşük risk + yüksek güven -> tamamla
    |
    +--> REVISE: açık eksik -> aynı modele tekrar ver
    |
    +--> ESCALATE: belirsiz/riskli -> Sol/Astra read-only reviewer
    |
    +--> BLOCK: kritik policy ihlali -> insan/sert kural
```

### Jev'e verilecek `ReviewPacket`

```json
{
  "task": {
    "request": "...",
    "acceptance_criteria": ["..."],
    "forbidden_changes": ["..."]
  },
  "route": {
    "worker_model": "gpt-5.6-luna",
    "risk_tier": "medium"
  },
  "change": {
    "diff": "...",
    "changed_symbols": ["..."],
    "relevant_original_code": ["..."],
    "callers_and_interfaces": ["..."]
  },
  "evidence": {
    "existing_tests": "...",
    "agent_authored_tests": "...",
    "test_results": "...",
    "typecheck": "...",
    "lint": "..."
  }
}
```

Agent tarafından yazılan testler ayrı etiketlenir. Judge bunları bağımsız doğrulama gibi görmez.

### Tek Jev çağrısında sorulacak atomik kararlar

- Değişiklik sabit acceptance criteria'nın tamamını kapsıyor mu?
- Diff, istenmeyen kapsam genişlemesi içeriyor mu?
- Uygulama yalnızca semptomu gizleyip temel hatayı bırakıyor mu?
- Public API, hata davranışı veya veri sözleşmesi istemeden değişmiş mi?
- İlgili caller/interface bağlamında belirgin bir regresyon riski var mı?
- Agent-yazımı testler uygulamayı tekrarlayan/tautological testler mi?
- Mevcut kanıt tamamlamak için yeterli mi?
- Repository araçları olan güçlü bir reviewer gerekli mi?
- Risk seviyesi `low`, `medium`, `high`, `critical` seçeneklerinden hangisi?

Jev bu sorulara olasılık verir. Tamir talimatını ise test hatası, statik analiz veya gerektiğinde açıklama üreten güçlü reviewer verir.

## Normal kullanım örnekleri

### 1. Küçük isimlendirme veya lokal UI değişikliği

Router Luna'yı seçer. Agent değişikliği yapar. Jev task + diff + ilgili component'i inceler; kapsam dışı dosya, API değişikliği veya eksik acceptance kriteri görmezse tamamlanır. Sol çağrısı yapılmaz.

### 2. Orta zorlukta bug fix

Router Terra'yı seçer. Agent kendi testini yazıp geçirir. Jev eski davranış, issue açıklaması, yeni diff ve caller bağlamını birlikte görür. Fix yalnızca tek örneği hard-code etmişse veya edge case bırakmışsa `needs_deep_review` yükselir. Sol reviewer repository'yi okuyup hedefli feedback üretir; Terra düzeltir veya görev Sol'a devredilir.

### 3. Refactor

Testler geçse bile Jev API uyumluluğu, hata semantiği, yan etkiler, kaldırılan davranış ve gereksiz kapsam değişimini ayrı sorularla değerlendirir. Yüksek belirsizlikte doğrudan kodu okuyabilen Sol reviewer devreye girer.

### 4. Yeni özellik

Router görev karmaşıklığına göre Terra/Sol seçer. Final judge acceptance kriterlerinin tek tek karşılanıp karşılanmadığını, entegrasyon noktalarını, config/migration/fallback ihtiyacını ve mevcut kullanıcı davranışını kontrol eder. Testlerin geçmesi sadece kanıtlardan biridir.

### 5. Auth, ödeme, migration veya veri izolasyonu

Hard policy ilk aşamada zaten Sol/Astra seçer. Jev ek bir risk ve kapsam kontrolü yapabilir ama görevi tek başına kabul edemez. Mevcut testler + doğrudan code review + gerektiğinde insan onayı gerekir.

### 6. PR review

Router diff büyüklüğü ve risk alanına göre reviewer modelini seçer. Jev önce diff'i konu başlıklarına ayırır ve riskli hunileri işaretler. Reviewer yalnızca değişen satırlara değil, full repository'deki caller, interface ve benzer implementasyonlara bakar. LangChain'in ReviewBench çalışması da gerçek review kusurlarının çoğunun yalnızca diff'ten değil, çevre kodun örtük sözleşmelerinden anlaşıldığını gösteriyor.

Kaynak: [LangChain ReviewBench](https://www.langchain.com/blog/evaluating-code-review-agents-with-reviewbench)

## Ne zaman Jev yeterli değildir?

Şu durumlarda repository araçları olan açıklamalı LLM reviewer gerekir:

- diff/bağlam 32k sınırına sığmıyorsa,
- hata çok dosyalı davranış zincirine bağlıysa,
- concurrency, lifecycle veya dağıtık durum muhakemesi gerekiyorsa,
- güvenlik/data isolation söz konusuysa,
- Jev ölçütleri birbiriyle çelişiyorsa,
- düzeltilecek yer ve gerekçe üretmek gerekiyorsa.

Jev'in avantajı, her görevi pahalı reviewer'a göndermeden bu az sayıdaki vakayı seçmektir.

## Benchmark planı

Bu yapıyı önce shadow mode'da sınamalıyız. Judge karar üretir ama agent akışını değiştirmez.

Karşılaştırılacak kollar:

1. Always Sol
2. Router only
3. Router + test/lint/type-check
4. Router + Jev task/diff judge
5. Router + Jev + seçici Sol reviewer

Kod çözme değerlendirmesinde SWE-bench Verified benzeri bağımsız/hidden fail-to-pass test sonucu gerçek etiket olur. Jev hidden testleri görmeden task + patch + repo bağlamından `accept/revise/escalate` tahmini yapar.

Öncelikli metrikler:

- resolved rate,
- false-pass: Jev'in kabul ettiği ama hidden testte kalan görev,
- false-fail: doğru patch'i gereksiz reddetme,
- escalation precision/recall,
- judge sayesinde kurtarılan görev,
- Sol/Astra çağrı oranı,
- toplam maliyet ve süre,
- Jev calibration (Brier/ECE),
- risk alanına göre ayrı sonuçlar.

Birinci başarı ölçütü toplam judge accuracy değil, **false-pass oranının düşüklüğü** olmalıdır.

## Sonuç

Jev'i sadece router değil, task + diff + seçilmiş repository bağlamını gören ucuz bir semantic gate olarak kullanmak mantıklıdır. Fakat Jev'i tam bir kıdemli code reviewer gibi konumlandırmak doğru değildir. En güçlü tasarım:

1. Jev ile ucuz model routing,
2. yerel ve bağımsız evidence collection,
3. Jev ile atomik diff/task yargıları,
4. yalnızca belirsiz veya riskli görevlerde Sol/Astra code reviewer,
5. kritik işlerde sert politika ve insan/bağımsız test doğrulaması.

Bu yapı self-generated test bias problemini tamamen yok etmez; testleri tek gerçek olmaktan çıkarır ve doğrudan kod/diff incelemesiyle, bağımsız sözleşmeyle ve seçici güçlü reviewer ile dengeler.
