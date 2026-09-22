# jev-llm-router-benchmark

Jev ile üretimden önce model rotası seçen ve üretimden sonra kod değişikliğini `accept`, `revise`, `escalate` veya `block` olarak değerlendiren bağımsız açık kaynak proje. Router ve judge karar verir; uygulamayı yapan model değildir.

Bu repo bir RAG projesi değildir ve başka ErenAILab projelerinden bağımsızdır. Ana sonuç ilkesi: “ucuzladı” tek başına başarı değildir; kalite farkı, eşleştirilmiş belirsizlik, hata/fallback oranı ve mutlak USD ile birlikte raporlanır.

Repo 40 görevlik fixture pilotuna ek olarak OpenRouter üzerinden `typesafe/jev-1.13`, `openai/gpt-5.6-luna` ve `openai/gpt-5.6-sol` ile kontrollü canlı akışı destekler. Worker üretimi OpenRouter API'den yapılabilir; yerel Codex kimliği zorunlu değildir.

Ayrıca dört resmî İngilizce benchmark ailesinden 200 dev + 1.000 kilitli test örneği hazırlayan yeniden üretilebilir veri betiği ve ayrıntılı canlı analiz akışı vardır. Üçüncü taraf sorular repoya commitlenmez; kaynak revision'ları, örnekleme tohumu ve veri hash'i kaydedilir.

## V0.01 (`v0.0.1`) benchmark referansı

V0.01, mevcut **quality-first** politikanın dondurulmuş referansıdır. Bu politika
görevi çözmeden önce Jev'e yalnız görev metnini gösterir; Jev Luna veya Sol'u seçer,
seçilen model çözümü üretir. Eşik ilk 100 LiveCodeBench sorusunda seçilmiş ve sonraki
100 sorunun sonucu görülmeden önce `0,08` olarak dondurulmuştur.

| Bölme | Görev | Luna | Always-Sol | V0.01 router | Sol çağrı oranı | Router maliyeti | Always-Sol maliyeti | Tasarruf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dev / kalibrasyon | 100 | 92 (%92) | 99 (%99) | 99 (%99) | %66 | $0,348893 | $0,405908 | %14,05 |
| Kilitli test | 100 | 84 (%84) | 94 (%94) | 94 (%94) | %68 | $0,375998 | $0,426348 | %11,81 |
| Birleşik | 200 | 176 (%88) | 193 (%96,5) | 193 (%96,5) | %67 | $0,724891 | $0,832256 | %12,90 |

| Ölçüm | V0.01 sonucu | Basit yorum |
|---|---:|---|
| Router–Sol kalite farkı | `0,0` yüzde puan | Bu 200 soruda router ile Sol aynı 193 soruyu geçti ve aynı 7 soruda kaldı. |
| Router başarı oranı için %95 Wilson GA | `%92,95–%98,29` | `%96,5` tahmininin örneklem belirsizliğidir; başka görev ailelerinde eşdeğerlik garantisi değildir. |
| Sol'dan kaçınılan görev | `66/200` (%33) | Her üç görevin yaklaşık birinde ucuz Luna kullanıldı. |
| Ölçülen politika tasarrufu | `$0,107365` (%12,90) | Kalite kaybı gözlenmedi, fakat hedeflenen `%30–40` tasarrufa henüz ulaşılamadı. |
| Held-out ortalama uçtan uca süre | Router `8,40 sn`; Sol `7,60 sn` | Router yaklaşık `%10,6` daha yavaştı; hız kapısı geçilmedi. |
| Toplam deney harcaması | bilinen `$1,032690`; muhafazakâr üst sınır `$1,134466` | Paired worker, calibration, judge ve smoke çağrılarının tamamı `$5` kampanya tavanının altında kaldı. |
| Code-judge held-out doğruluğu | `%71,4` | Sentetik 28 vakada hatalı/riskli değişiklikleri yakalama recall'u `%100`, geçerli değişikliği kabul recall'u yalnız `%28,6`; güvenli ama fazla muhafazakâr. |

