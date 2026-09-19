# Başlangıç araştırması ve sabitlenen sözleşmeler

Kontrol tarihi: **2026-09-19**. Canlı koşudan önce bu kayıt yeniden doğrulanmalıdır.

## TypeSafe / Jev

Resmî kaynaklar:

- https://docs.typesafe.ai/concepts/system-one
- https://docs.typesafe.ai/api
- https://docs.typesafe.ai/models
- https://docs.typesafe.ai/model-jaggedness/jev-1.13
- https://docs.typesafe.ai/sdk/python
- https://docs.typesafe.ai/primitives/choice
- https://docs.typesafe.ai/primitives/noul
- https://docs.typesafe.ai/confidence

Doğrulanan sözleşme:

- Uç nokta `POST https://api.typesafe.ai/v1/systemone`; bearer kimlik doğrulaması.
- İstek üst alanları `state`, `model`, `questions`.
- Sürüm `jev-1.13.0` olarak sabitlendi. `jev-latest` 2026-09-19'da bu sürüme işaret ediyor ancak hareketli alias kullanılmıyor.
- Jev 1.13 fiyatı girişte $0.042 / 1M token; çıktı tokenları ücretsiz.
- İstek context sınırı 64k; `state + en uzun soru` sınırı 32k.
- Sadece metin; görüntü, ses ve video desteklenmiyor.
- Choice çıktısı `choice`, tüm seçenekler için `probabilities` ve dağılımdan türetilen `confidence` taşır. Noul tek bir `noul` olasılığı verir ve ayrı confidence taşımaz.
- Yanıtta sürümlenmiş `model`, `answers`, `usage.input_tokens`, `usage.output_tokens` alanları bulunur.
- 429/529 için sınırlı exponential backoff gerekir. Resmî Python SDK varsayılanı 2 retry, ilk backoff 0.5 s, üst sınır 5 s ve toplam 30 s retry bütçesidir. Projede politika açıkça konfigüre edilir.
- Jev olasılığı tek isteğin doğruluk yüzdesi değildir. Eşikler yalnız dev kümesinde kalibre edilir.

Jev'in belgelenen pürüzleri tasarımı doğrudan etkiledi: sayım, maliyet hesabı, context uygunluğu ve tarih/matematik kodda kalır; modelden gerekçe üretilmez; state yalnız gerekli alanları içerir; router soruları dar Choice kararlarıdır.

## Üretici model çifti

Erişim anahtarları mevcut olmadığı için hesap erişimi doğrulanamadı. Aday çift aynı sağlayıcının aynı kuşak iki seviyesi seçilerek sağlayıcı farkı azaltıldı:

| Rol | Tam model kimliği | Context | Maks. çıktı | Girdi / cached / çıktı, USD/1M | Streaming |
|---|---|---:|---:|---:|---|
| ucuz | `gpt-5.6-luna` | 1,050,000 | 128,000 | 0.20 / 0.02 / 1.20 | destekleniyor |
| güçlü | `gpt-5.6-sol` | 1,050,000 | 128,000 | 4.00 / 0.40 / 20.00 | destekleniyor |

Kaynaklar:

- https://developers.openai.com/api/docs/models/gpt-5.6-luna
- https://developers.openai.com/api/docs/models/gpt-5.6-sol

`gpt-5.6-sol` fiyatı resmî sayfada en az 2026-11-21'e kadar promosyon olarak belirtiliyor. Bu nedenle her canlı koşu öncesi fiyat yenilemesi zorunludur. Model sayfaları tarihli snapshot göstermediği için model kimlikleri var olan en dar resmî kimlikle sabitlendi; manifest her canlı yanıtta sağlayıcının döndürdüğü model kimliğini de saklar.

## RouteLLM incelemesi

- Repo: https://github.com/lm-sys/RouteLLM
- İncelenen `main` HEAD: `0b64fdafe049e596a3f5657c219329f24af24198`
- Lisans: Apache-2.0
- Yararlı desenler: iki model arasında eşik kontrollü routing, güçlü model kullanım oranına göre threshold kalibrasyonu, rastgele oran-eşlenmiş kontrol, önceden hesaplanmış model matrisi ile replay evaluation, OpenAI-uyumlu serving yüzeyi.
- Hazır router'lar esas olarak `gpt-4-1106-preview` / `Mixtral-8x7B-Instruct-v0.1` tercih verileri üzerinde eğitilmiş. `mf` ve `sw_ranking` ayrıca OpenAI embedding erişimi istiyor.

Bu ilk sürümde RouteLLM baseline F varsayılan koşuya alınmadı: seçilen GPT-5.6 çiftiyle eğitim eşleşmesi yok, ek embedding maliyeti ve ağır bağımlılık getiriyor, Jev desteği hazır değil. Bu bilinçli bir uyumluluk kararıdır; A–E baseline'ları önce ölçülür. İleride ayrı, açıkça etiketli bir ekstra olarak aynı dev/test protokolüne takılabilir.

## Veri adayları

Demo pilot 40 özgün sentetik görevden oluşur ve yalnız altyapı doğrulamasıdır. Resmî benchmark diye sunulmaz. Bütçe onayından sonra yüzlerce örnek için aday havuz:

| Grup | Aday | Dil | Lisans / yeniden dağıtım notu |
|---|---|---|---|
| Çok adımlı akıl yürütme | GSM8K | EN | MIT; orijinal test ayrımı korunur |
| Çok dilli matematik | MGSM | TR/EN | CC BY 4.0; resmi split ve atıf korunur |
| Genel QA | MMLU seçili alt kümeler | EN | MIT; contamination riski ayrıca raporlanır |
| Kodlama | HumanEval | EN | MIT; model kodu ağsız gerçek sandbox'ta çalıştırılmalı |
| Çeviri | FLORES-200 `tur_Latn`/`eng_Latn` | TR/EN | CC BY-SA 4.0; türetilen dağıtım koşulları korunur |
| Özetleme | XLSum / MLSUM adayları | TR/EN | Lisans veri kartı ve ticari kullanım koşulu yeniden doğrulanmadan içerik repoya alınmaz |
| Extraction / classification | açık şemalı görevlerin lisanslı alt kümesi + ayrı sentetik ürün senaryoları | TR/EN | Sentetik sonuçlar benchmark sonuçlarından ayrı tutulur |

Public veri dosyaları bu repoda yeniden dağıtılmaz. İndirme URL'si, revision/hash ve lisans kabulü kilitlenmeden tam veri hazırlığı tamamlanmış sayılmaz.

