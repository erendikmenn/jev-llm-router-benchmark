# 1.055 görevlik resmî kod-router benchmarkı

Tarih: 20 Eylül 2026  
Ana kalite seti: LiveCodeBench `release_v6`, setin tamamı  
Worker: kullanıcının yerel Codex Pro oturumu  
Haricî API: yalnız Jev/OpenRouter yönlendirme ve önceki judge çağrıları  
Jev tavanı: `$5`

## Kısa hüküm

Altyapı ve kapsam hedefi başarılıdır: 1.055 resmî görevin tamamı Jev ile
yönlendirildi, seçilen Codex tier'inde cevaplandı ve LiveCodeBench'in modelden
saklanan resmî testleriyle değerlendirildi. 1.055 dispatch'in tamamı sonuçlandı,
1.055 çözümün tamamı boş olmayan kod üretti ve **913 çözüm geçti**. Ana sonuç
**`%86,54 pass@1`**; `%95` Wilson güven aralığı `%84,35–%88,47` oldu.

Router'ın ürün iddiası ise henüz kanıtlanmış değildir. Aynı ilk 100 görevdeki
eşlenik kontrol `%94` router, `%94` her-zaman-Luna ve `%98` her-zaman-Sol verdi.
Router bu 100 görevde 83 Luna, 6 Terra ve 11 Sol kullandı. Başka bir deyişle
Sol çağrılarının `%89`undan kaçındı, fakat Sol'e karşı 4 puan kalite kaybetti;
ayrıca Sol bu örneklemde daha hızlıydı. Fark 100 görevde istatistiksel olarak
kesin değildir (`McNemar p=0,21875`), fakat “aynı kalite ve daha hızlı” iddiasını
desteklemez.

Bu nedenle nihai karar iki parçalıdır:

- Resmî benchmark entegrasyonu, oracle izolasyonu, yerel Codex dispatch'i ve
  ölçüm hattı: **başarılı**.
- Mevcut Jev routing politikasıyla otonom üretim kullanımı: **henüz hazır değil**;
  hard görev kalibrasyonu ve daha büyük eşlenik kontrol gerekiyor.

## Tam LiveCodeBench sonucu

| Ölçüm | Sonuç |
|---|---:|
| Resmî görev | 1.055 |
| Tamamlanan dispatch | 1.055 |
| Boş olmayan çözüm | 1.055 |
| Geçen | 913 |
| Pass@1 | **%86,54** |
| %95 güven aralığı | %84,35–%88,47 |
| Jev maliyeti, kabul edilen 1.055 satır | `$0,057785` |
| Provider fallback | 1 |

Zorluk kırılımı:

| Zorluk | Görev | Geçen | Pass@1 |
|---|---:|---:|---:|
| Easy | 322 | 314 | **%97,52** |
| Medium | 383 | 336 | **%87,73** |
| Hard | 350 | 263 | **%75,14** |

Seçilen tier dağılımı:

| Tier | Görev | Geçen | Ham pass@1 |
|---|---:|---:|---:|
| Luna | 733 | 661 | %90,18 |
| Terra | 191 | 148 | %77,49 |
| Sol | 130 | 104 | %80,00 |
| Astra | 1 | 0 | %0,00 |

Tier satırları nedensel model karşılaştırması değildir. Router daha zor görevleri
Terra/Sol'a gönderdiği için ham tier yüzdeleri birbirine karşı model kalitesi olarak
okunamaz. Eşlenik kontrol bu nedenle ayrıca çalıştırıldı.

## Eşlenik 100 görev kontrolü

İlk 100 resmî görev aynı kimliklerle üç bağımsız kolda çalıştı. Bu kesitte 35 easy,
47 medium ve 18 hard görev vardı.

| Politika | Geçen | Pass@1 | Worker p50 | Seçimler |
|---|---:|---:|---:|---|
| Jev router | 94/100 | **%94** | 10,41 sn | 83 Luna / 6 Terra / 11 Sol |
| Her zaman Luna | 94/100 | **%94** | 10,56 sn | 100 Luna |
| Her zaman Sol | 98/100 | **%98** | 8,88 sn | 100 Sol |

