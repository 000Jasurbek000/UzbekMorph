# Django Morfologik Annotatsiya Tizimi

O'zbek tili uchun to'liq morfologik tahlil va annotatsiya tizimi. PREFIX, ROOT va barcha SUFFIX kategoriyalarini qo'llab-quvvatlaydi.

## Xususiyatlar

### Morfologik tahlil imkoniyatlari
- 🔤 **PREFIX** (Prefikslar): ba-, be-, no-, ser-, xush-, g'ayri-, ham-, alla-, hech-, har-
- 🌿 **ROOT** (O'zak/Ildiz): So'zning asosiy qismi
- 📊 **INFLECTION** (Ko'plik): -lar, -ler
- 👤 **POSSESSIVE** (Egalik): -m, -ng, -si, -miz, -ngiz, -lari, -im, -ing, -imiz, -ingiz, -i
- 📍 **CASE** (Kelishik): -ni, -ning, -ga, -ka, -qa, -da, -ta, -dan, -tan, -gacha, -dek, -day, -niki, -dagi, -tagi, -dagina
- 🔨 **DERIVATIONAL** (Yasovchi): -chi, -lik, -kor, -gar, -li, -siz, -dor, -mand, va boshqalar (42 ta variant)
- 💝 **DIMINUTIVE** (Kichraytirish): -cha, -choq, -chak, -kay, -gina, -kina, -qina, -jon, -oy, -bek, -boy
- ⚡ **VERB** (Fe'l): -moq, -ish, -la, -lan, -lash, -lashtir, -tir, -dir, -ir, -ar

### Misol tahlillar
```
maktablarimizdan → maktab + lar + imiz + dan
                   ROOT + INFLECTION + POSSESSIVE + CASE

tilshunoslik → til + shunos + lik
              ROOT + DERIVATIONAL + DERIVATIONAL

qizaloqlarimizga → qiz + aloq + lar + imiz + ga
                  ROOT + DIMINUTIVE + INFLECTION + POSSESSIVE + CASE

befarqlik → be + farq + lik
           PREFIX + ROOT + DERIVATIONAL
```

### Admin uchun
- 📤 **TSV lexicon fayli yuklash** (103+ affix bilan)
- 🔧 **Dataset yaratish va boshqarish**
- 📊 **Barcha foydalanuvchilar statistikasi**
- 👥 **Assignment rejimini tanlash** (Umumiy yoki Individual)
- 🔍 **Har bir tokenning barcha annotation'larini ko'rish**
- ✏️ **Annotation'larni tahrirlash va o'chirish**
- 💾 **CSV va JSONL formatda eksport**

### Testlovchilar uchun
- ✍️ **To'liq morfologik annotatsiya**
- 📋 **O'z tokenlarini ko'rish va tahrirlash**
- 📈 **Shaxsiy statistika**
- 🔄 **Jarayonni qaytadan boshlash**
- 💾 **O'z natijalarini eksport qilish**

### Umumiy
- 🎨 **My.gov.uz uslubida zamonaviy dizayn**
- 🔐 **Xavfsiz autentifikatsiya**
- 📱 **Responsive dizayn**
- ⚡ **Tez va qulay interfeys**
- 🔍 **Filtrlar** (Holat va Status bo'yicha)

## O'rnatish

### 1. Repositoriyani klonlash
```bash
git clone <repository-url>
cd django_morph_site
```

### 2. Virtual muhit yaratish
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

### 3. Bog'liqliklarni o'rnatish
```bash
pip install -r requirements.txt
```

### 4. Ma'lumotlar bazasini yaratish
```bash
python manage.py migrate
```

### 5. Superuser yaratish
```bash
python manage.py createsuperuser
```

### 6. Serverni ishga tushirish
```bash
python manage.py runserver 8001
```

Brauzerda `http://127.0.0.1:8001` manzilini oching.

## Foydalanish

### Admin uchun

1. **Admin panel**ga kiring (admin hisobi bilan)
2. **Dataset yaratish**:
   - Token fayli (CSV/TSV) yuklang
   - Suffix fayli (CSV/TSV) yuklang
   - Assignment rejimini tanlang (Umumiy/Individual)
3. **Dataset aktivlashtirish**: Kerakli datasetni aktivlashtiring
4. **Assignment yaratish**: "Assignment yaratish" tugmasini bosing
5. **Token ko'rish**: "📋 Tokenlar" sahifasidan barcha tokenlarni ko'ring
6. **Tahrirlash**: Har bir token uchun annotation'larni ko'rish va tahrirlash

### Testlovchi uchun

1. **Profil**: Statistika va progress ko'rish
2. **Testlash**: Token annotatsiya qilish
3. **Tokenlar**: O'z tokenlarini ko'rish va tahrirlash
4. **Statistika**: Shaxsiy natijalar va eksport
5. **Qaytadan boshlash**: Jarayonni boshidan boshlash

## Token va Lexicon formatlari

### Token fayli (CSV yoki TSV):
```
word
kitob
uylar
bolalar
maktablarimizdan
tilshunoslik
```

### Suffix Lexicon fayli (TSV - TAB bilan ajratilgan):
```
affix	type	category	pos_from	pos_to	code	description
ba	PREFIX	DERIVATIONAL	NOUN	ADJ	PX001	adjective forming prefix
lar	SUFFIX	INFLECTION	NOUN	NOUN	SF001	plural
im	SUFFIX	POSSESSIVE	NOUN	NOUN	SF016	first person singular alt
ni	SUFFIX	CASE	NOUN	NOUN	SF030	accusative
chi	SUFFIX	DERIVATIONAL	NOUN	NOUN	SF100	agent
cha	SUFFIX	DIMINUTIVE	NOUN	NOUN	SF300	diminutive
moq	SUFFIX	VERB	VERB	VERB	SF408	infinitive
```

**Ustunlar:**
- `affix` - morfema (ba, lar, ni va h.k.)
- `type` - PREFIX yoki SUFFIX
- `category` - INFLECTION, POSSESSIVE, CASE, DERIVATIONAL, DIMINUTIVE, VERB
- `pos_from` - boshlang'ich so'z turkumi
- `pos_to` - oxirgi so'z turkumi  
- `code` - kod (PXxxx yoki SFxxx)
- `description` - tavsif

To'liq lexicon fayli `suffix_lexicon.tsv` da (103 ta morfema)
ga
```

## Funksiyalar

### Cascade Delete
- Assignment o'chirilganda unga bog'langan barcha annotation'lar ham o'chadi
- Dataset o'chirilganda barcha assignment va annotation'lar o'chadi

### Annotation History
- Har bir tokenning barcha annotation'lari saqlanadi
- CSV va JSONL formatda eksport qilinadi
- Admin va foydalanuvchilar annotation'larni tahrirlashi mumkin

### Progress Tracking
- Avtomatik progress saqlanadi
- Foydalanuvchilar qaytadan boshlashi mumkin
- Har bir tokenning holati ko'rinadi

## Texnologiyalar

- **Backend**: Django 6.0.3
- **Database**: SQLite
- **Frontend**: HTML, CSS, JavaScript (Vanilla)
- **Dizayn**: My.gov.uz uslubida

## Struktura

```
django_morph_site/
├── annotator/           # Asosiy app
│   ├── models.py       # Ma'lumotlar modellari
│   ├── views.py        # View'lar
│   ├── urls.py         # URL routing
│   ├── segmenter.py    # Morfologik segmentatsiya
│   ├── services.py     # Yordamchi servislar
│   └── templates/      # HTML shablonlar
├── config/             # Django konfiguratsiya
├── media/              # Yuklangan fayllar
├── output/             # Eksport fayllari
└── requirements.txt    # Python bog'liqliklari
```

## Litsenziya

MIT License

## Muallif

Bakayev - 2026
