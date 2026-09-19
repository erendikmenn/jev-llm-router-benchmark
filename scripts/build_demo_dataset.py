#!/usr/bin/env python3
"""Build the 40-item synthetic pilot.

These tasks are for pipeline verification only. They are intentionally labelled
`synthetic_demo` and must never be reported as public benchmark results.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def cases() -> list[dict]:
    rows: list[dict] = []

    def add(language: str, group: str, prompt: str, metric: str, expected, cheap: str, strong: str, *, tests=None, strong_probability: float, task_type: str) -> None:
        index = len(rows) + 1
        split = "dev" if (index - 1) % 4 < 2 else "test"
        rows.append({
            "id": f"demo-{index:03d}",
            "split": split,
            "language": language,
            "group": group,
            "prompt": prompt,
            "metric": metric,
            "expected": expected,
            "constraints": {"modality": "text", "requires_tools": False, "max_output_tokens": 256, "source": "synthetic_demo"},
            "fixture": {
                "cheap": fixture(cheap, index, False),
                "strong": fixture(strong, index, True),
            },
            "jev_fixture": {
                "choice": "strong" if strong_probability >= 0.5 else "cheap",
                "probabilities": {"cheap": round(1 - strong_probability, 3), "strong": strong_probability},
                "confidence": round(abs(strong_probability - 0.5) * 1.7 + 0.15, 3),
                "task_type": task_type,
                "usage": {"input_tokens": 210 + len(prompt) // 3, "cached_input_tokens": 0, "output_tokens": 24},
                "latency_ms": 24 + index % 7,
            },
            "tests": tests or [],
        })

    # English: four tasks per group.
    add("en", "extraction_classification", "Return JSON with name and age from: Maya is 31 years old.", "json_match", {"name": "Maya", "age": 31}, '{"name":"Maya","age":31}', '{"name":"Maya","age":31}', strong_probability=.12, task_type="extraction_classification")
    add("en", "extraction_classification", "Classify the message as billing, technical, or sales. Output only the label: My card was charged twice.", "exact_normalized", "billing", "billing", "billing", strong_probability=.16, task_type="extraction_classification")
    add("en", "extraction_classification", "Return JSON with city and ISO country code: The office moved to İzmir, Türkiye.", "json_match", {"city": "İzmir", "country": "TR"}, '{"city":"Izmir","country":"TR"}', '{"city":"İzmir","country":"TR"}', strong_probability=.25, task_type="extraction_classification")
    add("en", "extraction_classification", "Classify as positive, neutral, or negative. Output only the label: It works, but setup took longer than expected.", "exact_normalized", "neutral", "negative", "neutral", strong_probability=.35, task_type="extraction_classification")

    add("en", "translation_summary", "Translate to Turkish: The meeting has been moved to Friday morning.", "translation_keywords", ["toplantı", "cuma", "sabah"], "Toplantı cuma sabahına alındı.", "Toplantı cuma sabahına ertelendi.", strong_probability=.14, task_type="translation_summary")
    add("en", "translation_summary", "Summarize in one sentence: Solar panels convert sunlight into electricity. Batteries store surplus energy for use after sunset.", "summary_keywords", ["solar", "electricity", "batteries", "store"], "Solar panels make electricity and batteries store it.", "Solar panels generate electricity while batteries store surplus energy for later use.", strong_probability=.18, task_type="translation_summary")
    add("en", "translation_summary", "Rewrite politely: Send the report now.", "contains_all", ["please", "report"], "Please send the report now.", "Could you please send the report now?", strong_probability=.10, task_type="translation_summary")
    add("en", "translation_summary", "Summarize without numbers: Revenue rose 12%, costs rose 4%, so operating margin improved.", "summary_keywords", ["revenue", "costs", "margin", "improved"], "Revenue and costs rose; margin improved.", "Revenue grew faster than costs, improving the operating margin.", strong_probability=.22, task_type="translation_summary")

    add("en", "general_qa", "What is the capital of Portugal? Output only the city.", "exact_normalized", "Lisbon", "Lisbon", "Lisbon", strong_probability=.10, task_type="general_qa")
    add("en", "general_qa", "Which gas do plants primarily absorb during photosynthesis? Output only the gas name.", "exact_normalized", "carbon dioxide", "carbon dioxide", "carbon dioxide", strong_probability=.15, task_type="general_qa")
    add("en", "general_qa", "Who wrote The Dispossessed? Output only the author name.", "exact_normalized", "Ursula K. Le Guin", "Ursula Le Guin", "Ursula K. Le Guin", strong_probability=.28, task_type="general_qa")
    add("en", "general_qa", "What SI unit measures electrical resistance? Output only the unit.", "exact_normalized", "ohm", "volt", "ohm", strong_probability=.32, task_type="general_qa")

    add("en", "multi_step_reasoning", "A box has 3 red and 2 blue balls. Two are drawn without replacement. How many unordered color outcomes are possible? Output only the number.", "exact_normalized", "3", "4", "3", strong_probability=.72, task_type="multi_step_reasoning")
    add("en", "multi_step_reasoning", "If every glib is a tor and no tor is a mip, can any glib be a mip? Output only yes or no.", "exact_normalized", "no", "no", "no", strong_probability=.61, task_type="multi_step_reasoning")
    add("en", "multi_step_reasoning", "A train travels 120 km at 60 km/h and returns at 40 km/h. What is the average speed for the whole trip? Output only km/h.", "exact_normalized", "48", "50", "48", strong_probability=.82, task_type="multi_step_reasoning")
    add("en", "multi_step_reasoning", "Find the next term: 2, 6, 12, 20, 30. Output only the number.", "exact_normalized", "42", "42", "42", strong_probability=.55, task_type="multi_step_reasoning")

    add("en", "coding", "Write Python function clamp(x, low, high) that returns x limited to the inclusive range.", "python_tests", None, "def clamp(x, low, high):\n    return min(high, max(low, x))", "def clamp(x, low, high):\n    if low > high: raise ValueError('low > high')\n    return min(high, max(low, x))", tests=[{"expression": "clamp(9, 0, 5) == 5"}, {"expression": "clamp(-2, 0, 5) == 0"}, {"expression": "clamp(3, 0, 5) == 3"}], strong_probability=.42, task_type="coding")
    add("en", "coding", "Write Python function is_palindrome(text) ignoring case and non-alphanumeric characters.", "python_tests", None, "def is_palindrome(text):\n    return text.lower() == text.lower()[::-1]", "def is_palindrome(text):\n    s = ''.join(c.casefold() for c in text if c.isalnum())\n    return s == s[::-1]", tests=[{"expression": "is_palindrome('A man, a plan, a canal: Panama')"}, {"expression": "not is_palindrome('router')"}], strong_probability=.68, task_type="coding")
    add("en", "coding", "Write Python function chunks(items, size) returning consecutive lists. Raise ValueError when size is not positive.", "python_tests", None, "def chunks(items, size):\n    return [items[i:i+size] for i in range(0, len(items), size)]", "def chunks(items, size):\n    if size <= 0: raise ValueError('size')\n    return [items[i:i+size] for i in range(0, len(items), size)]", tests=[{"expression": "chunks([1,2,3,4,5], 2) == [[1,2],[3,4],[5]]"}, {"expression": "chunks([], 2) == []"}, {"expression": "raises(lambda: chunks([1], 0))"}], strong_probability=.79, task_type="coding")
    add("en", "coding", "Write Python function dedupe(items) preserving first-seen order; items may be unhashable lists.", "python_tests", None, "def dedupe(items):\n    return list(dict.fromkeys(items))", "def dedupe(items):\n    out = []\n    for item in items:\n        if item not in out: out.append(item)\n    return out", tests=[{"expression": "dedupe([[1],[1],[2]]) == [[1],[2]]"}, {"expression": "dedupe([2,1,2]) == [2,1]"}], strong_probability=.86, task_type="coding")

    # Turkish: four tasks per group.
    add("tr", "extraction_classification", "Şu metinden ad ve yaşı JSON olarak döndür: Kerem 27 yaşındadır.", "json_match", {"ad": "Kerem", "yaş": 27}, '{"ad":"Kerem","yaş":27}', '{"ad":"Kerem","yaş":27}', strong_probability=.18, task_type="extraction_classification")
    add("tr", "extraction_classification", "Mesajı faturalama, teknik veya satış diye sınıflandır. Yalnız etiketi yaz: Uygulama açılırken çöküyor.", "exact_normalized", "teknik", "teknik", "teknik", strong_probability=.20, task_type="extraction_classification")
    add("tr", "extraction_classification", "Metinden şehir ve plaka kodunu JSON olarak çıkar: Etkinlik Eskişehir'de yapılacak.", "json_match", {"şehir": "Eskişehir", "plaka": 26}, '{"şehir":"Eskişehir","plaka":"26"}', '{"şehir":"Eskişehir","plaka":26}', strong_probability=.33, task_type="extraction_classification")
    add("tr", "extraction_classification", "Duyguyu olumlu, nötr veya olumsuz sınıflandır. Yalnız etiketi yaz: Ürün güzel ama teslimat berbattı.", "exact_normalized", "nötr", "olumsuz", "nötr", strong_probability=.40, task_type="extraction_classification")

    add("tr", "translation_summary", "İngilizceye çevir: Toplantı cuma sabahına alındı.", "translation_keywords", ["meeting", "moved", "friday", "morning"], "The meeting was moved to Friday morning.", "The meeting has been moved to Friday morning.", strong_probability=.16, task_type="translation_summary")
    add("tr", "translation_summary", "Tek cümlede özetle: Güneş panelleri ışığı elektriğe çevirir. Bataryalar fazla enerjiyi gece kullanmak için saklar.", "summary_keywords", ["güneş", "elektrik", "batarya", "saklar"], "Güneş elektrik üretir, batarya saklar.", "Güneş panelleri elektrik üretir ve bataryalar fazla enerjiyi gece için saklar.", strong_probability=.21, task_type="translation_summary")
    add("tr", "translation_summary", "Kibarca yeniden yaz: Dosyayı hemen gönder.", "contains_all", ["lütfen", "dosya"], "Lütfen dosyayı hemen gönderin.", "Dosyayı lütfen en kısa sürede gönderebilir misiniz?", strong_probability=.12, task_type="translation_summary")
    add("tr", "translation_summary", "Sayı kullanmadan özetle: Gelir yüzde 12, maliyet yüzde 4 arttı; faaliyet marjı iyileşti.", "summary_keywords", ["gelir", "maliyet", "marj", "iyileşti"], "Gelir ve maliyet arttı, marj iyileşti.", "Gelir maliyetten daha hızlı arttığı için faaliyet marjı iyileşti.", strong_probability=.25, task_type="translation_summary")

    add("tr", "general_qa", "Portekiz'in başkenti neresidir? Yalnız şehri yaz.", "exact_normalized", "Lizbon", "Lizbon", "Lizbon", strong_probability=.12, task_type="general_qa")
    add("tr", "general_qa", "Bitkiler fotosentez sırasında en çok hangi gazı emer? Yalnız gazı yaz.", "exact_normalized", "karbondioksit", "karbondioksit", "karbondioksit", strong_probability=.17, task_type="general_qa")
    add("tr", "general_qa", "Mülksüzler romanını kim yazdı? Yalnız yazarın adını yaz.", "exact_normalized", "Ursula K. Le Guin", "Ursula Le Guin", "Ursula K. Le Guin", strong_probability=.31, task_type="general_qa")
    add("tr", "general_qa", "Elektrik direncinin SI birimi nedir? Yalnız birimi yaz.", "exact_normalized", "ohm", "volt", "ohm", strong_probability=.37, task_type="general_qa")

    add("tr", "multi_step_reasoning", "Bir kutuda 3 kırmızı ve 2 mavi top var. Yerine koymadan iki top çekiliyor. Kaç sırasız renk sonucu mümkündür? Yalnız sayıyı yaz.", "exact_normalized", "3", "4", "3", strong_probability=.75, task_type="multi_step_reasoning")
    add("tr", "multi_step_reasoning", "Her glib bir tor ise ve hiçbir tor mip değilse, herhangi bir glib mip olabilir mi? Yalnız evet veya hayır yaz.", "exact_normalized", "hayır", "hayır", "hayır", strong_probability=.64, task_type="multi_step_reasoning")
    add("tr", "multi_step_reasoning", "Bir tren 120 km yolu 60 km/s ile gidip 40 km/s ile dönüyor. Tüm yolculuğun ortalama hızı kaç km/s? Yalnız sayıyı yaz.", "exact_normalized", "48", "50", "48", strong_probability=.84, task_type="multi_step_reasoning")
    add("tr", "multi_step_reasoning", "Dizinin sonraki terimini bul: 2, 6, 12, 20, 30. Yalnız sayıyı yaz.", "exact_normalized", "42", "42", "42", strong_probability=.57, task_type="multi_step_reasoning")

    add("tr", "coding", "x değerini kapalı [alt, üst] aralığına sınırlayan clamp(x, alt, ust) Python fonksiyonunu yaz.", "python_tests", None, "def clamp(x, alt, ust):\n    return min(ust, max(alt, x))", "def clamp(x, alt, ust):\n    if alt > ust: raise ValueError('aralık')\n    return min(ust, max(alt, x))", tests=[{"expression": "clamp(9, 0, 5) == 5"}, {"expression": "clamp(-2, 0, 5) == 0"}], strong_probability=.46, task_type="coding")
    add("tr", "coding", "Büyük-küçük harf ve alfasayısal olmayan karakterleri yok sayan is_palindrome(text) Python fonksiyonunu yaz.", "python_tests", None, "def is_palindrome(text):\n    return text.lower() == text.lower()[::-1]", "def is_palindrome(text):\n    s = ''.join(c.casefold() for c in text if c.isalnum())\n    return s == s[::-1]", tests=[{"expression": "is_palindrome('Ey Edip Adana’da pide ye')"}, {"expression": "not is_palindrome('yönlendirici')"}], strong_probability=.72, task_type="coding")
    add("tr", "coding", "Listeyi verilen pozitif boyutta ardışık alt listelere bölen chunks(items, size) Python fonksiyonunu yaz; sıfırda ValueError üret.", "python_tests", None, "def chunks(items, size):\n    return [items[i:i+size] for i in range(0, len(items), size)]", "def chunks(items, size):\n    if size <= 0: raise ValueError('size')\n    return [items[i:i+size] for i in range(0, len(items), size)]", tests=[{"expression": "chunks([1,2,3], 2) == [[1,2],[3]]"}, {"expression": "raises(lambda: chunks([1], 0))"}], strong_probability=.81, task_type="coding")
    add("tr", "coding", "Hashlenemeyen listeleri de destekleyerek ilk görülme sırasını koruyan dedupe(items) Python fonksiyonunu yaz.", "python_tests", None, "def dedupe(items):\n    return list(dict.fromkeys(items))", "def dedupe(items):\n    out = []\n    for item in items:\n        if item not in out: out.append(item)\n    return out", tests=[{"expression": "dedupe([[1],[1],[2]]) == [[1],[2]]"}, {"expression": "dedupe([2,1,2]) == [2,1]"}], strong_probability=.88, task_type="coding")
    return rows


def fixture(text: str, index: int, strong: bool) -> dict:
    input_tokens = 44 + index * 2
    output_tokens = max(3, len(text.encode("utf-8")) // 4)
    base_latency = 260 if strong else 115
    return {
        "text": text,
        "usage": {"input_tokens": input_tokens, "cached_input_tokens": 0, "output_tokens": output_tokens},
        "latency_ms": base_latency + (index * 17) % 90,
        "ttft_ms": None,
        "status": "ok",
    }


def main() -> None:
    data = cases()
    # Helper available only to coding tests, injected into candidate source expectation.
    for row in data:
        if row["metric"] == "python_tests" and any("raises(" in t["expression"] for t in row["tests"]):
            prefix = "def raises(fn):\n    try:\n        fn()\n    except ValueError:\n        return True\n    return False\n\n"
            for role in ("cheap", "strong"):
                row["fixture"][role]["text"] = prefix + row["fixture"][role]["text"]
    output = ROOT / "data" / "demo_pilot.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data), encoding="utf-8")
    print(f"wrote {len(data)} synthetic demo tasks to {output}")


if __name__ == "__main__":
    main()
