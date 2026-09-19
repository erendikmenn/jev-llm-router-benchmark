# Başlangıç araştırması ve sabitlenen sözleşmeler

Kontrol tarihi: **2026-09-19**. Canlı koşudan önce bu kayıt yeniden doğrulanmalıdır.

## TypeSafe / Jev — OpenRouter erişimi

Resmî kaynaklar:

- https://docs.typesafe.ai/concepts/system-one
- https://docs.typesafe.ai/api
- https://docs.typesafe.ai/models
- https://docs.typesafe.ai/model-jaggedness/jev-1.13
- https://docs.typesafe.ai/sdk/python
- https://docs.typesafe.ai/primitives/choice
- https://docs.typesafe.ai/primitives/noul
- https://docs.typesafe.ai/confidence

OpenRouter ve TypeSafe belgeleriyle doğrulanan sözleşme:

- Bu benchmarkın canlı uç noktası `POST https://openrouter.ai/api/alpha/decisions`; bearer `OPENROUTER_API_KEY` kimlik doğrulaması.
- İstek üst alanları `state`, `model`, `questions`.
- Sürüm OpenRouter kimliğiyle `typesafe/jev-1.13` olarak sabitlendi; canlı yanıt sürümlenmiş `typesafe/jev-1.13-20260917` kimliğini döndürdü.
- Jev 1.13 fiyatı girişte $0.042 / 1M token; çıktı tokenları ücretsiz.
- OpenRouter model endpoint'i context sınırını 32k olarak bildirdi.
- Sadece metin; görüntü, ses ve video desteklenmiyor.
- Choice çıktısı `choice`, tüm seçenekler için `probabilities` ve dağılımdan türetilen `confidence` taşır. Noul tek bir `noul` olasılığı verir ve ayrı confidence taşımaz.
- Yanıtta sürümlenmiş `model`, `provider`, `id`, `answers`, `usage.input_tokens`, `usage.output_tokens` ve `usage.cost` alanları bulunur.
- 429/529 için sınırlı exponential backoff gerekir. Resmî Python SDK varsayılanı 2 retry, ilk backoff 0.5 s, üst sınır 5 s ve toplam 30 s retry bütçesidir. Projede politika açıkça konfigüre edilir.
- Jev olasılığı tek isteğin doğruluk yüzdesi değildir. Eşikler yalnız dev kümesinde kalibre edilir.

Jev'in belgelenen pürüzleri tasarımı doğrudan etkiledi: sayım, maliyet hesabı, context uygunluğu ve tarih/matematik kodda kalır; modelden gerekçe üretilmez; state yalnız gerekli alanları içerir; router soruları dar Choice kararlarıdır.

Ek OpenRouter kaynakları:

- https://openrouter.ai/typesafe/jev-1.13
- https://openrouter.ai/openapi.json (`/api/alpha/decisions` sözleşmesi)
- https://openrouter.ai/api/v1/models/typesafe/jev-1.13/endpoints

## Üretici model çifti — OpenRouter

Yerel `OPENROUTER_API_KEY` varlığı değer yazdırılmadan doğrulandı. Model kimlikleri ve fiyatlar authenticated OpenRouter kataloğundan canlı koşu öncesinde okundu:

| Rol | Tam model kimliği | Context | Maks. çıktı | Girdi / cached / çıktı, USD/1M | Streaming |
|---|---|---:|---:|---:|---|
| ucuz | `openai/gpt-5.6-luna` | 1,050,000 | 128,000 | 0.20 / 0.02 / 1.20 | destekleniyor |
| güçlü | `openai/gpt-5.6-sol` | 1,050,000 | 128,000 | 2.00 / 0.20 / 10.00 | destekleniyor |

Kaynaklar:

- https://openrouter.ai/openai/gpt-5.6-luna
- https://openrouter.ai/openai/gpt-5.6-sol
- https://openrouter.ai/api/v1/models

OpenRouter `usage.cost` alanı ölçümde birincil maliyet kaynağıdır. Bu alan yoksa koşu öncesi doğrulanmış katalog fiyatı ile native token usage çarpılır ve kaynak açıkça `calculated_from_usage` diye etiketlenir.