Sonuç: **V0.01 kalite ve maliyet kapısını bu LiveCodeBench örneğinde geçti; hız,
`%30–40` tasarruf ve repository-agent genellemesi kapılarını geçmedi.** Bu nedenle
V0.01 silinmeyecek veya sonradan daha iyi görünecek şekilde yeniden ayarlanmayacak;
yeni `balanced` politika aynı veya daha iyi kaliteyi daha az Sol kullanımıyla göstermeye
çalışacaktır. Tam deney kartı ve ham özetler
[`results/openrouter-router-v2-livecodebench-200-20260922/`](results/openrouter-router-v2-livecodebench-200-20260922/)
altındadır. Luna'nın önce çalışıp gerçek diff/test/hata kanıtına göre seçici biçimde
Sol'a yükseltildiği sonraki sürümün durum makinesi, hız/maliyet sınırları ve kabul
kapıları [balanced trajectory planında](docs/BALANCED_TRAJECTORY_PLAN_TR.md) tanımlıdır.

## Router + judge mimarisi

```text
görev ──> hard guard + Jev router ──> uygun worker rolü
                                         │
                                  kod değişikliği
                                         │
                       yerel Git diff + ilgili kod + kanıt
                                         │
                           Jev atomik judge sinyalleri
                                         │
                           deterministik risk politikası
                              │       │         │       │
                           accept   revise   escalate  block
```

Jev yanıt veya kod yazmaz. Dar olasılık sinyalleri üretir; maliyet hesabı, eşikler, risk guard'ları, retry ve fail-safe davranış deterministik koddadır. Agent'ın kendi yazdığı testler bağımsız başarı kanıtı sayılmaz; judge doğrudan görev, kabul kriterleri, diff, ilgili kod ve mevcut kanıtları görür.

`pipeline --profile balanced` deneysel Luna-first akıştır. Açık kritik alan yoksa Luna
bir tur çalışır; sistem değişen/yeni dosyaları, diff parmak izini, eklenen/silinen
satırları, process sonucunu ve verifier stdout/stderr'ini kaydeder. Dispatch hatası,
boş diff veya kalan verifier varsa Jev çağrısını atlayıp kanıtı Sol düzeltme turuna
verir. Makine kapıları geçtiğinde Jev semantik yeterliliği denetler. `.env` ve credential
path'leri progress receipt'ine alınmaz; yalnız dışlanan hassas path sayısı ve fail-closed
risk flag'i tutulur.

İlk dış-API kullanmayan fixture smoke'unda bütün repository testleri geçti; Luna
verifier failure'ı Jev çağrılmadan Sol'a yükseltildi ve destructive değişiklik
bloklandı. Bu bir model kalite sonucu değildir. Ayrıntı:
[`results/balanced-trajectory-fixture-20260922/REPORT_TR.md`](results/balanced-trajectory-fixture-20260922/REPORT_TR.md).

İlk gerçek Codex + Jev smoke'unda Luna tek turda doğru değişikliği yaptı, 2/2 bağımsız
test geçti, Jev `accept` verdi ve Sol çağrılmadı. Toplam süre `20,72 sn`, Jev maliyeti
`$0,00006279` oldu. İlk koşuda generated `__pycache__` gürültüsünün gereksiz escalation
ürettiği görülüp evidence filtresi düzeltildi. Bu hâlâ `n=1` entegrasyon smoke'udur;
ayrıntı ve ilk başarısız koşu:
[`results/balanced-trajectory-live-smoke-20260922/REPORT_TR.md`](results/balanced-trajectory-live-smoke-20260922/REPORT_TR.md).

İlk resmî SWE-bench Verified test katmanında balanced final patch'ler `2/2` resolved
oldu; fakat iki görev de Luna'dan Sol'a gereksiz biçimde yükseltildi ve otomatik accept
`0/2` kaldı. Kaydedilmiş ilk Luna patch'lerinin ikisi de ayrıca resmî evaluator'da
geçti. Sonuç: worker kalitesi bu küçük örnekte yeterli, Jev kabul kalibrasyonu ise
ekonomik hedefi karşılamıyor. Tam tablo ve sınırlar:
[`results/balanced-trajectory-swebench-smoke-20260922/REPORT_TR.md`](results/balanced-trajectory-swebench-smoke-20260922/REPORT_TR.md).

