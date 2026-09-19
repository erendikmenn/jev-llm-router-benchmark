# jev-llm-router-benchmark

Jev ile iki üretici LLM arasında **yanıt üretilmeden önce** seçim yapan, kalite–maliyet–gecikme değişimini aynı görevler üzerinde ölçen bağımsız açık kaynak proje.

Bu repo bir RAG projesi değildir ve başka ErenAILab projelerinden bağımsızdır. Ana sonuç ilkesi: “ucuzladı” tek başına başarı değildir; kalite farkı, eşleştirilmiş belirsizlik, hata/fallback oranı ve mutlak USD ile birlikte raporlanır.

> Mevcut repodaki sonuçlar 40 görevlik **sentetik fixture pilotudur**. Gerçek API anahtarı bulunmadığından canlı benchmark çalıştırılmamıştır; fixture USD ve latency değerleri fatura veya canlı ölçüm değildir.

## Mimari

```text
istek + izinli bağlam + kısıtlar
                │
        deterministik uygunluk
        (text / tools / context)
                │
         Jev 1.13.0 Choice
       görev türü + model uygunluğu
                │
     kodda threshold / fallback / bütçe
          ┌─────┴─────┐
  gpt-5.6-luna   gpt-5.6-sol
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

# Jev ile canlı route (TYPESAFE_API_KEY gerekir)
uv run jev-router route --mode live-jev --threshold 0.58 --prompt "..."

# Bir aday modeli doğrudan fixture üzerinde çalıştır
uv run jev-router run-model --task-id demo-003 --role cheap

# Dev kalibrasyonu, tam eğriyle
uv run jev-router calibrate

# Beş test görevlik smoke
uv run jev-router smoke

# Kilitli testte A–E fixture benchmarkı
uv run jev-router benchmark --mode fixture --output results/fixture-test

# Canlı koşu: pozitif hard limit olmadan başlamaz
uv run jev-router estimate --split test
uv run jev-router benchmark --mode live --max-usd 5.00 --output results/live-001

# Yerel demo
uv run jev-router demo --port 8765
```

`benchmark` threshold verilmezse yalnız dev split'inde kalibre eder, sonra test split'ini çalıştırır. Rastgele baseline, Jev'in güçlü model kullanım oranıyla ve sabit seed ile eşleştirilir.

## Anahtar ve gizlilik

`.env.example` yalnız değişken adlarını gösterir. Uygulama `TYPESAFE_API_KEY` ve `OPENAI_API_KEY` değerlerini yalnız process environment'tan okur; `.env` dosyasını kendi başına yüklemez, değerleri loglamaz. `environment` komutu yalnız boolean var/yok sonucu verir. Demo formu girdiyi yanıtta veya server logunda göstermez.

## Model ve fiyat kayıtları

- Router: sabit `jev-1.13.0`, text-only, 64k istek / 32k state+en uzun soru, $0.042 / 1M input token.
- Ucuz aday: `gpt-5.6-luna`, 1.05M context, $0.20 / $0.02 cached / $1.20 output per 1M.
- Güçlü aday: `gpt-5.6-sol`, 1.05M context, $4.00 / $0.40 cached / $20.00 output per 1M.

Kontrol tarihi 2026-09-19'dur. Sol fiyatı geçici promosyon içerdiği için canlı koşudan hemen önce `configs/default.toml` güncellenmeli ve commitlenmelidir. Kaynak/sözleşme ayrıntıları [docs/RESEARCH.md](docs/RESEARCH.md), deney tasarımı [docs/PROTOCOL_TR.md](docs/PROTOCOL_TR.md) içindedir.

## Sonuç artefaktları

Her koşu dizini şunları üretir:

- `measurements.jsonl` ve `measurements.csv`: görev/baseline bazında model, kalite, usage, target/Jev/toplam maliyet, route ve latency.
- `summary.json`: kalite farkı ve eşleştirilmiş bootstrap GA, başarı, hata/fallback, model oranları, USD/istek, USD/1000, USD/başarı ve p50/p95.
- `manifest.json`: commit, tam model kimlikleri, veri hash'i, prompt/fiyat sürümleri, seed, retry, cache, concurrency ve streaming ayarları.
- `cost-quality.svg`, `latency-quality.svg`, `REPORT_TR.md`.

Tam model matrisi üretimi ile canlı routing ayrı deneylerdir. Fixture/replay latency canlı ölçüm diye sunulmaz. Streaming varsayılan olarak kapalı olduğu için TTFT `null` kalır; streaming açılan ayrı protokolde raporlanmalıdır.

## Veri ve lisans

`data/demo_pilot.jsonl` pipeline için özgün sentetik 40 görevdir; resmî benchmark değildir. Public benchmark içerikleri repoda yoktur. Adaylar, lisansları ve yeniden üretim politikası `data/SOURCES.json` ile araştırma belgesinde kayıtlıdır. Yeniden dağıtım izni net olmayan içerik commitlenmez.

Kod MIT lisanslıdır. İncelenen RouteLLM commit'i `0b64fdafe049e596a3f5657c219329f24af24198` ve lisansı Apache-2.0'dır; kodu bu repoya kopyalanmamıştır.

## Sınırlar

- API anahtarları olmadığı için mevcut artefaktlar gerçek model yeteneklerini ölçmez.
- 40 sentetik görev 2 yüzde puanlık non-inferiority iddiası için yetersizdir.
- Yerel kod evaluator'ü process/resource sınırları uygular ama güvenilmeyen public benchmark çıktıları için container/VM düzeyinde ağsız sandbox gerekir.
- Açık uçlu kalite için kör, sıra dengeli judge + insan denetimi henüz canlı veri olmadığı için koşulmamıştır.
- Aynı makinede ağır RAG koşusu sürerken latency benchmarkı çalıştırılmamalıdır.

Kısa kayıt akışı: [docs/DEMO_VIDEO_TR.md](docs/DEMO_VIDEO_TR.md).