Router ve Luna farklı üçer görevi kurtardı; eşlenik fark sıfır ve McNemar `p=1,0`.
Router, Sol'un kaçırdığı bir görevi geçti; Sol ise router'ın kaçırdığı beş görevi
geçti. Dört puanlık Sol avantajının iki yönlü exact McNemar değeri `p=0,21875`.
Bu örneklem farkın yönünü gösterir, fakat gerçek farkın tam dört puan olduğunu
kanıtlamak için küçüktür.

Önemli olumsuz sonuç: router, Luna'ya göre daha güçlü tier'i 17 görevde kullandığı
halde toplam doğruluğu yükseltmedi. Sol'e göre güçlü-model kullanımını ciddi azalttı,
fakat bu koşuda hız avantajı da sağlamadı. Ürün hedefi Sol'e göre en fazla 3 puan
kalite kaybı ise gözlenen sonuç 4 puanla hedefin dışındadır.

## Routing tanısı

- 733 görevin `%69,48`i Luna, `%18,10`u Terra, `%12,32`si Sol'a gitti.
- 350 hard görevin 106'sı Luna'da kaldı; bunların yalnız 72'si geçti (`%67,92`).
  Aynı hard havuzun Terra ve Sol'a yönlendirilen kısımları sırasıyla `%77,78` ve
  `%79,00` geçti. Alt kümeler rastgele olmadığı için bu doğrudan model farkı değildir,
  fakat hard→Luna kararlarının yeniden kalibre edilmesi gerektiğine güçlü işarettir.
- Toplam 72 başarısız Luna görevi under-route adayıdır; karşı-olgusal daha güçlü
  model koşusu olmadan bunlara kesin under-route denemez.
- Düşük güvenlik koruması 111 görevi en az Sol'a çıkardı; bu zor alt kümenin başarı
  oranı `%79,28` oldu. Normal Jev profil kuralı 943 görevde `%87,49` verdi.
- Bir Jev isteği HTTP 520 ile başarısız oldu, fail-safe Astra seçildi ve çözüm testten
  geçmedi. 1.055 üretim yönlendirmesinde provider fallback oranı `%0,095`tir.
- Önceden kilitlenen route-only kararları ile gerçek üretim koşusunun tier anlaşması
  `%93,93` oldu. İki bağımsız route-only koşusu arasındaki anlaşma `%88,15`ti.
  Router hâlâ tam deterministik değildir.

## Hız ve kullanım

| Ölçüm | Ortalama/p50/p95 |
|---|---:|
| Jev route ortalama | 0,517 sn |
| Jev route p50 / p95 | 0,458 / 0,664 sn |
| Worker ortalama | 33,36 sn |
| Worker p50 / p95 | 12,78 / 129,00 sn |

Codex kullanımı 20.419.767 input, 17.984.512 cached input, 957.091 output ve
711.044 reasoning-output token oldu. Koşu yüksek paralellikle yapıldığı için uzun
kuyruklar p95'e dahildir; bunlar temiz tek-istek latency sayıları değildir. Gerçek
bir Codex çağrısı 15 dakikada timeout oldu ve aynı görev checkpoint'ten tekrarlandı.
Bu olay segmenti durdurduğu için dispatch katmanı timeout'u `returncode=124` olarak
kaydedecek ve kampanyayı sürdürecek biçimde düzeltildi.

## Para ve hesap kullanımı

Worker modeller için OpenRouter veya OpenAI API anahtarı kullanılmadı. Worker çağrısı
sayısı bakımından API faturası **sıfırdır**; çağrılar kullanıcının Codex Pro oturumundan
çalıştı. Codex haftalık pencere göstergesi koşunun başındaki `%22 kullanılmış`tan
finalde `%25 kullanılmış`a çıktı; gözlenen fark 3 yüzde puandır.