`route` yalnız görev metnini gönderir. `review` ve `control`, judge kararı için temizlenmiş ve boyutu sınırlanmış diff/ilgili kodu Jev sağlayıcısına gönderir; `.env`, credential/key dosyaları dışlanır ve bilinen secret biçimleri redakte edilir. Dolayısıyla judge modu “yalnız karar dışarı gider” değildir. Hassas repository'lerde fixture/native politika kullanılmalı veya bu dış aktarım açıkça kabul edilmelidir.

`codex-route`, seçilen Luna/Sol rolünü yerel `codex exec` sürecine mevcut Codex kimliğiyle teslim edebilir; Terra ve Astra forced baseline olarak da kullanılabilir. Güvenlik için varsayılan davranış dry-run'dır ve gerçek teslim `--execute` ister. `control` ise henüz worker çalıştırmaz; pre-route ve post-change judge kararını tek receipt'te birleştirir.

## Hızlı başlangıç

Global Python ortamını değiştirmez:

```bash
uv sync --extra dev
uv run pytest
uv run jev-router environment
uv run jev-router calibrate
uv run jev-router smoke
uv run jev-router benchmark --mode fixture
uv run jev-router report
uv run jev-router judge-benchmark --mode fixture --split all

# Resmî kodlama planı ve güvenli kuru çalışma
uv run jev-router benchmark-catalog
uv run jev-router benchmark-plan --suite swebench-verified --dev 20 --test 100
uv run jev-router swebench-generate --arm always-luna --limit 1

# Diğer resmî harness'lar: veri dizinleri upstream revision'lara pinlenmelidir
uv run jev-router livecodebench-plan --dataset-dir /path/to/livecodebench-jsonl
uv run jev-router livecodebench-run --plan results/benchmark-plans/livecodebench-release-v6.json \
  --repo . --offset 0 --limit 20 --output results/livecodebench-segment
uv run jev-router livecodebench-openrouter-run --limit 100 --role luna \
  --max-usd 0.60 --output results/livecodebench-openrouter-luna
uv run jev-router livecodebench-openrouter-cascade-run --limit 100 \
  --threshold 0.21 --difficulty-gates --max-usd 2.50 \
  --output results/livecodebench-openrouter-cascade
uv run jev-router terminalbench-plan --dataset-root /path/to/terminal-bench-2
uv run jev-router terminalbench-run --plan results/benchmark-plans/terminal-bench-2.json \
  --dataset-root /path/to/terminal-bench-2 --route-only
uv run jev-router swebench-pro-generate --plan /path/to/swebench-pro-plan.json \
  --arm router-only --limit 1 --execute
```

Üretilen ana rapor: `results/fixture-test/REPORT_TR.md`.

## CLI

