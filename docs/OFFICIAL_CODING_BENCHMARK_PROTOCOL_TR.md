# Resmî kodlama benchmark protokolü

## Amaç

Bu protokol router ve judge sistemini kendi yazdığımız sorularla değil, sürümü sabitlenmiş üçüncü taraf benchmark'ların resmî değerlendiricileriyle ölçer. Ana iddia yalnızca “Jev ucuz modeli daha sık seçti” değildir. Bir routing politikası ancak şu üç koşulu birlikte karşılarsa yararlıdır:

1. Resmî gizli/ayrık testlerde çözüm oranını kabul edilebilir düzeyde tutar.
2. Aynı görevde gereksiz pahalı model kullanımını azaltır.
3. Hatalı patch'leri judge ile yakalarken doğru patch'leri gereksiz yere reddetmez.

## Sekiz iş paketi ve başarı kapısı

| # | İş paketi | Ölçüm | Başarı kapısı |
|---|---|---|---|
| 1 | Resmî veri kaynağı | Dataset ve harness revision'ı | Revision, split, seed ve seçim hash'i kayıtlı |
| 2 | Sızıntı önleme | Worker'a verilen alanlar | Gold patch, test patch, FAIL_TO_PASS ve cevap anahtarı verilmez |
| 3 | Dört sabit baz çizgisi | Luna, Terra, Sol, Astra pass@1 | Aynı instance ve aynı base commit üzerinde resmî evaluator sonucu |
| 4 | Router-only | Seçilen tier, pass@1, süre | Sabit baz çizgilerindeki en ucuz başarılı tier ile karşılaştırma |
| 5 | Router + judge | Accept/revise/escalate/block ve son pass@1 | Yanlış kabul ve gereksiz escalation ayrı raporlanır |
| 6 | Resmî doğrulama | resolved/unresolved/infra error | Gold smoke geçmeden model skoru yayımlanmaz |
| 7 | Maliyet ve hız | Jev USD, Codex token kullanımı, wall time | API maliyeti ile abonelik kullanımını birbirine karıştırmaz |
| 8 | Tekrarlanabilirlik ve CI | Test, manifest, atomik commit | Tüm birim testleri ve GitHub Actions yeşil |

## Benchmark ailesi

- **SWE-bench Verified (birincil):** 500 insan tarafından doğrulanmış repository issue. Resmî Docker evaluator fail-to-pass ve pass-to-pass testlerini çalıştırır.
- **Terminal-Bench 2 (ikincil):** Terminalde çalışan agent görevleri; resmî Harbor testleri kullanılır. Router entegrasyonu SWE-bench hattından sonra gelir.
- **LiveCodeBench (hızlı filtre):** İzole kod üretimi, çalıştırma, çıktı tahmini ve self-repair görevleri. Repository agent kalitesinin yerine geçmez.
- **SWE-bench Pro public (ileri seviye):** Daha uzun ve zor repository görevleri. Birincil sistem kararlı olmadan ana seçim metriği yapılmaz.

Tam kimlikler ve commit'ler `benchmarks/registry.json` dosyasındadır. Veri satırları repoya kopyalanmaz; resmî kaynak revision'ından deterministik plan üretilir.

## Körlük ve veri akışı

Worker yalnız şu dört alanı alır: `instance_id`, repository slug, `base_commit` ve `problem_statement`. Plan yükleyici diğer bütün dataset alanlarını düşürür. Her kol ayrı checkout'ta tam `base_commit` üzerinde başlar. Worker patch'i üretince `git diff --binary HEAD` alınır ve resmî SWE-bench tahmin biçimine çevrilir.

Resmî evaluator daha sonra patch'i bağımsız container'a uygular. Agent'ın yazdığı testler bağımsız kanıt sayılmaz. Judge görev metnini, diff'i, ilgili kodu ve “agent-authored tests are not independent” işaretini görür; son doğruluk etiketi yine yalnız resmî evaluator'dan gelir.

## Deney kolları

