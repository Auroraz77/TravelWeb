import pandas as pd
import numpy as np
import os

# 读取数据
file_path = os.path.join(os.path.dirname(__file__), '..', 'data', '旅游景点.xlsx')
df = pd.read_excel(file_path)

print(f"原始数据形状: {df.shape}")
print(f"原始数据前5行:\n{df.head()}")

# 统计各列空值
print("\n=== 各列空值统计 ===")
null_counts = df.isnull().sum()
print(null_counts)

# 用"未知"填充所有缺失值
df = df.fillna('未知')

# 去除省/市/区为数字的无效行（只保留包含·的有效地址）
df_cleaned = df[df['省/市/区'].astype(str).str.contains('·', na=False)].copy()

# 去除价格不是数字的无效行
def is_valid_price(x):
    try:
        float(x)
        return True
    except (ValueError, TypeError):
        return False

original_count = len(df_cleaned)
df_cleaned = df_cleaned[df_cleaned['价格'].apply(is_valid_price)]
print(f"清除价格异常数据: {original_count - len(df_cleaned)} 行")

# 去除销量为0的行
df_cleaned = df_cleaned[df_cleaned['销量'] != 0]

# 新增 today_sales 列，赋予 50~200 的随机初始整数值
np.random.seed(42)
df_cleaned['today_sales'] = np.random.randint(50, 201, size=len(df_cleaned))

print(f"\n清洗后数据形状: {df_cleaned.shape}")
print(f"清洗后数据前5行:\n{df_cleaned.head()}")

# 保存清洗后的数据
output_path = os.path.join(os.path.dirname(__file__), '..', 'data', '旅游景点_清洗后.xlsx')
df_cleaned.to_excel(output_path, index=False)
print(f"\n清洗后的数据已保存到: {output_path}")