```bash
# Bir isteği sadece route et; model yanıtı üretmez
uv run jev-router route --mode rule --prompt "Bu mesajı üç sınıftan birine ayır"

# Jev ile canlı route (OPENROUTER_API_KEY gerekir)
uv run jev-router route --mode live-jev --threshold 0.58 --prompt "..."

# Bir yerel Git değişikliğini Jev ile incele
uv run jev-router review --repo . --base HEAD~1 --head HEAD \
  --task "Cache anahtarındaki tenant izolasyonunu düzelt" \
  --criterion "Tenant'lar birbirinin verisini okuyamaz" --max-usd 0.01

# Pre-route ve post-change judge kararını tek kontrol çıktısında birleştir
uv run jev-router control --repo . --base HEAD~1 --head HEAD \
  --task "İstenen değişikliği uygula" --criterion "Testler ve kabul kriterleri sağlanır"

# Router kararını mevcut Codex oturumu üzerinden Luna veya Sol'e gerçekten gönder
# --execute verilmezse güvenli dry-run planı gösterilir
uv run jev-router codex-route --mode live-jev --repo . --task "..."
uv run jev-router codex-route --mode live-jev --repo . --execute --task "..."

# Aynı görevde doğrudan model baseline'ı
uv run jev-router codex-route --role luna --sandbox read-only --execute --task "..."
uv run jev-router codex-route --role sol --sandbox read-only --execute --task "..."

# Deneysel Luna-first trajectory akışı; --execute olmadan yalnız planı gösterir
uv run jev-router pipeline --profile balanced --repo . \
  --task "İstenen değişikliği uygula" \
  --criterion "Kabul kriteri sağlanır" \
  --verify-json '["uv","run","pytest","-q"]'

# Gerçek worker + verifier + seçici Jev/Sol akışı
# Jev review için OPENROUTER_API_KEY gerekir; worker mevcut Codex kimliğini kullanır
uv run jev-router pipeline --profile balanced --execute --repo . \
  --task "İstenen değişikliği uygula" \
  --criterion "Kabul kriteri sağlanır" \
  --verify-json '["uv","run","pytest","-q"]' \
  --output results/balanced-run.json

# V0.01 davranışını koruyan task-router-first profil
uv run jev-router pipeline --profile quality-first --repo . --task "..."

# 40 sentetik vaka; canlı test yalnız dondurulmuş test split'inde
uv run jev-router judge-benchmark --mode fixture --split all \
  --output results/judge-fixture
uv run jev-router judge-benchmark --mode live --split test --max-usd 0.01 \
  --output results/judge-live-test

# Kayıtlı measurement'lardan API çağrısı yapmadan raporu yeniden üret
uv run jev-router judge-report --results results/judge-live-test

# Bir aday modeli doğrudan fixture üzerinde çalıştır
uv run jev-router run-model --task-id demo-003 --role cheap

# Dev kalibrasyonu, tam eğriyle
uv run jev-router calibrate

# Beş test görevlik smoke
uv run jev-router smoke

# Kilitli testte A–E fixture benchmarkı
uv run jev-router benchmark --mode fixture --output results/fixture-test

# Kontrollü canlı smoke: aynı OpenRouter anahtarıyla Jev + tam Luna/Sol matrisi
set -a; source ~/.config/openrouter.env; set +a
uv run jev-router estimate --data data/live_smoke_v1.jsonl --split test
uv run jev-router benchmark --data data/live_smoke_v1.jsonl --mode live \
  --threshold 0.58 --output results/openrouter-smoke-20260919

# Büyük İngilizce benchmark verisini hazırla (Global-MMLU, Belebele, GSM8K, ARC-Challenge)
uv sync --extra dev --extra data
uv run python scripts/build_public_benchmark.py

# Önce 200 dev, sonra dev'de dondurulan eşikle 1.000 test
uv run jev-router benchmark --data data/public_benchmark_en_v1.jsonl --mode live \
  --split dev --threshold 0.58 --max-usd 1.0 --output results/live-en-dev
uv run python scripts/analyze_live_results.py results/live-en-dev --dev-only
uv run jev-router benchmark --data data/public_benchmark_en_v1.jsonl --mode live \
  --split test --threshold 0.02 --max-usd 4.0 --output results/live-en-test
uv run python scripts/analyze_live_results.py results/live-en-test \
  --calibration-results results/live-en-dev

# Yerel demo
uv run jev-router demo --port 8765
```

`benchmark` threshold verilmezse yalnız dev split'inde kalibre eder, sonra test split'ini çalıştırır. Rastgele baseline, Jev'in güçlü model kullanım oranıyla ve sabit seed ile eşleştirilir.

## Doğrulanmış canlı smoke — 2026-09-19

10 sentetik TR/EN görevde OpenRouter üzerinden 20 hedef model ve 10 Jev çağrısı çalıştı. Hata/fallback olmadı; tüm çağrılarda provider usage/cost ve streaming TTFT alındı. Sol kalite 1.00, Luna 0.70, Jev yolu 0.90 oldu. Jev yolu Sol'a göre %36.1 daha düşük politika maliyeti gösterdi, fakat 10 yüzde puanı kalite kaybıyla önceden tanımlı 2 puan hedefini karşılamadı. Gerçek benzersiz çağrı harcaması $0.009566 idi.

Tam Türkçe rapor ve ham artefaktlar: [`results/openrouter-smoke-20260919/REPORT_TR.md`](results/openrouter-smoke-20260919/REPORT_TR.md).

## 1.000 soruluk İngilizce canlı benchmark — 2026-09-19

