import sqlite3
from pathlib import Path

def initdb():

    db_dir = Path(__file__).resolve().parent
    db_path = db_dir / "accounting.db"
    schema_path = db_dir / "schema.sql"

    conn = sqlite3.connect(db_path)

    with schema_path.open("r") as file:
        conn.executescript(file.read())

    conn.commit()
    conn.close()

    print(f"Database initialized: {db_path}")

if __name__ == "__main__":
    initdb()
