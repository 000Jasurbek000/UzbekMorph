# Django Morfologik Annotatsiya Tizimi

Morfologik annotatsiya qilish uchun Django asosida qurilgan web tizim.

## Xususiyatlar

### Admin uchun
- 📤 **Token va suffix fayllarini yuklash** (CSV/TSV format)
- 🔧 **Dataset yaratish va boshqarish**
- 📊 **Barcha foydalanuvchilar statistikasi**
- 👥 **Assignment rejimini tanlash** (Umumiy yoki Individual)
- 🔍 **Har bir tokenning barcha annotation'larini ko'rish**
- ✏️ **Annotation'larni tahrirlash va o'chirish**
- 💾 **CSV va JSONL formatda eksport**

### Testlovchilar uchun
- ✍️ **Token annotatsiya qilish**
- 📋 **O'z tokenlarini ko'rish va tahrirlash**
- 📈 **Shaxsiy statistika**
- 🔄 **Jarayonni qaytadan boshlash**
- 💾 **O'z natijalarini eksport qilish**

### Umumiy
- 🎨 **My.gov.uz uslubida zamonaviy dizayn**
- 🔐 **Xavfsiz autentifikatsiya**
- 📱 **Responsive dizayn**
- ⚡ **Tez va qulay interfeys**

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

## Token formati

Token fayli (CSV yoki TSV):
```
kitob
uylar
bolalar
```

Suffix fayli (CSV yoki TSV):
```
lar
ning
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