200 ayrı dev sorusunda eşik `0.02` olarak seçilip testten önce donduruldu. 1.000 kilitli testte Sol %94.2, Luna %83.9 ve Jev yolu %89.7 doğruluk verdi. Jev %19.2 Sol kullandı ve Sol politikasına göre %62.3 maliyet tasarrufu gösterdi; ancak 4.5 yüzde puan kalite kaybıyla önceden tanımlı 2 puan hedefini geçemedi. Jev, aynı Sol kullanım oranındaki rastgele router'dan 3.9 puan daha iyi olsa da p50 uçtan uca gecikmesi routing ek yükü nedeniyle Sol'dan daha yüksekti. Kalibrasyon + test için 3.600 çağrının gerçek ledger harcaması `$0.458076` oldu.

Ayrıntılı rapor: [`results/openrouter-en-test-1000-20260919/DETAILED_REPORT_TR.md`](results/openrouter-en-test-1000-20260919/DETAILED_REPORT_TR.md).

## İlk Jev code-judge benchmarkı — 2026-09-20

Eşikler yalnız 12 vakalık dev split'inde ayarlandı ve 28 vakalık sentetik testten önce donduruldu. Held-out testte dört sınıflı karar doğruluğu `%71.4` oldu. Hatalı/riskli 21 vakanın hiçbiri yanlışlıkla `accept` edilmedi (`unsafe detection recall %100`, `accept precision %100`); yedi geçerli değişikliğin ise yalnız ikisi kabul edildi (`valid accept recall %28.6`). Yani ilk sürüm güvenli tarafta fakat belirgin biçimde fazla muhafazakâr. Toplam canlı test maliyeti `$0.001196`, vaka başı `$0.000043`; ortalama gecikme `513 ms`, p95 `648 ms` oldu.

Bu sonuç üretim doğruluğu veya SWE-bench başarısı değildir. Sentetik set politika ve tesisatı doğrular. Ham held-out ölçümler [`results/judge-openrouter-test-20260920/`](results/judge-openrouter-test-20260920/) altında; deney sözleşmesi ve dürüst yorum [docs/JUDGE_PROTOCOL_TR.md](docs/JUDGE_PROTOCOL_TR.md) içindedir.

Codex-native dispatch de gerçek Luna ve Sol oturumlarıyla smoke-test edildi. Aynı kolay salt-okunur görevde ikisi de doğru cevap verdi; Luna `12.65 s`, Sol `15.87 s` sürdü. Bu çağrılar OpenRouter'a gitmedi ve API USD maliyeti üretmedi; mevcut Codex oturumu/kullanım hakkını kullandı. Ayrıntı: [`results/codex-native-smoke-20260920/REPORT_TR.md`](results/codex-native-smoke-20260920/REPORT_TR.md).

Repository düzeyi kod benchmark hattı artık SWE-bench Verified görevlerini dört sabit Codex tier'i, router-only ve router+judge kollarında çalıştırır. Worker'a gold/test patch veya gizli test kimliği verilmez; skor yalnız resmî evaluator çıktısından alınır. Sekiz iş paketi, başarı kapıları ve tam komutlar [docs/OFFICIAL_CODING_BENCHMARK_PROTOCOL_TR.md](docs/OFFICIAL_CODING_BENCHMARK_PROTOCOL_TR.md) içindedir.

İlk resmî iki-görev smoke matrisinde Luna 0/2, Terra 2/2, Sol 1/2, Astra 2/2, router-only 1/2 ve router+judge 2/2 sonuç verdi. Jev seçimleri bir exact ve bir over-route üretti; under-route yoktu. Judge her iki geçen sonucu da gereksiz biçimde insan incelemesine bıraktı. Bu bir ürün başarı oranı değil, `n=2` tesisat/behavior smoke'udur. Ayrıntılı ve sınırlamaları açık rapor: [`results/swebench-official-smoke-20260920/REPORT_TR.md`](results/swebench-official-smoke-20260920/REPORT_TR.md).

## 2.375 görevlik resmî routing kampanyası — 2026-09-20