- `always-luna`, `always-terra`, `always-sol`, `always-astra`: counterfactual baz çizgileri.
- `router-only`: Jev yalnız en düşük yeterli tier'i seçer; seçilen Codex rolü bir kez çalışır.
- `router-judge`: Aynı route sonrası Jev diff'i inceler; deterministik politika accept, revise, escalate veya block uygular.
- `balanced-trajectory`: Task-router çağrısı yapmadan Luna ile başlar; gerçek diff/progress kanıtı ve Jev review sonucuna göre yalnız gerektiğinde Sol/Astra'ya yükselir.

Doğru route etiketi, dört sabit kolun aynı görevdeki resmî sonuçlarından türetilir. En ucuz başarılı sabit tier “observed oracle”dır. Router daha düşük ve yetersiz tier seçerse `under_routed`; daha pahalı tier seçerse `over_routed`; aynısını seçerse `exact` olur. Dört sabit sonuç tamamlanmamışsa routing accuracy hesaplanmaz.

## Metrikler

- Resmî pass@1 ve eşleştirilmiş kalite farkı
- Exact/under/over routing oranı ve oracle coverage
- Judge unsafe false accept, false revise/escalate ve escalation recovery
- Ortalama/p50/p95 wall time; routing ve worker süreleri ayrı
- Jev'in gerçek provider USD maliyeti
- Codex input/cached/output tokenları; Codex yerel abonelik akışına hayalî API USD fiyatı yazılmaz
- Boş patch, dispatch hatası, evaluator hatası ve infra hatası

Infra/evaluator hataları başarısız çözüm gibi gösterilmez; pass-rate paydasından ayrılır ve ayrıca raporlanır.

## Çalıştırma sırası

```bash
# 1. Sabitlenmiş 20 dev + 100 test planı
uv run jev-router benchmark-plan --suite swebench-verified --dev 20 --test 100

# 2. Kuru çalışma; dış çağrı veya clone yok
uv run jev-router swebench-generate --arm always-luna --limit 1

# 3. Aynı dev örneklerinde altı kolu çalıştır
uv run jev-router swebench-generate --arm always-luna --limit 20 --execute
uv run jev-router swebench-generate --arm always-terra --limit 20 --execute
uv run jev-router swebench-generate --arm always-sol --limit 20 --execute
uv run jev-router swebench-generate --arm always-astra --limit 20 --execute
uv run jev-router swebench-generate --arm router-only --limit 20 --execute
uv run jev-router swebench-generate --arm router-judge --limit 20 --execute
uv run jev-router swebench-generate --arm balanced-trajectory --limit 20 --execute

# 4. predictions.jsonl dosyalarının her birini resmî evaluator ile değerlendir
uvx --from swebench swebench eval verified -p PATH/predictions.jsonl \
  --run-id ARM -j 1 --task-repo ~/.cache/jev-router/swe-bench-tasks

# 5. Generation summary + resmî evaluator JSON'larını birleştir
uv run jev-router swebench-report \
  --generation always-luna=PATH/generation-summary.json \
  --evaluation always-luna=PATH/evaluator-report.json \
  --output results/swebench-analysis.json
```

Dev split, eşik ve politika ayarı içindir. Dondurulan politika yalnız bir kez test split'inde çalıştırılır. Test sonucuna bakarak eşik değiştirilirse yeni bir deney sürümü açılır; eski sonuç üzerine yazılmaz.

## İlk altyapı doğrulaması

20 Eylül 2026'da `sphinx-doc__sphinx-10323` gold patch'i Apple ARM üzerinde resmî görev deposundan yerel Docker imajı kurularak çalıştırıldı: 1/1 resolved, 0 evaluator error, 0 infrastructure failure. Registry'deki hazır x86 imajı ARM'de bulunmadığı için `swe-bench-tasks` commit'i `3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d` üzerinden yerel build zorunludur.

Bu tek gold smoke model başarısı değildir; yalnız ölçüm altyapısının doğru çalıştığını kanıtlar.
