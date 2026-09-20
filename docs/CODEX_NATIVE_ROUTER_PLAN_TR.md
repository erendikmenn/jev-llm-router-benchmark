# Codex-native yazılım mühendisliği router'ı

Durum: araştırma ve uygulama planı
Tarih: 2026-09-19

## Amaç

Bu projenin bir sonraki sürümü, yalnızca Luna ve Sol yanıtlarını OpenRouter üzerinden karşılaştıran bir benchmark olmayacaktır. Hedef, kullanıcının normal Codex oturumunda verdiği yazılım mühendisliği görevini uygun Codex subagent'ına yönlendiren, sonucu yerel testlerle doğrulayan ve yalnız riskli/başarısız sonuçları daha güçlü bir modele yükselten açık kaynak bir workflow oluşturmaktır.

Ana hedef modeller:

- GPT-5.6 Luna: açık, dar, tekrarlı ve yüksek hacimli işler.
- GPT-5.6 Terra: gündelik uygulama, keşif ve orta karmaşıklıktaki işler.
- GPT-5.6 Sol: karmaşık profesyonel uygulama ve hata ayıklama.
- GPT-6 Astra: en zor, belirsiz, uzun soluklu veya yüksek riskli uçtan uca işler.

## Önemli sınır

Codex içinde çalışan hedef subagent'lar ayrı bir Responses API entegrasyonu gerektirmez; mevcut Codex oturumunun kimliği ve kullanım hakkıyla çalışır. Bununla birlikte modeller fiziksel olarak yerel bilgisayarda inference yapmaz; Codex hizmeti üzerinden çalışır.

Jev günümüzde OpenRouter/TypeSafe üzerinden çağrılıyorsa bu çağrı haricidir. Bu nedenle proje iki çalışma modu sunmalıdır:

1. `native`: Sıfır üçüncü taraf router çağrısı. Deterministik kurallar ve ana Codex ajanının yapılandırılmış kararı kullanılır.
2. `jev`: Yalnızca küçültülmüş ve temizlenmiş routing kartı Jev'ye gönderilir. Repository içeriği, kod, secret veya tam konuşma varsayılan olarak gönderilmez. Uygulama yine Codex subagent'ı tarafından yapılır.

## Önerilen mimari

```text
Kullanıcı görevi
      |
      v
Yerel routing kartı
(görev türü, kapsam, risk, testler, diller; secret/kod yok)
      |
      +--> deterministic hard guards
      |      güvenlik/veri kaybı/migration -> Sol veya Astra + review
      |
      +--> native classifier veya opsiyonel Jev
                     |
                     v
          Codex custom subagent seçimi
          Luna / Terra / Sol / Astra
                     |
                     v
             uygulama + araç kullanımı
                     |
                     v
        yerel verifier: test/lint/typecheck/diff/risk
                     |
            geçer ----+---- kalır/riskli
              |                    |
              v                    v
          sonucu sun       Sol/Astra review/fix
```

Bu tasarım yalnız pre-routing yapmaz. Southbridge entity-resolution çalışmasındaki asıl güçlü fikir olan `ucuz işçi + deterministik kapı + seyrek güçlü inceleme` yapısını yazılım mühendisliğine taşır.

## Codex entegrasyonu

Codex, proje içindeki `.codex/agents/*.toml` dosyalarından farklı model ve reasoning ayarlarına sahip özel subagent'lar yükleyebilir. Bir repo skill'i veya `AGENTS.md` talimatı gerekli durumda bu subagent'lara delegasyonu tetikleyebilir.

Planlanan ajanlar:

- `router_explorer`: Salt okunur keşif; Terra medium.
- `luna_worker`: Dar, mekanik, düşük riskli uygulama; Luna medium.
- `terra_worker`: Gündelik çok dosyalı uygulama; Terra high.
- `sol_worker`: Karmaşık hata ayıklama/refactor; Sol high veya xhigh.
- `astra_worker`: Belirsiz ve uzun ufuklu işler; Astra high/max.
- `sol_reviewer`: Test, doğruluk ve regresyon incelemesi; Sol high.
- `astra_reviewer`: Güvenlik, migration ve yüksek etkili değişiklikler; Astra high.

Repo skill'i şu sözleşmeyi uygulamalıdır:

