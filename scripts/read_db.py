import sqlite3

conn = sqlite3.connect('data.db')
c = conn.cursor()

# Get all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("=" * 80)
print("TABLES IN DATABASE:")
print("=" * 80)
for table in tables:
    print(f"\n{table[0]}")
    c.execute(f"PRAGMA table_info({table[0]})")
    columns = c.fetchall()
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")

# Display data from each table
for table in tables:
    table_name = table[0]
    print(f"\n{'=' * 80}")
    print(f"DATA FROM {table_name.upper()}:")
    print(f"{'=' * 80}")
    c.execute(f"SELECT * FROM {table_name}")
    rows = c.fetchall()
    
    # Get column names
    c.execute(f"PRAGMA table_info({table_name})")
    column_names = [col[1] for col in c.fetchall()]
    
    print(f"Columns: {', '.join(column_names)}")
    print(f"Total rows: {len(rows)}")
    
    for i, row in enumerate(rows[:20], 1):  # Show first 20 rows
        print(f"\nRow {i}:")
        for col_name, val in zip(column_names, row):
            print(f"  {col_name}: {val}")
    
    if len(rows) > 20:
        print(f"\n... and {len(rows) - 20} more rows")

conn.close()
