import sqlite3
conn = sqlite3.connect(r'E:\naxuye-agent\naxuye_memory.db')

# 删除噪音数据，只保留 id 1, 2, 21
keep_ids = (1, 2, 21)
conn.execute(f"DELETE FROM error_patterns WHERE id NOT IN {keep_ids}")
conn.commit()

rows = conn.execute('SELECT id, level, count, pattern_type, pattern_detail FROM error_patterns').fetchall()
for r in rows:
    print(r)
conn.close()
print("清理完成")