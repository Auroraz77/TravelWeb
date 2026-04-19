import sqlite3
import pandas as pd
import os

def init_db():
    """从 Excel 导入数据到 SQLite"""
    # 获取项目根目录（backend/ 的上一级）
    project_root = os.path.dirname(os.path.dirname(__file__))
    db_path = os.path.join(os.path.dirname(__file__), 'tourism.db')
    excel_path = os.path.join(project_root, 'data', '旅游景点_清洗后.xlsx')

    conn = sqlite3.connect(db_path)
    df = pd.read_excel(excel_path)

    # 处理城市提取（省/市/区 -> 城市，省/市/区格式如 "北京·朝阳区"）
    def extract_city(x):
        if '·' in str(x):
            parts = str(x).split('·')
            return parts[0] if len(parts) > 1 else parts[0]
        return str(x)

    df['城市'] = df['省/市/区'].apply(extract_city)
    df.to_sql('attractions', conn, if_exists='replace', index=False)
    conn.close()
    print(f"数据库初始化完成: {db_path}")
    print(f"数据来源: {excel_path}")

if __name__ == "__main__":
    init_db()
