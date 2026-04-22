"""
FastAPI 后端服务 - 旅游景点实时排名 + LLM 自然语言查询
使用 DashScope SDK 直接调用
"""

import os
import sqlite3
import asyncio
import random
import re
from contextlib import asynccontextmanager
from datetime import datetime

import pandas as pd
import dashscope
from dashscope import Generation
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 配置 DashScope HTTP 请求地址
dashscope.base_url = "https://dashscope.aliyuncs.com/api/v1"

# 数据文件路径
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', '旅游景点_清洗后.xlsx')
DB_FILE = os.path.join(os.path.dirname(__file__), 'tourism.db')

# 全局变量
df: pd.DataFrame = None
df_lock = asyncio.Lock()

# 通义千问 API 配置
dashscope.api_key = "sk-8edfb88c67a54c6b81aa180693f605e6"

# 导入知识库 RAG 模块
from knowledge_base import retrieve_knowledge
# 导入天气服务模块
from weather_service import get_weather_now, get_weather_forecast, geo_lookup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global df

    # 加载景点数据
    try:
        df = pd.read_excel(DATA_FILE)
        print(f"数据加载成功，共 {len(df)} 条记录")
    except Exception as e:
        print(f"加载数据失败: {e}")

    # 启动后台更新任务
    asyncio.create_task(background_update())

    yield
    print("应用关闭")


async def background_update():
    """后台任务：每 0.2 秒更新景点销量"""
    while True:
        await asyncio.sleep(0.2)
        async with df_lock:
            if df is not None and len(df) >= 20:
                indices = random.sample(list(df.index), 20)
                for idx in indices:
                    df.loc[idx, 'today_sales'] += random.randint(20, 50)


app = FastAPI(title="旅游景点 API", version="1.0.0", lifespan=lifespan)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 已有接口 ============

@app.get("/api/live_ranking")
async def get_live_ranking():
    async with df_lock:
        if df is None:
            return {"success": False, "message": "数据未加载"}
        top10 = df.nlargest(10, 'today_sales')[['名称', 'today_sales']].copy()
        top10['rank'] = range(1, 11)
        result = top10.to_dict(orient='records')
    return {"success": True, "data": result, "timestamp": datetime.now().isoformat()}


@app.get("/api/top_history_sales")
async def get_top_history_sales():
    async with df_lock:
        if df is None:
            return {"success": False, "message": "数据未加载"}
        df['销量'] = pd.to_numeric(df['销量'], errors='coerce')
        sorted_df = df.sort_values('销量', ascending=False).head(10)
        result = []
        for i, (_, row) in enumerate(sorted_df.iterrows()):
            result.append({
                "rank": i + 1,
                "名称": str(row['名称']),
                "销量": float(row['销量']) if pd.notna(row['销量']) else 0
            })
    return {"success": True, "data": result, "timestamp": datetime.now().isoformat()}


@app.get("/api/sales_by_province")
async def get_sales_by_province():
    async with df_lock:
        if df is None:
            return {"success": False, "message": "数据未加载"}
        try:
            df['省份'] = df['省/市/区'].apply(lambda x: str(x).split('·')[0] if '·' in str(x) else str(x))
            province_sales = df.groupby('省份')['销量'].sum().reset_index()
            province_sales.columns = ['name', 'value']
            province_sales['value'] = province_sales['value'].fillna(0).astype(int)
            result = province_sales.to_dict(orient='records')
        except Exception as e:
            return {"success": False, "message": str(e)}
    return {"success": True, "data": result, "timestamp": datetime.now().isoformat()}


@app.get("/api/province_4a5a_count")
async def get_province_4a5a_count():
    async with df_lock:
        if df is None:
            return {"success": False, "message": "数据未加载"}
        try:
            df['省份'] = df['省/市/区'].apply(lambda x: str(x).split('·')[0] if '·' in str(x) else str(x))
            df_filtered = df[df['星级'].astype(str).isin(['4A', '5A'])]
            province_count = df_filtered.groupby('省份').size().reset_index()
            province_count.columns = ['name', 'value']
            result = province_count.to_dict(orient='records')
        except Exception as e:
            return {"success": False, "message": str(e)}
    return {"success": True, "data": result, "timestamp": datetime.now().isoformat()}


