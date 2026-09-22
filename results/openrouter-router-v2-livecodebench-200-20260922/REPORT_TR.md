# OpenRouter Router v2 — LiveCodeBench 200 görev

## Sonuç

Evet, bu kapsamda router başarılı oldu: geliştirme setinde seçilen Jev eşiği değiştirilmeden ikinci 100 soruya uygulandı ve Sol ile **aynı 94/100** sonucu verdi. İki set birlikte değerlendirildiğinde router ve always-Sol aynı 193/200 (`%96,5`) görevi geçti. Eşleştirilmiş düzeyde de fark yoktu: ikisi aynı 193 soruyu geçti ve aynı yedi soruda başarısız oldu.

Router bunu her görevde Sol kullanmadan yaptı. 200 görevin 134'ü (`%67`) Sol'a, 66'sı Luna'ya gitti. Provider tarafından raporlanan politika maliyeti `$0,724891`; always-Sol maliyeti `$0,832256` oldu. Aynı ölçülen kaliteyle tasarruf `$0,107365`, yani `%12,90`.

Bu “iki kat ucuz” sonucu değildir. Doğru ifade şudur: **bu 200 görevlik paired LiveCodeBench deneyinde kalite kaybı gözlenmeden maliyet yaklaşık yüzde 13 azaldı.**

## Deney tasarımı

- Worker çağrıları yerel Codex aboneliğiyle değil, kullanıcının yerel `OPENROUTER_API_KEY` değişkeni üzerinden OpenRouter API'ye gönderildi.
- Adaylar `openai/gpt-5.6-luna` (medium reasoning) ve `openai/gpt-5.6-sol` (high reasoning) idi.
- Router `typesafe/jev-1.13` ile yalnız karar verdi; çözümü Jev üretmedi.
- İlk 100 görev geliştirme/calibration, sonraki 100 görev dokunulmamış test olarak ayrıldı.
- Calibration'da `1 - P(Luna)` için `0,08` eşiği seçildi. Eşik test sonucunu görmeden donduruldu.
- Her iki modelin çözümü aynı sorularda üretildi; başarı yalnız pinlenmiş resmî LiveCodeBench gizli testleriyle ölçüldü.
- Dataset revision: `0fe84c3912ea0c4d4a78037083943e8f0c4dd505`.
- Harness revision: `28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24`.

## Sayılar

| Bölme | Luna | Sol | Router | Sol çağrı oranı | Router maliyeti | Sol maliyeti | Tasarruf |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dev 100 | 92 | 99 | 99 | %66 | $0,348893 | $0,405908 | %14,05 |
| Held-out 100 | 84 | 94 | 94 | %68 | $0,375998 | $0,426348 | %11,81 |
| Birleşik 200 | 176 | 193 | 193 | %67 | $0,724891 | $0,832256 | %12,90 |

Birleşik router/Sol doğruluğu `%96,5`; Wilson `%95` güven aralığı `%92,95–%98,29`. Bu aralık router ile Sol farkının belirsizliği değil, mutlak başarı oranının belirsizliğidir. Bu örnekte paired discordance sıfırdır, fakat yalnız 200 soru daha geniş trafik için eşdeğerlik kanıtı sayılmaz.

## Hız

Kalite ve maliyet kapıları geçti, hız kapısı geçmedi. Held-out router uçtan uca ortalaması yaklaşık `8,40 s`; always-Sol worker ortalaması yaklaşık `7,60 s` idi. Jev kararı yaklaşık yarım saniye ekliyor; ayrıca bu örnekte Luna her zaman Sol'dan hızlı değildi. Router'ı “daha hızlı” diye tanımlamıyoruz.

## Çözüm-sonrası judge ne oldu?

Çözüm sonrası Jev cascade ayrı olarak sınandı. İlk yüzde `0,33` eşiği 38 Sol çağrısıyla 98/100 üretti; always-Sol 99/100 idi ve maliyet `%25,9` daha düşüktü. Dokunulmamış ikinci yüzde aynı eşik 93/100, Sol 94/100 verdi ve tasarruf `%17,7` oldu. Daha agresif, dev'de seçilen `0,66` eşiği ikinci sette 89/100'e düştü; bu yüzden üretim varsayılanı yapılmadı.

Sonuç: çözüm-sonrası judge yararlı bir **balanced mode** oluşturabiliyor, fakat quality-first varsayılan için prompt öncesi kalibre edilmiş router daha güvenilir çıktı.

## Harcama ve 5 USD tavanı

Bu iterasyonda iki modelin 200×2 paired çıktıları, smoke çağrıları ve bütün Jev calibration/judge deneyleri için bilinen provider maliyeti `$1,032690` oldu. Dokuz boş/invalid streaming yanıtta eski collector usage'ı saklayamadı; tam 2.048 output token harcanmış kabul edilen muhafazakâr ek üst sınır `$0,101775`. Böylece toplam muhafazakâr üst sınır `$1,134466`; belirlenen `$5` tavanının çok altında.

Collector daha sonra düzeltildi: boş içerik artık token usage'ıyla birlikte başarısız receipt olarak saklanıyor ve resume aynı pass@1 çağrısını sessizce yeniden örneklemiyor.

## Ne kanıtlandı, ne kanıtlanmadı?

Kanıtlanan:

- OpenRouter tabanlı gerçek worker dispatch çalışıyor.
- Jev'in kalibre edilmiş olasılığı, bu 200 izole Python probleminde Sol'un task-level sonucunu aynen korurken Sol çağrılarını üçte bir azalttı.
- Maliyet, kalite, latency, provider hatası ve gizli test sonucu aynı kimlikle eşleştirilebiliyor.
- Router hata durumunda güçlü modele fail-safe yönleniyor.

Kanıtlanmayan:

- SWE-bench/Terminal-Bench gibi repository ve tool kullanan uzun ajan görevlerinde aynı kazanç.
- Türkçe görevlerde aynı eşik.
- Farklı tarihte veya stochastic tekrar örneklemede aynı yüzde.
- Router'ın Sol'dan hızlı olduğu; bu deneyde değildi.

## Araştırma kararı

Exa ve yerel X API araştırması, prompt-only yönlendirmenin agentic görevlerde bir bilgi tavanı olduğunu gösterdi. Bu nedenle sonraki sürümde repository görevleri için Luna'ya kısa bir keşif trajectory'si verilecek; Jev bu doğrulanabilir ara kanıt üzerinden yükseltme yapacak ve güçlü model temiz bağlamla yeniden başlayacak. Ayrıntılı kaynak sentezi: [`exa-results/router-v2-research-2026-09-22.md`](../../exa-results/router-v2-research-2026-09-22.md).
