import psycopg2

# Baza ma'lumotlari
db_params = {
    "dbname": "data",
    "user": "postgres",
    "password": "12345678",
    "host": "localhost",
    "port": "5432"
}

conn = None  # Xatolik bo'lsa finally qismida muammo bo'lmasligi uchun

try:
    print("Bazaga ulanilmoqda...")
    conn = psycopg2.connect(**db_params)
    cursor = conn.cursor()

    print("SQL fayli o'qilmoqda...")
    # 'utf-8' encoding Windowsda ba'zan 'cp1251' yoki 'latin-1' bo'lishi mumkin
    # Agar xato bersa, encodingni o'zgartirib ko'ring
    with open('database.sql', 'r', encoding='utf-8') as f:
        full_sql = f.read()

    print("Ma'lumotlar tiklanmoqda (bu biroz vaqt olishi mumkin)...")
    cursor.execute(full_sql)

    conn.commit()
    print("Tabriklaymiz! Barcha ma'lumotlar muvaffaqiyatli tiklandi.")

except Exception as e:
    print(f"Xatolik yuz berdi: {e}")
    if conn:
        conn.rollback()
finally:
    if conn:
        cursor.close()
        conn.close()