LiveCodeBench `release_v6` (1.055), SWE-bench Verified (500), SWE-bench Pro public
(731) ve Terminal-Bench 2 (89) setlerinin tamamında Jev kararı alındı. Toplam maliyet
`$0.123703`; dağılım Luna 848, Terra 797, Sol 568 ve Astra 162 oldu. Provider
fallback'i yoktu; ortalama karar süresi `480,54 ms`, p95 `676,02 ms` idi.

Bu sayı çözüm başarısı değildir. Yönlendirme kapsamasını gösterir. Aynı 1.055
LiveCodeBench sorusunun iki koşusunda nihai tier anlaşması yalnız `%88,15` oldu;
router sınır örneklerinde tam kararlı değildir. Ayrıca iki kritik-keyword false positive'i
bulunup düzeltildi. Ayrıntılı rapor:
[`results/official-routing-2375-20260920/REPORT_TR.md`](results/official-routing-2375-20260920/REPORT_TR.md).

Üç ayrı harness'taki ilk gerçek uçtan uca denemeler başarılı oldu: LiveCodeBench'te
Luna 5/5 gizli testi, Terminal-Bench 2'de Sol `1.0` reward'u ve SWE-bench Pro'da
Sol resmî resolved kapısını geçti. Bunlar genel başarı oranı değil, harness
entegrasyonu kanıtlarıdır: [LiveCodeBench](results/livecodebench-official-smoke-20260920/REPORT_TR.md),
[Terminal-Bench 2](results/terminalbench-official-smoke-20260920/REPORT_TR.md),
[SWE-bench Pro](results/swebench-pro-official-smoke-20260920/REPORT_TR.md).

LiveCodeBench `release_v6` setinin **1.055 görevinin tamamı** daha sonra gerçek
Jev→yerel Codex zincirinde çalıştırıldı ve resmî gizli testlerle puanlandı: 913/1.055,
`%86,54 pass@1` (`%95` GA `%84,35–%88,47`). Aynı ilk 100 görevde router ve
always-Luna `%94`, always-Sol `%98` verdi; bu nedenle altyapı başarılı olsa da mevcut
routing politikasının kalite/hız üstünlüğü henüz kanıtlanmış değildir. Tam, eleştirel
yorum ve maliyet hesabı [1.055 görev raporundadır](results/livecodebench-official-1055-20260920/REPORT_TR.md).

## OpenRouter Router v2 — 2026-09-22

İlk 100 görevde kalibre edilip ikinci 100 görevden önce dondurulan Jev eşiğiyle,
router ve always-Sol aynı 193/200 (`%96,5`) soruyu geçti. Router Sol'u görevlerin
`%67`'sinde kullandı; paired politika maliyeti `$0,724891`, always-Sol maliyeti
`$0,832256` oldu. Böylece bu örnekte task-level kalite kaybı gözlenmeden `%12,90`
maliyet tasarrufu elde edildi. Held-out 100'de sonuç router 94, Sol 94, Luna 84'tür.

Hız iyileşmedi: routing ek yüküyle held-out ortalama süre yaklaşık `8,40 s`, Sol
worker ortalaması `7,60 s` oldu. Sonuç yalnız izole LiveCodeBench problemleri içindir;
repository ajan görevlerine genellenmez. Tam yöntem, harcama üst sınırı ve başarısız
denemeler: [`results/openrouter-router-v2-livecodebench-200-20260922/REPORT_TR.md`](results/openrouter-router-v2-livecodebench-200-20260922/REPORT_TR.md).

## Anahtar ve gizlilik

`.env.example` yalnız değişken adını gösterir. Uygulama `OPENROUTER_API_KEY` değerini yalnız process environment'tan okur; `.env` dosyasını kendi başına yüklemez, değeri loglamaz. `environment` komutu yalnız boolean var/yok sonucu verir. Yerel `~/.config/openrouter.env` kaynağı çağıran shell tarafından yüklenebilir.

## Model ve fiyat kayıtları

- Router: sabit `typesafe/jev-1.13`, 32k context, $0.042 / 1M input token.
- Ucuz aday: `openai/gpt-5.6-luna`, 1.05M context, $0.20 / $0.02 cached / $1.20 output per 1M.
- Güçlü aday: `openai/gpt-5.6-sol`, 1.05M context, $2.00 / $0.20 cached / $10.00 output per 1M.

