# 🚀 ZeroG-Sandbox

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-6366f1?style=flat-square&logo=python)](https://python.org)
[![Zero External Dependencies](https://img.shields.io/badge/Dependencies-Standard%20Library%20Only-10b981?style=flat-square)](#)
[![ZeroG CI](https://img.shields.io/badge/ZeroG-Verified-blue?style=flat-square&logo=github)](https://github.com)

> **"Test Before You Commit. Measure Before You Merge."**

**ZeroG-Sandbox**, kod değişiklikleri henüz ana çalışma alanına ve `git` geçmişine uygulanmadan önce onları tamamen izole geçici çalışma alanlarında (sandbox) çalıştıran, alternatif çözüm varyasyonlarını yan yana kıyaslayıp **Etki Ağırlığı (Blast-Radius / Gravity Score)** üreten ve en hafif, en güvenilir çözümü GitHub PR akışına aktaran otonom simülasyon ve karar motorudur.

---

## ⚡ Quickstart (30 Saniyede Çalıştır)

Hiçbir harici kütüphane kurulumu gerekmez (Sadece Python 3.9+ yeterlidir).

### Seçenek 1: Tek Tıkla Demo Başlatıcı

**Windows:**
```cmd
demo.bat
```

**macOS / Linux:**
```bash
chmod +x demo.sh
./demo.sh
```
> Otomatik olarak `http://127.0.0.1:8484` adresinde yerel Web UI açılır!

---

### Seçenek 2: CLI ile Standart Kurulum (`pip install -e .`)

```bash
# 1. Depoyu klonlayın ve içine girin
git clone https://github.com/<your-username>/zerog-sandbox.git
cd zerog-sandbox

# 2. Paketi düzenlenebilir (editable) modda yükleyin
pip install -e .

# 3. Örnek depoyu karşılaştırın veya Web UI'ı başlatın
zerog compare --repo examples/sample_repo
zerog ui --repo examples/sample_repo
```

*(Not: Dilerseniz kurulum yapmadan doğrudan `python -m zerog_sandbox.cli` veya Windows'ta `py -m zerog_sandbox.cli` şeklinde de kullanabilirsiniz.)*

---

## 🌟 Örnek Simülasyon Çıktısı

Örnek repo (`examples/sample_repo`) üzerinde 3 farklı adayı kıyasladığınızda:

```bash
zerog compare --repo examples/sample_repo
```

```text
====================================================================================
                ZEROG-SANDBOX | BLAST-RADIUS IMPACT COMPARISON              
====================================================================================
Variation          | Score    | Badge    | Delta Lines    | Tests        | Crit? 
------------------------------------------------------------------------------------
variation_A_light  | 10.6     | Light    | +1 / -1        | PASSED       | SAFE   [★ RECOMMENDED]
variation_B_medium_critical | 41.8     | Medium   | +4 / -3        | PASSED       | YES   
variation_C_heavy_broken | 108.2    | Heavy    | +6 / -23       | FAILED       | YES   
====================================================================================

[NOTE] 1 variation(s) broke existing tests and were penalized.
```

- **variation_A_light:** En az satır değiştiren, testleri geçiren, kritik modüllere dokunmayan güvenli çözüm.
- **variation_B_medium_critical:** Testleri geçirse de kritik `auth.py` modülüne temas ettiği için orta riskli.
- **variation_C_heavy_broken:** Testleri kırdığı ve geriye dönük uyumsuzluk ürettiği için ağır ceza alan ve elenen varyasyon.

---

## 💻 CLI Kullanım Kılavuzu

Hem `zerog <komut>` hem de `python -m zerog_sandbox.cli <komut>` desteklenir:

| Komut | Açıklama | Örnek |
|---|---|---|
| `compare` | Tüm aday varyasyonları izole sandboxta çalıştırıp skor tablosunu gösterir | `zerog compare --repo .` |
| `simulate` | Belirli bir varyasyon/patch'i test eder. Eşik (`--threshold`) aşılırsa CI'da hata kodu fırlatır | `zerog simulate --repo . --target ./candidates/var1 --threshold 30` |
| `land` | En düşük etki skoruna sahip varyasyonu yeni bir git branch'ine uygular, commit'ler ve PR oluşturur | `zerog land --repo . --variation variation_A_light --pr` |
| `ui` | Tarayıcıda modern koyu temalı yerel dashboard açar | `zerog ui --repo . --port 8484` |
| `init-config` | Projenize varsayılan `zerog.json` dosyasını ekler | `zerog init-config --repo .` |

---

## 🛠️ Kendi Projenize Nasıl Entegre Edersiniz?

ZeroG'yi herhangi bir Python veya çok dilli projede kullanmak son derece kolaydır:

### Adım 1: Konfigürasyon Dosyasını Başlatın
Kendi projenizin kök dizininde şu komutu çalıştırın:
```bash
zerog init-config --repo .
```
Oluşan `zerog.json` dosyasını kendi test komutunuza ve kritik modüllerinize göre özelleştirin:
```json
{
  "project_name": "My-Awesome-App",
  "test_command": "pytest -q",
  "timeout_seconds": 30,
  "critical_files": [
    "auth.py",
    "database.py",
    "payments.py"
  ]
}
```

### Adım 2: Alternatif Adaylarınızı Hazırlayın
Proje kökünde `candidates/` (veya `variations/`, `patches/`) adında bir klasör oluşturun:
```
my_project/
├── candidates/
│   ├── solution_fast/          # Klasör formatında varyasyon (içinde değişen dosyalar)
│   ├── solution_refactor/      # Farklı bir yaklaşım klasörü
│   └── fix_issue.patch         # Unified diff patch formatı (.patch / .diff)
├── src/
└── zerog.json
```

### Adım 3: Kıyaslayın ve Güvenle Land Edin
```bash
# Skorları karşılaştırın
zerog compare --repo .

# Arayüzde inceleyin
zerog ui --repo .

# En iyi varyasyonu doğrudan branch'e aktarın
zerog land --repo .
```

---

## 🧮 Blast-Radius Skoru Nasıl Hesaplanır?

$$\text{Blast-Radius} = P_{\text{files}} + P_{\text{lines}} + P_{\text{critical}} + P_{\text{centrality}} + P_{\text{tests}} + P_{\text{time}} - B_{\text{coverage}}$$

1. **Dosya & Satır Hacmi:** Değişen dosya ve satır sayısı arttıkça skor yükselir.
2. **Kritik Dosya Teması:** Güvenlik/çekirdek olarak işaretlenmiş dosyalara (`critical_files`) dokunan varyasyonlar risk primi alır ($+25.0$).
3. **AST Bağımlılık Haritası:** Python AST çözümleyicisiyle diğer modüllerin bu modüle bağımlılığı ölçülür ($+6.0 \times \text{in-degree}$).
4. **Test Başarısızlığı Cezası:** Test kıran varyasyonlar $+50.0$ ile $+100.0$ arasında ağır ceza alır ve asla tavsiye edilmez.
5. **Etiketleme:**
   - **Light (Hafif):** Skor $\le 20.0$ ve kırılan test yok.
   - **Medium (Orta):** Skor $\le 50.0$ ve kırılan test yok.
   - **Heavy (Ağır):** Skor $> 50.0$ veya kırılan test var.

---

## 🛡️ Güvenlik ve İzolasyon

- **Sıfır Çalışma Alanı Kirliliği:** Kodlar ana deponuzda değil, `tempfile.mkdtemp` ile işletim sisteminin geçici belleğinde çalıştırılır.
- **Bytecode İzolasyonu:** `PYTHONDONTWRITEBYTECODE=1` ile `__pycache__` kirliliği önlenir.
- **Git Stash & Return Garantisi:** `land` işlemi sırasında uncommitted değişiklikler korunur ve branch oluşturulduktan sonra çalışma alanınız otomatik olarak ana dala geri döndürülür.

---

## 🧪 Testleri Çalıştırma

```bash
# Standart kütüphane test koşucusuyla:
python -m unittest discover -s tests -p "test_*.py"

# veya:
py tests/test_zerog.py
```

---

## 📄 Lisans ve Telif Hakkı

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.  
Copyright (c) 2026 **VASCO**. Tüm hakları saklıdır.
