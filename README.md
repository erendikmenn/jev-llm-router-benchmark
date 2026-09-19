# jev-llm-router-benchmark

Jev ile iki üretici LLM arasında **yanıt üretilmeden önce** seçim yapan, kalite–maliyet–gecikme değişimini aynı görevler üzerinde ölçen bağımsız açık kaynak proje.

Bu repo bir RAG projesi değildir ve başka ErenAILab projelerinden bağımsızdır. Ana sonuç ilkesi: “ucuzladı” tek başına başarı değildir; kalite farkı, eşleştirilmiş belirsizlik, hata/fallback oranı ve mutlak USD ile birlikte raporlanır.

Repo 40 görevlik fixture pilotuna ek olarak OpenRouter üzerinden `typesafe/jev-1.13`, `openai/gpt-5.6-luna` ve `openai/gpt-5.6-sol` ile kontrollü canlı smoke akışını destekler. Canlı smoke 8–12 görev, concurrency=1 ve kısa çıktı bütçesiyle sınırlandırılır.

## Mimari

```text
istek + izinli bağlam + kısıtlar
                │
        deterministik uygunluk
        (text / tools / context)
                │
   OpenRouter Jev 1.13 Choice
       görev türü + model uygunluğu
                │
     kodda threshold / fallback / bütçe
          ┌─────┴─────┐
 openai/gpt-5.6-luna   openai/gpt-5.6-sol
```

Jev yanıt yazmaz, fiyat toplamaz ve doğruluk yüzdesi iddia etmez. Maliyet hesabı, eligibility, retry, threshold ve fallback deterministik koddadır.

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
```

Üretilen ana rapor: `results/fixture-test/REPORT_TR.md`.

## CLI

```bash
# Bir isteği sadece route et; model yanıtı üretmez
uv run jev-router route --mode rule --prompt "Bu mesajı üç sınıftan birine ayır"

# Jev ile canlı route (OPENROUTER_API_KEY gerekir)
uv run jev-router route --mode live-jev --threshold 0.58 --prompt "..."

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

# Yerel demo
uv run jev-router demo --port 8765
```

`benchmark` threshold verilmezse yalnız dev split'inde kalibre eder, sonra test split'ini çalıştırır. Rastgele baseline, Jev'in güçlü model kullanım oranıyla ve sabit seed ile eşleştirilir.

## Doğrulanmış canlı smoke — 2026-09-19

10 sentetik TR/EN görevde OpenRouter üzerinden 20 hedef model ve 10 Jev çağrısı çalıştı. Hata/fallback olmadı; tüm çağrılarda provider usage/cost ve streaming TTFT alındı. Sol kalite 1.00, Luna 0.70, Jev yolu 0.90 oldu. Jev yolu Sol'a göre %36.1 daha düşük politika maliyeti gösterdi, fakat 10 yüzde puanı kalite kaybıyla önceden tanımlı 2 puan hedefini karşılamadı. Gerçek benzersiz çağrı harcaması $0.009566 idi.

Tam Türkçe rapor ve ham artefaktlar: [`results/openrouter-smoke-20260919/REPORT_TR.md`](results/openrouter-smoke-20260919/REPORT_TR.md).

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

Canlı smoke'ta tam Luna/Sol matrisi her görev/model için yalnız bir kez üretilir ve Jev'in seçtiği yol aynı canlı yanıtı yeniden kullanır. Streaming açıktır; ilk boş olmayan metin parçasine kadar TTFT, tam hedef latency ve Jev latency ayrı saklanır.

Timeout gibi usage dönmeyen başarısız çağrılar ücretsiz varsayılmaz; tam çıktı bütçesine göre muhafazakâr tahmin edilir ve measurement hata alanında etiketlenir. Provider usage bulunan retry/fallback çağrıları doğrudan toplam maliyete eklenir.

## Veri ve lisans

`data/demo_pilot.jsonl` pipeline için özgün sentetik 40 görevdir; resmî benchmark değildir. Public benchmark içerikleri repoda yoktur. Adaylar, lisansları ve yeniden üretim politikası `data/SOURCES.json` ile araştırma belgesinde kayıtlıdır. Yeniden dağıtım izni net olmayan içerik commitlenmez.

Kod MIT lisanslıdır. İncelenen RouteLLM commit'i `0b64fdafe049e596a3f5657c219329f24af24198` ve lisansı Apache-2.0'dır; kodu bu repoya kopyalanmamıştır.

## Sınırlar

- 10 görevlik canlı smoke gerçek erişimi ve ölçüm tesisatını doğrular, fakat üretim kalitesi veya istatistiksel non-inferiority kanıtı değildir.
- 40 sentetik görev 2 yüzde puanlık non-inferiority iddiası için yetersizdir.
- Yerel kod evaluator'ü ayrı süreç/resource sınırları yanında macOS `sandbox-exec` veya Linux Bubblewrap ile ağı kapatır ve backend yoksa fail-closed durur. Güvenilmeyen public benchmark çıktıları için yine de tek-kullanımlık container/VM savunma katmanı önerilir.
- Açık uçlu kalite için kör, sıra dengeli judge + insan denetimi henüz canlı veri olmadığı için koşulmamıştır.
- Aynı makinede ağır RAG koşusu sürerken latency benchmarkı çalıştırılmamalıdır.

Kısa kayıt akışı: [docs/DEMO_VIDEO_TR.md](docs/DEMO_VIDEO_TR.md).