Kontrol tarihi 2026-09-19'dur. Kimlikler ve fiyatlar authenticated OpenRouter model/endpoints API'sinden doğrulanmıştır. Canlı yanıtta `usage.cost` varsa doğrudan saklanır; yoksa katalog fiyatı ve provider token usage ile hesaplanır. Kaynak/sözleşme ayrıntıları [docs/RESEARCH.md](docs/RESEARCH.md), deney tasarımı [docs/PROTOCOL_TR.md](docs/PROTOCOL_TR.md) içindedir.

## Sonuç artefaktları

Her koşu dizini şunları üretir:

- `measurements.jsonl` ve `measurements.csv`: görev/baseline bazında model, kalite, usage, target/Jev/toplam maliyet, route ve latency.
- `summary.json`: kalite farkı ve eşleştirilmiş bootstrap GA, başarı, hata/fallback, model oranları, USD/istek, USD/1000, USD/başarı ve p50/p95.
- `manifest.json`: commit, tam model kimlikleri, veri hash'i, prompt/fiyat sürümleri, seed, retry, cache, concurrency ve streaming ayarları.
- `cost-quality.svg`, `latency-quality.svg`, `REPORT_TR.md`.

Trajectory pipeline receipt'i bunlara ek olarak tur başına `progress`, `evidence_gate`,
`review_called` ve `outcome` alanlarını yazar. Böylece Luna'nın ne yaptığı, Jev'nin
çağrılıp çağrılmadığı ve Sol'a hangi somut nedenle geçildiği sonradan replay edilebilir.

Canlı smoke'ta tam Luna/Sol matrisi her görev/model için yalnız bir kez üretilir ve Jev'in seçtiği yol aynı canlı yanıtı yeniden kullanır. Streaming açıktır; ilk boş olmayan metin parçasine kadar TTFT, tam hedef latency ve Jev latency ayrı saklanır.

Timeout gibi usage dönmeyen başarısız çağrılar ücretsiz varsayılmaz; tam çıktı bütçesine göre muhafazakâr tahmin edilir ve measurement hata alanında etiketlenir. Provider usage bulunan retry/fallback çağrıları doğrudan toplam maliyete eklenir.

## Veri ve lisans

`data/demo_pilot.jsonl` pipeline için özgün sentetik 40 görevdir; resmî benchmark değildir. Public benchmark içerikleri repoda yoktur. Adaylar, lisansları ve yeniden üretim politikası `data/SOURCES.json` ile araştırma belgesinde kayıtlıdır. Yeniden dağıtım izni net olmayan içerik commitlenmez.

Kod MIT lisanslıdır. İncelenen RouteLLM commit'i `0b64fdafe049e596a3f5657c219329f24af24198` ve lisansı Apache-2.0'dır; kodu bu repoya kopyalanmamıştır.

## Sınırlar

- 10 görevlik canlı smoke gerçek erişimi ve ölçüm tesisatını doğrular, fakat üretim kalitesi veya istatistiksel non-inferiority kanıtı değildir.
- 1.000 soruluk İngilizce sonuç Türkçe trafiğe veya açık uçlu üretim görevlerine doğrudan genellenemez; dört aile de otomatik ve nesnel puanlanan görevlerdir.
- 40 sentetik görev 2 yüzde puanlık non-inferiority iddiası için yetersizdir.
- Yerel kod evaluator'ü ayrı süreç/resource sınırları yanında macOS `sandbox-exec` veya Linux Bubblewrap ile ağı kapatır ve backend yoksa fail-closed durur. Güvenilmeyen public benchmark çıktıları için yine de tek-kullanımlık container/VM savunma katmanı önerilir.
- Açık uçlu kalite için kör, sıra dengeli judge + insan denetimi henüz canlı veri olmadığı için koşulmamıştır.
- Aynı makinede ağır RAG koşusu sürerken latency benchmarkı çalıştırılmamalıdır.

Kısa kayıt akışı: [docs/DEMO_VIDEO_TR.md](docs/DEMO_VIDEO_TR.md).
