
import sqlite3

# Connect to the SQLite database
conn = sqlite3.connect("database/neurotrack.db")

# Required database tables
tables = [
    "users",
    "assessments",
    "assessment_responses",
    "predictions"
]

# Display table columns
for table in tables:
    print("\nTable:", table)

    columns = conn.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    for column in columns:
        print(column)

conn.close()

print("\nDatabase verification completed!")