1. Görevi sınıflandır.
2. Gerekmedikçe birden çok yazan ajan başlatma.
3. Seçilen tek worker'ın işi tamamlamasını bekle.
4. Yerel verifier'ı çalıştır.
5. Yalnız açık bir escalation sinyali varsa reviewer/fixer başlat.
6. Kullanıcıya seçilen rota, doğrulama ve escalation nedenini raporla.

## Routing kararı

Router serbest metin yerine sürümlü JSON üretmelidir:

```json
{
  "schema_version": "1",
  "task_kind": "bugfix",
  "risk": "medium",
  "scope": "multi_file",
  "primary_agent": "terra_worker",
  "review_agent": "sol_reviewer",
  "review_mode": "on_failed_verifier",
  "confidence": 0.78,
  "reason_codes": ["existing_tests", "bounded_scope", "multi_file"],
  "redactions_applied": ["paths", "secrets"]
}
```

Olasılık tek başına karar vermemelidir. Aşağıdaki durumlar deterministik hard guard olmalıdır:

- auth, cryptography, payment, permissions, sandbox veya secret değişikliği;
- veri silme, schema migration veya geri dönüşü zor işlem;
- testlerin çalışmadığı/bulunmadığı durum;
- büyük public API değişikliği;
- belirsiz kabul kriterleri;
- worker'ın test/lint/typecheck sonucunu tamamlayamaması;
- beklenenden büyük diff veya hassas path değişikliği.

## Sol-high ana oturum konusu

Kullanıcı ana görevi Sol high oturumuna verebilir ve Sol yalnız koordinatör olabilir. Bu kalite öncelikli bir moddur fakat en ekonomik mod değildir: Sol routing kararında da token tüketir, ardından subagent ayrıca token kullanır.

İki profil sunulmalıdır:

- `quality-first`: Ana ajan Sol high; Astra'ya yükseltir veya daha ucuz worker'a delegasyon yapar; riskli sonuçları inceler.
- `efficiency-first`: Ana ajan Terra medium; kolay işi Luna'ya, zor işi Sol/Astra'ya yükseltir.

Benchmark her iki profilin toplam token ve süre maliyetini ayrı raporlamalıdır.

## Otomatik benchmark entegrasyonu

Codex CLI `codex exec --json` her koşu için JSONL olay akışı ve `turn.completed` kullanım alanları üretir. Benchmark runner kayıtlı Codex oturum kimliğini kullanarak hedef modeli `--model` ile seçebilir; ayrı bir API anahtarı zorunlu değildir. Ölçülecek değerler:

- input, cached input, output ve reasoning token;
- duvar saati, time-to-first-event ve test süresi;
- çözüm oranı / pass@1;
- yeni testlerin geçmesi ve regresyon testleri;
- model ve reasoning seçimi;
- escalation/review oranı;
- çözülen görev başına token ve dakika;
- API liste fiyatıyla yalnız karşılaştırma amaçlı `API-equivalent USD` (gerçek Codex faturası diye sunulmaz).

Karşılaştırma kolları:

- always Luna;
- always Terra;
- always Sol;
- always Astra;
- deterministik kural router'ı;
- Codex-native router;
- opsiyonel Jev pre-router;
- Jev/native worker + verifier + seyrek Sol/Astra review;
- karşı-olgusal oracle.

## Benchmarkların rolleri

### LiveCodeBench

Hızlı ve görece ucuz ilk filtre. İzole kod üretimi, execution, self-repair ve test-output prediction ölçer. Gerçek repository ajanı ölçümü değildir.

### SWE-bench Verified

Container ve patch değerlendirme adaptörümüzün uyumluluk testi için kullanılır. 500 gerçek GitHub issue'su vardır; ancak güncel frontier modeller için kontaminasyon ve kusurlu test riski nedeniyle ana ürün iddiası yapılmamalıdır.

### SWE-bench Pro

Uzun ufuklu repository işleri için değerlidir; fakat güncel denetimler public split'in yaklaşık yüzde 30'unda problem raporlamıştır. Ham Pro skoru deneysel olarak etiketlenmeli; doğrulanmış/audit edilmiş alt kümeler tercih edilmelidir.

### Terminal-Bench

Codex benzeri terminal kullanan ajanı en iyi ölçen public adaptör olmalıdır. Sürüm sabitlenmeli; görev, harness ve container hash'leri manifestte tutulmalıdır.