Ana 1.055 kabul satırının Jev maliyeti `$0,057785`; iki sınır tekrarı dahil kaydedilen
üretim yönlendirme maliyeti `$0,057891` oldu. Dört setin 2.375 route-only kararı,
tekrar koşusu, resmî smoke'lar ve SWE judge tanısı dahil bu resmî kodlama kampanyasında
kayda geçmiş Jev toplamı `$0,243786`dır. Interrupt anında satıra yazılamayan yaklaşık
on route çağrısı için konservatif pay eklendiğinde toplam **`$0,245`ten küçüktür**;
`$5` tavanının `%4,9`undan azdır.

Burada “iki kat daha ucuz” diye bir worker USD iddiası kurmuyoruz. Codex aboneliğinde
model başına fatura yoktur. Gözlenen kaynak avantajı, ilk 100 kontrolde 100 Sol yerine
11 Sol kullanılmasıdır; bunun parasal karşılığı bu çalışma düzeninde ölçülmemiştir.

## Diğer resmî setler

Dört kilitli sette toplam 2.375/2.375 görev için Jev kararı üretildi:
LiveCodeBench 1.055, SWE-bench Verified 500, SWE-bench Pro public 731 ve
Terminal-Bench 2 89. Bunların yönlendirme maliyeti `$0,123703`, route p50'si
`455 ms`, p95'i `676 ms` ve provider fallback sayısı sıfırdı.

Kalite açısından dört setin tamamı aynı sayıda gerçek agent göreviyle çözülmedi:

- LiveCodeBench: **1.055/1.055 tam kalite koşusu**, 913 geçti.
- SWE-bench Verified: 2 görev × 6 kol; router-only 1/2, router+judge 2/2,
  always-Luna 0/2, Terra 2/2, Sol 1/2, Astra 2/2.
- SWE-bench Pro public: bir gerçek Sol repository-agent görevi resmî Docker
  evaluator'da 1/1 geçti.
- Terminal-Bench 2: bir gerçek Sol görevi Harbor'da reward `1,0` ile geçti.

Son üç satır entegrasyon kanıtıdır, genel başarı yüzdesi değildir. 500+731+89 ağır
agent görevinin tamamını çözmüş gibi raporlanmamıştır; kullanıcı tarafından istenen
en az 1.000 gerçek resmî değerlendirme LiveCodeBench'in 1.055 görevinin tamamıyla
karşılandı.

## Güvenilirlik ve sonraki karar

Şu anda kabul edilebilir iddia: “Router resmî, gizli-testli 1.055 kod görevinde
`%86,54` pass@1 verdi ve görevlerin yaklaşık `%69,5`ini Luna'ya yönlendirdi.”

Şu anda kabul edilemez iddia: “Router Sol kalitesini koruyor, iki kat ucuz ve daha
hızlı.” İlk 100 eşlenik kontrol kalite ve hız tarafında bunu doğrulamadı; abonelik
düzeninde worker USD maliyeti de yok.

Bir sonraki kalibrasyon turunda hard→Luna eşiği yükseltilmeli, Jev kararları
deterministikleştirilmeli ve en az 500 sabit görevde router/Luna/Sol eşlenik olarak
yeniden çalıştırılmalıdır. Judge bu aşamada otomatik merge kapısı değil, shadow/advisory
modunda kalmalıdır.

## Kaynak bütünlüğü

- LiveCodeBench dataset/harness revision: `28fef95...`
- Dataset plan hash'i: `6108435b7b39af8ffaf11dc6c206adb6fa2ae92d6f01ea58ae0134ba345fd47a`
- Model girdisinden çıkarılan alanlar: public/private testler ve metadata
- Ölçüm etiketi: yalnız resmî evaluator sonucu
- Ham üçüncü taraf soru, test ve model çıktıları Git deposuna eklenmez; yalnız özet,
  protokol, kaynak revision'ı ve hash commitlenir.
