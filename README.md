Modul KRS Sederhana (Python)

Deskripsi singkat:
Program ini adalah implementasi sederhana modul KRS (Kartu Rencana Studi) berupa CLI untuk menambah mahasiswa, menambah mata kuliah, mendaftarkan mahasiswa ke mata kuliah, membatalkan pendaftaran, melihat KRS mahasiswa, melihat daftar mahasiswa pada mata kuliah, serta menyimpan/memuat data ke file JSON.

Cara menjalankan (Windows PowerShell):

1. Pastikan Anda memiliki Python 3 terpasang (>=3.7).
2. Buka PowerShell dan pindah ke folder proyek, misalnya:

```powershell
cd "d:\KULIAH\Semester 3\Pemrograman Berorientasi Objek untuk Sistem AI Agenik\Tugas\KRS"
```

3. Jalankan program:

```powershell
python krs.py
```

4. Ikuti menu interaktif.

Data tersimpan ke file `krs_data.json` di folder yang sama saat Anda memilih menyimpan atau keluar.

Catatan:
- Program ini dibuat sederhana untuk keperluan tugas: tidak ada autentikasi, tidak ada validasi rumit, dan penyimpanan hanya via JSON.
- Jika Anda mau, saya bisa bantu menambahkan fitur ekspor CSV, batas maksimal SKS, atau antarmuka GUI/Flask.