@app.get("/api/price_distribution")
async def get_price_distribution():
    async with df_lock:
        if df is None:
            return {"success": False, "message": "数据未加载"}
        try:
            df['价格'] = pd.to_numeric(df['价格'], errors='coerce')
            bins = [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
            labels = ['0-50', '50-100', '100-150', '150-200', '200-250', '250-300', '300-350', '350-400', '400-450', '450-500']
            counts = []
            for i in range(len(bins) - 1):
                count = df[(df['价格'] >= bins[i]) & (df['价格'] < bins[i+1])].shape[0]
                counts.append({
                    'name': labels[i],
                    'value': count,
                    'xAxis': (bins[i] + bins[i+1]) / 2,
                    'yAxis': count
                })
            result = counts
        except Exception as e:
            return {"success": False, "message": str(e)}
    return {"success": True, "data": result, "timestamp": datetime.now().isoformat()}


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


# ============ LLM 查询接口 ============

class QueryRequest(BaseModel):
    question: str
    export: bool = False  # 是否导出CSV


def get_table_info():
    """获取数据库表结构信息"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(attractions)")
    columns = cursor.fetchall()
    conn.close()

    col_info = []
    for col in columns:
        col_name = col[1]
        col_type = col[2]
        if isinstance(col_name, bytes):
            col_name = col_name.decode('utf-8')
        if isinstance(col_type, bytes):
            col_type = col_type.decode('utf-8')
        col_info.append(f"{col_name} ({col_type})")

    return "\n".join(col_info)


def extract_sql(text):
    """从 LLM 回复中提取 SQL 语句"""
    # 尝试匹配 SELECT 语句
    match = re.search(r'(SELECT\s+.+?;)', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # 尝试匹配反引号包裹的 SQL
    match = re.search(r'```sql\s*(SELECT\s+.+?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def find_attraction_coords(attraction_name: str) -> tuple:
    """根据景点名称或地区查找坐标，返回 (坐标, 地点名称)"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 优先搜索景点名称
        cursor.execute(
            "SELECT 坐标, 名称 FROM attractions WHERE 名称 LIKE ? LIMIT 1",
            (f"%{attraction_name}%",)
        )
        result = cursor.fetchone()
        if result and result[0]:
            conn.close()
            return (result[0], result[1])

        # 搜索省/市/区字段
        cursor.execute(
            "SELECT 坐标, 省/市/区 FROM attractions WHERE 省/市/区 LIKE ? LIMIT 1",
            (f"%{attraction_name}%",)
        )
        result = cursor.fetchone()
        if result and result[0]:
            conn.close()
            return (result[0], result[1])

        # 搜索具体地址
        cursor.execute(
            "SELECT 坐标, 具体地址 FROM attractions WHERE 具体地址 LIKE ? LIMIT 1",
            (f"%{attraction_name}%",)
        )
        result = cursor.fetchone()
        if result and result[0]:
            conn.close()
            return (result[0], result[1])

        conn.close()
    except Exception as e:
        print(f"查找坐标失败: {e}")
    return (None, None)


def execute_query(sql):
    """执行 SQL 查询并返回结果"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        conn.close()

        result = []
        for row in rows:
            encoded_row = []
            for item in row:
                if isinstance(item, bytes):
                    item = item.decode('utf-8')
                elif item is None:
                    item = ''
                encoded_row.append(item)
            result.append(dict(zip(columns, encoded_row)))
        return result
    except Exception as e:
        return str(e)


async def query_with_llm(question: str) -> str:
    """使用 LLM + RAG + 天气 进行自然语言查询"""

    # 1. 判断问题类型
    db_keywords = ['景点名称', '哪个景点', '哪里有', '价格', '销量', '评分', '星级', '城市', '多少个', '有几个', '有哪些', '有什么', '景点', '地方']
    knowledge_keywords = ['系统', '功能', '能做什么', '怎么用', '是什么', '介绍', '帮助']
    weather_keywords = ['天气', '气温', '温度', '下雨', '晴天', '阴天', '刮风', '湿度', '风']

    is_db_query = any(k in question for k in db_keywords)
    is_knowledge_query = any(k in question for k in knowledge_keywords)
    is_weather_query = any(k in question for k in weather_keywords)

    # 2. 如果是天气查询
    if is_weather_query:
        # 先尝试用 LLM 提取景点/地区名称
        extract_prompt = f"""从以下问题中提取地名（只输出地名，不要其他内容）：
{question}

只输出一个地名，如"上海"、"北京"、"陕西西安碑林区"。"""

        extract_response = Generation.call(
            model="qwen-turbo",
            prompt=extract_prompt,
            temperature=0
        )

        location_name = "上海"  # 默认
        if extract_response.status_code == 200:
            extracted_name = extract_response.output['text'].strip()
            if extracted_name:
                location_name = extracted_name

        # 用 geo_lookup 获取 Location ID
        geo_result = geo_lookup(location_name)

        if geo_result.get("success"):
            location_id = geo_result.get("id")
            weather = get_weather_now(location_id)
            if weather.get("success"):
                w = weather
                weather_text = f"{geo_result['name']}当前天气：{w['text']}，温度{w['temp']}°C，体感温度{w['feelsLike']}°C，湿度{w['humidity']}%，{w['windDir']}风，风速{w['windSpeed']}km/h。"
                return weather_text
            else:
                return f"抱歉，暂时无法获取{location_name}的天气信息。"
        else:
            return f"抱歉，无法找到{location_name}的位置信息。"

    # 2. 检索相关知识
    retrieved_knowledge = retrieve_knowledge(question)

    # 3. 构建综合 Prompt
    if is_knowledge_query or not is_db_query:
        # 知识库查询
        prompt = f"""你是一个旅游景点智能助手。请根据以下知识回答用户问题。

【相关知识】
{retrieved_knowledge}

【用户问题】
{question}

请根据相关知识回答，如果知识中没有相关信息，请礼貌地说明你只能回答关于景点数据查询和系统功能的问题。"""

        response = Generation.call(
            model="qwen-turbo",
            prompt=prompt,
            temperature=0
        )

        if response.status_code == 200:
            return response.output['text']
        else:
            return f"LLM 调用失败：{response.message}"

    # 4. 数据库查询
    table_info = get_table_info()

    sql_prompt = f"""你是一个景点数据查询助手。数据库中有一张名为 attractions 的表，包含以下字段：
{table_info}

只生成 SELECT 查询，不要做任何修改。
用户问题：{question}

请只输出 SQL 语句，不要其他解释。"""

    sql_response = Generation.call(
        model="qwen-turbo",
        prompt=sql_prompt,
        temperature=0
    )

    if sql_response.status_code != 200:
        return f"LLM 调用失败：{sql_response.message}"

    sql = extract_sql(sql_response.output['text'])
    if not sql:
        return "无法理解您的问题，请尝试换一种表达方式"

    result = execute_query(sql)
    if isinstance(result, str):
        return f"查询出错：{result}"
    if len(result) == 0:
        return "没有找到相关数据"

    # 判断是否为"列出全部"类型的查询
    list_all_keywords = ['有哪些', '有什么', '全部', '所有', '列出', '罗列']
    is_list_all = any(k in question for k in list_all_keywords)

    # 5. 格式化结果
    if is_list_all:
        # 列出全部模式：直接格式化输出，不经过LLM摘要
        if len(result) == 1:
            # 只有一条时直接返回
            item = result[0]
            return '、'.join([f"{k}：{v}" for k, v in item.items()])

        # 多条时列出所有结果
        lines = []
        for i, item in enumerate(result, 1):
            name = item.get('名称', item.get('name', '未知'))
            city = item.get('城市', item.get('city', ''))
            price = item.get('价格', item.get('price', ''))
            lines.append(f"{i}. {name}" + (f"（{city}）" if city else "") + (f" - ¥{price}" if price else ""))

        total = f"共找到 {len(result)} 个结果：\n"
        return total + '\n'.join(lines)
    else:
        # 摘要模式
        format_prompt = f"""用户问题：{question}
SQL查询结果：{str(result[:100])}

请用简洁的自然语言总结这些数据。
【重要】如果查询结果有多条，请务必全部列出，不要遗漏。"""

        format_response = Generation.call(
            model="qwen-turbo",
            prompt=format_prompt,
            temperature=0
        )

        if format_response.status_code == 200:
            return format_response.output['text']
        else:
            return str(result[:20])


def format_csv(result):
    """将查询结果转换为CSV格式"""
    if not result:
        return ""

    def escape_csv_value(value):
        """CSV字段转义：如果包含逗号、引号或换行，则加引号"""
        s = str(value)
        if ',' in s or '"' in s or '\n' in s:
            s = '"' + s.replace('"', '""') + '"'
        return s

    columns = list(result[0].keys())
    lines = [','.join(escape_csv_value(col) for col in columns)]
    for row in result:
        lines.append(','.join(escape_csv_value(row.get(col, '')) for col in columns))
    return '\n'.join(lines)


@app.post("/api/query")
async def query(request: QueryRequest):
    """自然语言查询接口"""
    try:
        result = await query_with_llm(request.question)

        if request.export and isinstance(result, str) and not result.startswith("查询出错"):
            # 导出模式：重新生成SQL并执行获取完整数据
            table_info = get_table_info()
            sql_prompt = f"""你是一个景点数据查询助手。数据库中有一张名为 attractions 的表，包含以下字段：
{table_info}

只生成 SELECT 查询，不要做任何修改。
用户问题：{request.question}

请只输出 SQL 语句，不要其他解释。"""

            sql_response = Generation.call(
                model="qwen-turbo",
                prompt=sql_prompt,
                temperature=0
            )

            if sql_response.status_code == 200:
                sql = extract_sql(sql_response.output['text'])
                if sql:
                    data = execute_query(sql)
                    csv_data = format_csv(data)
                    return {
                        "success": True,
                        "result": f"导出成功，共 {len(data)} 条数据",
                        "csv": csv_data,
                        "timestamp": datetime.now().isoformat()
                    }

        return {"success": True, "result": result, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/weather")
async def weather(city: str = "上海"):
    """天气查询接口"""
    result = get_weather_now(city)
    return result


@app.get("/api/weather/forecast")
async def weather_forecast(city: str = "上海", days: int = 3):
    """天气预报接口"""
    result = get_weather_forecast(city, days)
    return result


@app.get("/api/random_attraction")
async def random_attraction():
    """获取随机景点简介"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        # 随机获取一个有简介的景点
        cursor.execute(
            "SELECT 名称, 简介, 城市 FROM attractions WHERE 简介 IS NOT NULL AND 简介 != '未知' AND 简介 != '' ORDER BY RANDOM() LIMIT 1"
        )
        result = cursor.fetchone()
        conn.close()
        if result:
            return {
                "success": True,
                "data": {
                    "name": result[0],
                    "description": result[1],
                    "city": result[2]
                }
            }
        else:
            return {"success": False, "error": "没有找到景点简介"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
