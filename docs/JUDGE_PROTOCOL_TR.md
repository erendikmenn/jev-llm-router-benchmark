# Jev code-judge benchmark protokolü

Tarih: 2026-09-20

## Ölçülen sistem

Judge bir kod üreticisi değildir. Yerel olarak toplanan görev, kabul kriterleri, Git diff'i, ilgili güncel kod, haricî kanıtlar, yasak değişiklikler ve risk bayraklarından atomik sinyaller üretir. Kod politikası bu sinyalleri dört eylemden birine dönüştürür:

- `accept`: değişiklik yeterli ve düşük riskli görünüyor;
- `revise`: aynı worker'ın düzeltebileceği açık eksik var;
- `escalate`: belirsizlik, yüksek etki veya derin inceleme gereksinimi var;
- `block`: politika ihlali ya da kritik risk var.

Jev'e tek bir “kod iyi mi?” sorusu sorulmaz. Gereksinim tamlığı, kapsam uyumu, davranış kanıtı, regresyon riski, self-test bias, derin review gereksinimi ve politika ihlali ayrı olasılık sinyalleridir. Risk seviyesi de ayrı bir `Choice` dağılımıdır. Nihai eylem, sürümlü ve test edilen deterministik eşiklerden çıkar.

## Test bias yaklaşımı

Agent'ın yazdığı lint, type-check ve testler yararlı kanıttır ama bağımsız oracle değildir. Paket varsayılan olarak `agent_authored_tests_are_independent = false` kaydeder. Judge ayrıca doğrudan diff'i, güncel ilgili kodu, kabul kriterlerini, değişiklik kapsamını ve risk yollarını görür. Bununla birlikte model incelemesi gizli haricî testin yerini tutmaz. Gerçek coding benchmarkında birincil başarı ölçüsü, agent'ın görmediği evaluator testleri veya insan doğrulamasıdır.

## Veri ve split

`data/code_judge_synthetic_v1.jsonl` 40 özgün sentetik vakadan oluşur: her eylem için 10 vaka. Vakaların 12'si dev, 28'i test split'indedir. Her kayıtta gerçek unified before/after diff, ilgili kod, kabul kriterleri, kanıt ve oracle gerekçesi vardır.

Kalibrasyon sırası:

1. Fixture ile veri yükleme, politika ve raporlama tesisatı doğrulandı.
2. Yalnız dev split'i üzerinde Jev davranışı incelendi.
3. Dataset iç tutarlılık kusurları düzeltildi.
4. Muhafazakâr eşikler dev split'inde bir kez ayarlandı.
5. Politika dondurulduktan sonra 28 test vakası tek canlı koşuda değerlendirildi.

Test sonuçları görüldükten sonra eşik değiştirilmedi. Eski keşif koşuları nihai sonuç olarak repoya alınmadı.

## Metrikler

- Dört-sınıf doğruluk: tam eylem eşleşmesi.
- Unsafe false-pass: oracle eylemi `accept` değilken sistemin `accept` demesi.
- Unsafe detection recall: oracle `accept` değilken sistemin bunu kabul etmemesi.
- Accept precision: sistemin kabul ettiği değişikliklerin gerçekten kabul sınıfında olma oranı.
- Valid accept recall: gerçekten kabul edilebilir değişikliklerin kabul edilme oranı.
- Escalation/block recall: derin inceleme veya blok gerektiren vakaların bu iki güvenli eylemden birine gitmesi.
- Provider hatası, maliyet, input token, ortalama/p50/p95 gecikme.

Exact accuracy tek başına yeterli değildir. Bir güvenlik kapısında yanlış kabul ile gereksiz escalation aynı maliyete sahip değildir; bu nedenle iki hata ayrı raporlanır.

## Sonuçlar

| Split | Vaka | Exact | Unsafe false-pass | Unsafe detection | Accept precision | Valid accept recall | Escalation recall | Maliyet | Ortalama / p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Dev | 12 | %91.7 | 0 | %100 | %100 | %66.7 | %100 | $0.000504 | 526 / 630 ms |
| Held-out test | 28 | %71.4 | 0 | %100 | %100 | %28.6 | %78.6 | $0.001196 | 513 / 648 ms |

Test confusion özeti:

- yedi `block` vakasının tamamı doğru bloklandı;
- yedi `revise` vakasının tamamı doğru revize edildi;
- yedi `escalate` vakasının dördü escalate, üçü revise oldu; hiçbiri kabul edilmedi;
- yedi geçerli vakanın ikisi kabul, beşi gereksiz escalate oldu.

## Yorum

İlk politika güvenlik yönünde başarılı, verim yönünde zayıftır. “Riskli değişikliği otomatik kabul etmeme” bu sentetik sette `%100`; fakat geçerli değişiklik kabul recall'ı `%28.6` olduğu için sistemi bugün zorunlu merge kapısı yapmak geliştirici akışını gereksiz yavaşlatır. En uygun ilk kullanım shadow mode veya tavsiye veren ikinci görüş modudur.

`%71.4` tam eylem doğruluğu “kod görevlerinin %71.4'ünü çözüyor” anlamına gelmez. Burada ölçülen şey patch üretimi değil, önceden hazırlanmış değişiklikler üzerindeki kontrol eylemidir.

## Gizlilik ve sınırlar

`review`/`control` canlı modunda temizlenmiş diff ve ilgili kod OpenRouter veya TypeSafe Jev endpoint'ine gönderilir. Hassas dosya adları dışlanır, bilinen secret biçimleri redakte edilir ve toplam state boyutu sınırlandırılır. Bu korumalar mutlak veri kaybı önleme garantisi değildir.

Sentetik 28 vaka; framework çeşitliliği, büyük repository bağlamı, araç çıktısı sahteciliği, prompt injection ve uzun ufuklu agent davranışı için yeterli değildir. Bir sonraki ölçüm katmanı:

1. shadow mode gerçek repository görevleri;
2. SWE-bench Verified uyumluluk alt kümesi;
3. Terminal-Bench tarzı terminal görevleri;
4. agent'tan gizli bağımsız testler;
5. risk sınıfına göre bootstrap güven aralıkları ve insan review audit'i.

Ham ölçümler `results/judge-openrouter-dev-final-20260920/` ve `results/judge-openrouter-test-20260920/` dizinlerindedir. `judge-report` komutu mevcut JSONL'den yeni API çağrısı yapmadan metrikleri yeniden üretir.
