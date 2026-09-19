# Ölçüm protokolü v1

## Hipotez ve önceden tanımlı hedef

Ana hipotez: Jev, hedef model yanıtlarını görmeden ve yalnız kullanıcı isteği, izinli bağlam, görev kısıtları ile dev'de öğrenilmiş yetenek profillerini kullanarak uygun modeli seçebilir.

Önceden tanımlı işletme hedefi, güçlü baseline'a göre toplam kalite/başarı kaybı en fazla **2 yüzde puanı** iken toplam maliyeti azaltmaktır. Bu bilimsel sabit değildir. %95 eşleştirilmiş bootstrap güven aralığı 2 yüzde puanının altında kalite korumasını desteklemiyorsa sonuç “belirsiz” sayılır.

## Split ve sızıntı önlemleri

- Train: bu ilk sürümde klasik bir model eğitilmez.
- Dev: model profilleri, kural baseline'ı ve Jev threshold seçimi.
- Kilitli test: yalnız son değerlendirme. Cevaplar, oracle ve gizli testler router state'ine girmez.
- Normalize edilmiş tam kopyalar split'ler arasında otomatik kontrol edilir. Yakın kopya için tam veri hazırlığında MinHash/embedding incelemesi eklenmeden test kilitlenmez.
- Testte prompt, çıktı bütçesi, concurrency, cache ve sampling/reasoning ayarı model çiftinde aynı tutulur.

## Ana pre-routing akışı

1. Deterministik filtre modality, araç gereksinimi, input/output context sınırlarını kontrol eder.
2. Jev bir Choice ile `cheap`/`strong` yetenek profili arasından seçim sinyali ve ayrı bir Choice ile görev türü üretir.
3. Kod, dev'de seçilmiş `P(strong)` eşiğini uygular. Confidence düşükse açık fallback kuralı güçlü modeldir.
4. Yalnız seçilen üretici model çağrılır.
5. Timeout/429/5xx için en fazla iki retry yapılır. Ucuz yol tamamen başarısız olursa güçlü modele tek fallback uygulanır. Tüm başarılı retry usage kayıtları toplam maliyete girer.

Jev fiyatları görmez ve maliyeti hesaplamaz. Jev açıklama üretmediği için rapor yalnız görev etiketi, skorlar ve uygulanan kod kuralını gösterir.

## Baseline'lar

- A `always_strong`
- B `always_cheap`
- C dev'de sabitlenmiş regex/kural router'ı
- D Jev ile aynı güçlü model kullanım oranında, seed'li rastgele router
- E Jev router, yalnız dev'de seçilmiş threshold
- F RouteLLM bu sürümde uyumsuzluk ve ek embedding maliyeti nedeniyle koşulmaz; gerekçe araştırma belgesindedir.

Tek bir seçilmiş eşik dışında kalibrasyon eğrisinin tamamı saklanır. Canlı raporda ayrıca önceden tanımlı `%25/%50/%75` güçlü kullanım oranlarına en yakın noktalar gösterilmelidir.

## Kalite

- Extraction: JSON parse + alan/değer doğruluğu.
- Sınıflandırma/kapalı QA/matematik: normalize exact match.
- Çeviri/özet demo fixture: önceden tanımlı anahtar kapsama yalnız pipeline testi içindir; gerçek koşuda uygun otomatik metrik + kör insan incelemesi gerekir.
- Kod: ağsız, ayrı süreç, `-I -S`, CPU/bellek/dosya/timeout limitleri. macOS'ta `sandbox-exec`, Linux'ta Bubblewrap ile ağ kapatılır; backend yoksa evaluator fail-closed durur. Bu yerel koruma tam container/VM sandbox yerine geçmez; public HumanEval canlı koşusunda ek tek-kullanımlık container/VM sandbox önerilir.
- Açık uçlu görevler: sabit rubrik, model kimliği gizli, sıra dengeli judge ve örneklenmiş insan kontrolü. Judge üretim sırasında test cevabını göremez.

Farklı metrikler doğrudan “tek skor” diye ortalanmaz. Demo agregası 0–1 normalize görev puanlarının makro ortalamasıdır ve her dil/görev alt grubu ayrıca gösterilir.

## Maliyet ve gecikme

`tasarruf = 1 - routed_toplam_maliyet / always_strong_toplam_maliyet`

Routed toplam maliyet = Jev + seçilen hedef + retry + fallback + varsa validator. Provider usage yoksa değer `estimated/calculated` olarak etiketlenir, fatura denmez. Benchmark matrisi üretme maliyeti ayrı tutulur.

Timeout veya bağlantı hatasında sağlayıcı usage gövdesi dönmezse çağrının ücretsiz olduğu varsayılmaz: başarısız deneme konfigüre edilmiş tam çıktı bütçesiyle muhafazakâr tahmin edilir ve measurement hata alanında bu tahmin açıkça işaretlenir.

Replay kalite/maliyet eğrileri canlı routing gecikmesi değildir. Canlı latency koşusunda yalnız gerçekten seçilen yol çağrılır. Uçtan uca p50/p95, Jev ve hedef süreleri ayrı; streaming açıksa TTFT raporlanır. Ağır RAG benchmarkı ile aynı makinede eşzamanlı adil latency koşusu yapılmaz.

## Pilot ve ölçek

İlk pilot 40 örnektir. Bu sayı pipeline, metrik ve kaba hata tiplerini doğrular; 2 yüzde puanlık non-inferiority iddiasına yetmez. Yüzlerce örnekli test boyutu, pilotta gözlenen eşleştirilmiş fark varyansı ve hedef güven aralığı genişliği ile güç analizi yapılarak seçilir. Bütçe belirlenmeden ücretli matrise başlanmaz.
