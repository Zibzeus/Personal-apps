# Deploy ke PythonAnywhere Free

Panduan ini untuk web dashboard online saja. Telegram bot tidak jalan 24 jam di PythonAnywhere Free.

## 1. Upload Code

Cara paling rapi adalah push project ini ke GitHub private repo, lalu clone di PythonAnywhere Bash console:

```bash
git clone https://github.com/YOUR_USERNAME/money-manager.git ~/money-manager
cd ~/money-manager
```

Kalau tidak pakai GitHub, upload ZIP dari tab Files lalu extract ke `~/money-manager`.

## 2. Buat Virtualenv Hemat Storage

```bash
cd ~/money-manager
python3.13 -m venv ~/.virtualenvs/money-manager
source ~/.virtualenvs/money-manager/bin/activate
pip install --no-cache-dir -r requirements.txt
```

Kalau Python 3.13 tidak tersedia di akun kamu, pilih versi Python terbaru yang tersedia di PythonAnywhere Web tab dan gunakan versi yang sama untuk virtualenv.

## 3. Buat `.env`

```bash
cp deploy/pythonanywhere.env.example .env
nano .env
```

Ganti:

```env
DJANGO_SECRET_KEY=secret-panjang-random
DJANGO_ALLOWED_HOSTS=YOUR_USERNAME.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://YOUR_USERNAME.pythonanywhere.com
```

Generate secret yang layak:

```bash
python - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
```

## 4. Setup Database, User Login, Static Files

```bash
source ~/.virtualenvs/money-manager/bin/activate
cd ~/money-manager
python manage.py migrate
python manage.py seed_defaults
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

User yang dibuat dengan `createsuperuser` dipakai untuk login dashboard.

## 5. Buat Web App di PythonAnywhere

Di PythonAnywhere:

1. Buka tab **Web**.
2. Add a new web app.
3. Pilih **Manual configuration**, bukan Django wizard.
4. Pilih versi Python yang sama dengan virtualenv.
5. Set **Virtualenv** ke:

```text
/home/YOUR_USERNAME/.virtualenvs/money-manager
```

6. Set **Source code** dan **Working directory** ke:

```text
/home/YOUR_USERNAME/money-manager
```

## 6. Edit WSGI File

Di Web tab, klik WSGI file. Replace isinya dengan isi:

```text
deploy/pythonanywhere_wsgi.py
```

Jangan lupa ganti `YOUR_USERNAME`.

## 7. Static Files Mapping

Di Web tab, bagian **Static files**, tambahkan:

```text
URL:       /static/
Directory: /home/YOUR_USERNAME/money-manager/staticfiles
```

Klik **Reload** di Web tab.

## 8. Test

Buka:

```text
https://YOUR_USERNAME.pythonanywhere.com
```

Harus diarahkan ke halaman login. Setelah login, dashboard akan tampil.

## Notes

- Jangan simpan banyak backup SQLite di PythonAnywhere Free karena storage 512MB terbatas.
- Untuk backup, pakai tombol Backup DB lalu download file ke laptop.
- Kurs checker memakai `https://open.er-api.com/v6/latest/{currency}` dan menyimpan hasil cek ke SQLite untuk audit/forecasting.
- Setelah update CSS/JS, jalankan `python manage.py collectstatic --noinput` dan reload web app.
- Kalau error, cek **Error log** di Web tab PythonAnywhere.