## RouteLLM incelemesi

- Repo: https://github.com/lm-sys/RouteLLM
- İncelenen `main` HEAD: `0b64fdafe049e596a3f5657c219329f24af24198`
- Lisans: Apache-2.0
- Yararlı desenler: iki model arasında eşik kontrollü routing, güçlü model kullanım oranına göre threshold kalibrasyonu, rastgele oran-eşlenmiş kontrol, önceden hesaplanmış model matrisi ile replay evaluation, OpenAI-uyumlu serving yüzeyi.
- Hazır router'lar esas olarak `gpt-4-1106-preview` / `Mixtral-8x7B-Instruct-v0.1` tercih verileri üzerinde eğitilmiş. `mf` ve `sw_ranking` ayrıca OpenAI embedding erişimi istiyor.

Bu ilk sürümde RouteLLM baseline F varsayılan koşuya alınmadı: seçilen GPT-5.6 çiftiyle eğitim eşleşmesi yok, ek embedding maliyeti ve ağır bağımlılık getiriyor, Jev desteği hazır değil. Bu bilinçli bir uyumluluk kararıdır; A–E baseline'ları önce ölçülür. İleride ayrı, açıkça etiketli bir ekstra olarak aynı dev/test protokolüne takılabilir.

## Canlı public benchmark v1 veri kaynakları

İngilizce koşu için dört otomatik ve nesnel puanlanabilir kaynak sabitlendi:

| Kaynak | Revision | Lisans | Dev / test örneği |
|---|---|---|---:|
| CohereLabs/Global-MMLU (`en`) | `0e619dbeb34206cd48705a1a0ea7fb21cae09993` | Apache-2.0 | 50 / 250 |
| facebook/belebele (`eng_Latn`) | `7899cdfa4e1e0d733fd77c848e2c273cb1d32be2` | CC-BY-SA-4.0 | 50 / 250 |
| openai/gsm8k (`main`) | `740312add88f781978c0658806c59bc2815b9866` | MIT | 50 / 250 |
| allenai/ai2_arc (`ARC-Challenge`) | `210d026faf9955653af8916fad021475a3f00453` | CC-BY-SA-4.0 | 50 / 250 |

Kaynak şemaları, split sayıları ve lisanslar Hugging Face Dataset Viewer/Hub API üzerinden doğrulandı. `scripts/build_public_benchmark.py` Parquet dönüşümlerini indirir, sabit seed `20260919` ile seçer ve yerel manifest/hash üretir. Public soru metinleri repoda yeniden dağıtılmaz.

## Önceki veri adayları

Demo pilot 40 özgün sentetik görevden oluşur ve yalnız altyapı doğrulamasıdır. Resmî benchmark diye sunulmaz. Bütçe onayından sonra yüzlerce örnek için aday havuz:

| Grup | Aday | Dil | Lisans / yeniden dağıtım notu |
|---|---|---|---|
| Çok adımlı akıl yürütme | GSM8K | EN | MIT; orijinal test ayrımı korunur |
| Çok dilli matematik | MGSM | EN ve desteklenen diğer diller; Türkçe yok | CC BY 4.0; Türkçe içerdiği varsayılmamalı |
| Genel QA | MMLU seçili alt kümeler | EN | MIT; contamination riski ayrıca raporlanır |
| Kodlama | HumanEval | EN | MIT; model kodu ağsız gerçek sandbox'ta çalıştırılmalı |
| Çeviri | FLORES-200 `tur_Latn`/`eng_Latn` | TR/EN | CC BY-SA 4.0; türetilen dağıtım koşulları korunur |
| Özetleme | XLSum / MLSUM adayları | TR/EN | Lisans veri kartı ve ticari kullanım koşulu yeniden doğrulanmadan içerik repoya alınmaz |
| Extraction / classification | açık şemalı görevlerin lisanslı alt kümesi + ayrı sentetik ürün senaryoları | TR/EN | Sentetik sonuçlar benchmark sonuçlarından ayrı tutulur |

Public veri dosyaları bu repoda yeniden dağıtılmaz. İndirme URL'si, revision/hash ve lisans kabulü kilitlenmeden tam veri hazırlığı tamamlanmış sayılmaz.