### Rolling private/public-safe set

Ana routing iddiası için taze bir set gereklidir:

- model cutoff'larından sonra oluşturulan gerçek veya kontrollü mutation görevleri;
- gizli testler;
- agent workspace'inden kaldırılmış future git history ve çözüm artefaktları;
- ağ kapalı veya allowlist;
- görevler donduktan sonra router eşiğinin değiştirilmemesi;
- dev/test zaman ayrımı;
- daha sonra yalnız lisansı uygun ve sızıntı riski düşük görevlerin yayınlanması.

## Deney aşamaları

### Aşama 1 — tesisat

- 12–20 küçük yerel görev.
- Her modelde tam matris.
- Route log, token, süre, patch ve verifier kayıtlarının doğrulanması.

### Aşama 2 — kalibrasyon

- 50 LiveCodeBench + 25 Terminal-Bench/SWE görevi.
- Hard guard ve eşiklerin yalnız dev setinde dondurulması.
- Router'ın “zor görev” precision/recall ölçümü.

### Aşama 3 — kilitli test

- En az 100 repository/terminal görevi.
- Always-model baselines ve matched-random karşılaştırması.
- Eşleştirilmiş bootstrap ve McNemar analizi.

### Aşama 4 — gerçek kullanım

- Kullanıcının gerçek Codex görevlerinden açık rızayla ve secret temizlenerek route metadata'sı.
- Çözüldü/çözülmedi, yeniden açılma, insan müdahalesi ve review bulguları.
- Public benchmarktan ayrı rapor.

## Başarı kriteri

Tek başına “ucuzladı” başarı değildir. Önerilen ilk ürün hedefi:

- always-Sol'a göre kilitli testte en fazla 3 yüzde puan resolved-rate kaybı;
- en az yüzde 40 token veya API-equivalent maliyet azalması;
- çözülen görev başına maliyette en az 1,5 kat iyileşme;
- kritik güvenlik/veri kaybı regresyonu sıfır;
- p50 duvar saatinde en fazla yüzde 10 kötüleşme;
- matched-random router'a karşı pozitif eşleştirilmiş güven aralığı.

Bu eşikler başlangıç hipotezidir; gerçek kullanıcı hata maliyetine göre değiştirilip testten önce dondurulmalıdır.

## Önerilen repo yapısı

```text
.codex/
  config.toml
  agents/
    router-explorer.toml
    luna-worker.toml
    terra-worker.toml
    sol-worker.toml
    astra-worker.toml
    sol-reviewer.toml
    astra-reviewer.toml
.agents/skills/codex-model-router/
  SKILL.md
  references/routing-policy.md
src/jev_router/
  codex/
    decision.py
    verifier.py
    receipts.py
  policies/
    native.py
    jev.py
  benchmarks/
    livecodebench.py
    swebench.py
    terminalbench.py
schemas/
  route-decision.schema.json
  run-receipt.schema.json
docs/
  ARCHITECTURE.md
  PRIVACY.md
  BENCHMARK_CARD.md
```

Benchmark veri kümeleri repoya kopyalanmamalı; adaptörler upstream revision/hash sabitleyerek indirmeli veya kullanıcının mevcut kurulumunu kullanmalıdır.

## Açık kaynak sürüm sırası

1. `v0.1`: Codex-native agent dosyaları, skill, deterministik policy ve dry-run.
2. `v0.2`: Tek worker çalıştırma, yerel verifier ve selective review.
3. `v0.3`: `codex exec --json` receipt toplayıcı ve fixture benchmark.
4. `v0.4`: LiveCodeBench ve Terminal-Bench adaptörleri.
5. `v0.5`: SWE adaptörleri, rolling set ve istatistiksel raporlar.
6. `v1.0`: Dondurulmuş protokol, yeniden üretilebilir sonuç, gizlilik dokümanı ve CI.

## Sonuç

En doğru ürün “Jev her görevi tek başına route etsin” değildir. En doğru ürün, Codex-native custom agent'ları çalıştıran; Jev'yi opsiyonel, dar ve veri-minimum bir classifier olarak kullanan; yerel testleri hakem yapan ve yalnız belirsiz/başarısız işleri güçlü modele yükselten bir software-engineering cascade'dir.
