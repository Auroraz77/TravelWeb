"""
FastAPI 后端服务 - 旅游景点实时排名 + LLM 自然语言查询
使用 DashScope SDK 直接调用
"""

import os
import sqlite3
import asyncio
import random
import re
import time
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pandas as pd
import dashscope
from dashscope import Generation
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import bcrypt
from jose import jwt, JWTError

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

# JWT 配置
SECRET_KEY = "cb2e6aae58f8aeeeed1c6836371ec81927edd1b780516ea5c4c9f6da02eec10b"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 86400  # 24小时

def hash_password(password: str) -> str:
    """对密码进行 bcrypt 哈希"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """验证密码与哈希是否匹配"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# 认证方案
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

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

    # 创建用户表
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("用户表初始化完成")

    # 创建行程计划表
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trip_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            trip_date TEXT NOT NULL,
            time TEXT DEFAULT '',
            note TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    # 创建账单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            bill_date TEXT NOT NULL,
            icon TEXT DEFAULT 'wallet',
            color TEXT DEFAULT '#1976d2',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()
    print("行程计划表和账单表初始化完成")

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


@app.get("/api/attractions")
async def get_attractions(keyword: str = "", city: str = "", star: str = "", page: int = 1, page_size: int = 10):
    """景点门票列表（支持搜索、筛选、分页）"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 构建查询条件
        conditions = []
        params = []

        if keyword:
            conditions.append("(名称 LIKE ? OR 城市 LIKE ? OR 简介 LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        if city:
            conditions.append("城市 LIKE ?")
            params.append(f"%{city}%")
        if star:
            conditions.append("星级 = ?")
            params.append(star)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 查询总数
        cursor.execute(f"SELECT COUNT(*) FROM attractions WHERE {where_clause}", params)
        total = cursor.fetchone()[0]

        # 分页查询
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        cursor.execute(
            f"SELECT 名称, 城市, [省/市/区], 星级, 评分, 价格, 销量, 简介, 具体地址 FROM attractions WHERE {where_clause} ORDER BY 销量 DESC LIMIT ? OFFSET ?",
            params + [page_size, offset]
        )
        rows = cursor.fetchall()
        conn.close()

        data = []
        for row in rows:
            data.append({
                "name": row[0],
                "city": row[1],
                "province": row[2] if len(row) > 2 else "",
                "star": row[3] if len(row) > 3 else "",
                "rating": row[4] if len(row) > 4 else 0,
                "price": row[5] if len(row) > 5 else 0,
                "sales": row[6] if len(row) > 6 else 0,
                "description": row[7] if len(row) > 7 else "",
                "address": row[8] if len(row) > 8 else "",
            })

        return {
            "success": True,
            "data": data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
            }
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/cities")
async def get_cities():
    """获取所有城市列表"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT 城市 FROM attractions ORDER BY 城市")
        cities = [row[0] for row in cursor.fetchall()]
        conn.close()
        return {"success": True, "data": cities}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ============ 用户认证接口 ============

class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

def create_access_token(data: dict) -> str:
    """创建 JWT token"""
    to_encode = data.copy()
    to_encode["exp"] = time.time() + ACCESS_TOKEN_EXPIRE_SECONDS
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """从 JWT token 中解析当前用户"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        username = payload.get("username")
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效的认证凭据")
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="认证已过期")
        return {"id": int(user_id), "username": username}
    except JWTError as e:
        print(f"[AUTH] JWT 验证失败: {e}")
        raise HTTPException(status_code=401, detail="无效的认证凭据")

async def get_optional_current_user(credentials: HTTPAuthorizationCredentials = Depends(optional_security)) -> dict | None:
    """尽量从 JWT token 中解析当前用户，未登录或 token 无效时返回 None。"""
    if credentials is None:
        return None
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        username = payload.get("username")
        if user_id is None or payload.get("exp", 0) < time.time():
            return None
        return {"id": int(user_id), "username": username}
    except JWTError as e:
        print(f"[AUTH] 可选 JWT 验证失败: {e}")
        return None

@app.post("/api/register")
async def register(req: RegisterRequest):
    """用户注册"""
    username = req.username.strip()
    password = req.password

    # 参数校验
    if not (3 <= len(username) <= 20):
        return {"success": False, "message": "用户名长度应为 3-20 个字符"}
    if len(password) < 6:
        return {"success": False, "message": "密码长度不能少于 6 个字符"}

    password_hash = hash_password(password)

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )
        conn.commit()
        conn.close()
        return {"success": True, "message": "注册成功"}
    except sqlite3.IntegrityError:
        return {"success": False, "message": "用户名已存在"}
    except Exception as e:
        return {"success": False, "message": f"注册失败: {str(e)}"}

@app.post("/api/login")
async def login(req: LoginRequest):
    """用户登录"""
    username = req.username.strip()
    password = req.password

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return {"success": False, "message": "用户名或密码错误"}

    user_id, db_username, password_hash = user
    if not verify_password(password, password_hash):
        return {"success": False, "message": "用户名或密码错误"}

    token = create_access_token({"sub": str(user_id), "username": db_username})
    return {
        "success": True,
        "message": "登录成功",
        "token": token,
        "user": {"id": user_id, "username": db_username}
    }

@app.get("/api/user/info")
async def get_user_info(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return {
        "success": True,
        "user": {
            "id": current_user["id"],
            "username": current_user["username"]
        }
    }


# ============ 行程计划接口 ============

class TripPlanCreate(BaseModel):
    name: str
    trip_date: str
    time: str = ''
    note: str = ''
    status: str = 'pending'

class TripPlanUpdate(BaseModel):
    name: str = None
    trip_date: str = None
    time: str = None
    note: str = None
    status: str = None

@app.get("/api/trip-plans")
async def get_trip_plans(current_user: dict = Depends(get_current_user)):
    """获取当前用户所有行程计划"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, trip_date, time, note, status FROM trip_plans WHERE user_id = ? ORDER BY trip_date, time",
        (current_user["id"],)
    )
    rows = cursor.fetchall()
    conn.close()
    data = [{"id": r[0], "name": r[1], "trip_date": r[2], "time": r[3], "note": r[4], "status": r[5]} for r in rows]
    return {"success": True, "data": data}

@app.post("/api/trip-plans")
async def create_trip_plan(req: TripPlanCreate, current_user: dict = Depends(get_current_user)):
    """新增行程计划"""
    if not req.name.strip():
        return {"success": False, "message": "行程名称不能为空"}
    if not req.trip_date.strip():
        return {"success": False, "message": "日期不能为空"}
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO trip_plans (user_id, name, trip_date, time, note, status) VALUES (?, ?, ?, ?, ?, ?)",
        (current_user["id"], req.name.strip(), req.trip_date.strip(), req.time, req.note, req.status)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return {"success": True, "message": "添加成功", "data": {"id": new_id}}

@app.put("/api/trip-plans/{plan_id}")
async def update_trip_plan(plan_id: int, req: TripPlanUpdate, current_user: dict = Depends(get_current_user)):
    """更新行程计划"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM trip_plans WHERE id = ? AND user_id = ?", (plan_id, current_user["id"]))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "message": "行程不存在"}
    fields = []
    params = []
    if req.name is not None:
        fields.append("name = ?")
        params.append(req.name.strip())
    if req.trip_date is not None:
        fields.append("trip_date = ?")
        params.append(req.trip_date.strip())
    if req.time is not None:
        fields.append("time = ?")
        params.append(req.time)
    if req.note is not None:
        fields.append("note = ?")
        params.append(req.note)
    if req.status is not None:
        fields.append("status = ?")
        params.append(req.status)
    if fields:
        params.append(plan_id)
        cursor.execute(f"UPDATE trip_plans SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()
    conn.close()
    return {"success": True, "message": "更新成功"}

@app.delete("/api/trip-plans/{plan_id}")
async def delete_trip_plan(plan_id: int, current_user: dict = Depends(get_current_user)):
    """删除行程计划"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trip_plans WHERE id = ? AND user_id = ?", (plan_id, current_user["id"]))
    conn.commit()
    conn.close()
    return {"success": True, "message": "删除成功"}


# ============ 账单接口 ============

class BillCreate(BaseModel):
    name: str
    category: str
    amount: float
    bill_date: str
    icon: str = 'wallet'
    color: str = '#1976d2'

class BillUpdate(BaseModel):
    name: str = None
    category: str = None
    amount: float = None
    bill_date: str = None

@app.get("/api/bills")
async def get_bills(current_user: dict = Depends(get_current_user)):
    """获取当前用户所有账单"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, category, amount, bill_date, icon, color FROM bills WHERE user_id = ? ORDER BY bill_date DESC, id DESC",
        (current_user["id"],)
    )
    rows = cursor.fetchall()
    conn.close()
    data = [{"id": r[0], "name": r[1], "category": r[2], "amount": r[3], "bill_date": r[4], "icon": r[5], "color": r[6]} for r in rows]
    return {"success": True, "data": data}

@app.post("/api/bills")
async def create_bill(req: BillCreate, current_user: dict = Depends(get_current_user)):
    """新增账单"""
    if not req.name.strip():
        return {"success": False, "message": "账单名称不能为空"}
    if req.amount <= 0:
        return {"success": False, "message": "金额必须大于0"}
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bills (user_id, name, category, amount, bill_date, icon, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (current_user["id"], req.name.strip(), req.category, req.amount, req.bill_date, req.icon, req.color)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return {"success": True, "message": "添加成功", "data": {"id": new_id}}

@app.delete("/api/bills/{bill_id}")
async def delete_bill(bill_id: int, current_user: dict = Depends(get_current_user)):
    """删除账单"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bills WHERE id = ? AND user_id = ?", (bill_id, current_user["id"]))
    conn.commit()
    conn.close()
    return {"success": True, "message": "删除成功"}


# ============ LLM 查询接口 ============

class QueryRequest(BaseModel):
    question: str
    export: bool = False  # 是否导出CSV
    page: int = 1         # 当前页码（从1开始）
    page_size: int = 20   # 每页条数，默认20，最大100


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


RECORD_KEYWORDS = [
    '添加行程', '新增行程', '记录行程', '行程记录', '帮我安排', '安排去', '计划去',
    '记账', '记一笔', '账单', '消费', '花了', '支付', '付款', '支出',
]

BILL_CATEGORIES = {
    '交通': {'icon': 'navigate', 'color': '#42a5f5'},
    '门票': {'icon': 'image', 'color': '#1976d2'},
    '餐饮': {'icon': 'coffee', 'color': '#ff9800'},
    '住宿': {'icon': 'home', 'color': '#7b1fa2'},
    '购物': {'icon': 'gift', 'color': '#e91e63'},
}


def is_record_request(question: str) -> bool:
    """判断用户是否在请求助手记录行程或账单。"""
    if any(keyword in question for keyword in RECORD_KEYWORDS):
        return True
    return bool(re.search(r'(今天|明天|后天|昨天|\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}).{0,20}(去|游览|参观)', question))


def normalize_record_date(value: str | None) -> str:
    """将相对日期转成可展示的日期字符串，无法判断时保留原文。"""
    if not value:
        return datetime.now().strftime("%Y-%m-%d")
    text = str(value).strip()
    today = datetime.now()
    if text in ('今天', '今日'):
        return today.strftime("%Y-%m-%d")
    if text == '明天':
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if text == '后天':
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    if text == '昨天':
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    return text


def infer_bill_category(text: str) -> str:
    """根据名称和上下文推断账单分类。"""
    category_keywords = {
        '交通': ['打车', '公交', '地铁', '高铁', '火车', '机票', '出租车', '车费', '交通'],
        '门票': ['门票', '票', '景区', '入园', '展览', '博物馆'],
        '餐饮': ['饭', '餐', '饮料', '奶茶', '咖啡', '小吃', '早餐', '午餐', '午饭', '晚餐', '晚饭', '早饭'],
        '住宿': ['酒店', '民宿', '住宿', '房费', '宾馆'],
        '购物': ['购物', '纪念品', '特产', '商店'],
    }
    for category, keywords in category_keywords.items():
        if any(keyword in text for keyword in keywords):
            return category
    return '购物'


def extract_json_object(text: str) -> dict | None:
    """从 LLM 回复中提取 JSON 对象。"""
    if not text:
        return None
    cleaned = text.strip()
    fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL | re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        object_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if object_match:
            cleaned = object_match.group(0)
    try:
        return json.loads(cleaned)
    except Exception as e:
        print(f"[RECORD] JSON 解析失败: {e}, raw={text}")
        return None


def fallback_parse_records(question: str) -> dict:
    """LLM 不可用时的简单兜底解析。"""
    parsed = {"trips": [], "bills": []}
    date_match = re.search(r'((?:\d{4}[-年])?\d{1,2}[月/-]\d{1,2}日?|今天|明天|后天|昨天)', question)
    date_text = normalize_record_date(date_match.group(1)) if date_match else datetime.now().strftime("%Y-%m-%d")

    amount_match = re.search(r'(.{0,30}?)(?:花了|消费|支付|付款|支出|用了)\s*[¥￥]?\s*(\d+(?:\.\d+)?)\s*(?:元|块|人民币)?', question)
    if not amount_match:
        amount_match = re.search(r'(.{0,30}?)[¥￥]\s*(\d+(?:\.\d+)?)', question)
    if amount_match and any(k in question for k in ['记账', '账单', '消费', '花了', '支付', '付款', '支出']):
        raw_name = re.sub(r'(帮我|请|记账|记一笔|账单|消费|花了|支付|付款|支出|今天|明天|后天|昨天)', '', amount_match.group(1)).strip(' ，,。')
        name = raw_name or infer_bill_category(question)
        parsed["bills"].append({
            "name": name,
            "category": infer_bill_category(question),
            "amount": float(amount_match.group(2)),
            "bill_date": date_text,
        })

    if any(k in question for k in ['添加行程', '新增行程', '记录行程', '行程记录', '帮我安排', '安排去', '计划去']) or re.search(r'(今天|明天|后天|昨天|\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}).{0,20}(去|游览|参观)', question):
        time_match = re.search(r'((?:上午|下午|晚上|中午|早上)?\s*\d{1,2}[:：点]\d{0,2})', question)
        name = re.sub(r'(帮我|请|添加行程|新增行程|记录行程|行程记录|安排|今天|明天|后天|昨天)', '', question)
        name = re.sub(r'((?:\d{4}[-年])?\d{1,2}[月/-]\d{1,2}日?)', '', name)
        if time_match:
            name = name.replace(time_match.group(1), '')
        name = name.strip(' ，,。') or '未命名行程'
        parsed["trips"].append({
            "name": name,
            "trip_date": date_text,
            "time": time_match.group(1).strip() if time_match else '',
            "note": '',
            "status": 'pending',
        })
    return parsed


def parse_records_with_llm(question: str) -> dict:
    """用 LLM 从用户话语中提取行程和账单记录。"""
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""你是旅游助手的信息抽取器。请从用户输入中提取需要新增的行程记录和账单记录，只返回 JSON，不要解释。

今天日期：{today}
允许的账单分类：交通、门票、餐饮、住宿、购物

返回格式：
{{
  "intent": "record" 或 "none",
  "trips": [
    {{"name": "行程名称", "trip_date": "日期", "time": "时间或空字符串", "note": "备注或空字符串", "status": "pending"}}
  ],
  "bills": [
    {{"name": "账单名称", "category": "交通/门票/餐饮/住宿/购物", "amount": 数字, "bill_date": "日期"}}
  ]
}}

规则：
1. 用户只是在询问景点、天气、系统功能时，intent 返回 "none"。
2. “今天/明天/后天/昨天”请换算为 YYYY-MM-DD；用户明确写了中文日期也可以保留。
3. 一句话里有多条记录时全部提取。
4. 缺少金额的账单不要提取；缺少日期的记录使用今天日期。

用户输入：{question}"""
    response = Generation.call(
        model="qwen-turbo",
        prompt=prompt,
        temperature=0
    )
    if response.status_code != 200:
        print(f"[RECORD] LLM 调用失败: {response.message}")
        return fallback_parse_records(question)
    parsed = extract_json_object(response.output.get('text', ''))
    if not parsed:
        return fallback_parse_records(question)
    return parsed


def save_assistant_records(parsed: dict, user_id: int) -> dict:
    """保存助手提取出的行程和账单。"""
    trips = parsed.get("trips") or []
    bills = parsed.get("bills") or []
    created_trips = []
    created_bills = []

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        for item in trips:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            trip_date = normalize_record_date(item.get("trip_date"))
            trip_time = str(item.get("time") or "").strip()
            note = str(item.get("note") or "").strip()
            status_value = item.get("status") if item.get("status") in ("pending", "completed") else "pending"
            cursor.execute(
                "INSERT INTO trip_plans (user_id, name, trip_date, time, note, status) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name, trip_date, trip_time, note, status_value)
            )
            created_trips.append({
                "id": cursor.lastrowid,
                "name": name,
                "trip_date": trip_date,
                "time": trip_time,
                "note": note,
                "status": status_value,
            })

        for item in bills:
            name = str(item.get("name") or "").strip()
            try:
                amount = float(item.get("amount"))
            except (TypeError, ValueError):
                continue
            if not name or amount <= 0:
                continue
            category = str(item.get("category") or "").strip()
            if category not in BILL_CATEGORIES:
                category = infer_bill_category(name)
            bill_date = normalize_record_date(item.get("bill_date"))
            icon = BILL_CATEGORIES[category]["icon"]
            color = BILL_CATEGORIES[category]["color"]
            cursor.execute(
                "INSERT INTO bills (user_id, name, category, amount, bill_date, icon, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, name, category, amount, bill_date, icon, color)
            )
            created_bills.append({
                "id": cursor.lastrowid,
                "name": name,
                "category": category,
                "amount": amount,
                "bill_date": bill_date,
                "icon": icon,
                "color": color,
            })
        conn.commit()
    finally:
        conn.close()

    return {"trips": created_trips, "bills": created_bills}


async def handle_assistant_record(question: str, current_user: dict | None) -> dict | None:
    """处理助手中的行程/账单记录请求，不是记录请求则返回 None。"""
    if not is_record_request(question):
        return None

    parsed = parse_records_with_llm(question)
    fallback_parsed = fallback_parse_records(question)
    if fallback_parsed.get("trips") and not parsed.get("trips"):
        parsed["trips"] = fallback_parsed["trips"]
    if fallback_parsed.get("bills") and not parsed.get("bills"):
        parsed["bills"] = fallback_parsed["bills"]
    if not parsed.get("trips") and not parsed.get("bills") and parsed.get("intent") != "record":
        return None

    if current_user is None:
        return {"type": "error", "text": "请先登录后，再让我帮你添加行程或账单。"}

    saved = save_assistant_records(parsed, current_user["id"])
    trip_count = len(saved["trips"])
    bill_count = len(saved["bills"])
    if trip_count == 0 and bill_count == 0:
        return {
            "type": "record",
            "text": "我还没能提取出可保存的行程或账单。可以这样说：明天 9 点去外滩，今天午餐花了 68 元。",
            "records": saved,
        }

    parts = []
    if trip_count:
        trip_names = "、".join(item["name"] for item in saved["trips"])
        parts.append(f"已添加 {trip_count} 条行程：{trip_names}")
    if bill_count:
        bill_names = "、".join(f"{item['name']} ¥{item['amount']}" for item in saved["bills"])
        parts.append(f"已记录 {bill_count} 笔账单：{bill_names}")
    return {
        "type": "record",
        "text": "；".join(parts) + "。去个人信息页就能看到最新记录。",
        "records": saved,
    }


async def query_with_llm(question: str) -> dict:
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
                return {"type": "weather", "text": weather_text}
            else:
                return {"type": "weather", "text": f"抱歉，暂时无法获取{location_name}的天气信息。"}
        else:
            return {"type": "weather", "text": f"抱歉，无法找到{location_name}的位置信息。"}

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
            return {"type": "knowledge", "text": response.output['text']}
        else:
            return {"type": "knowledge", "text": f"LLM 调用失败：{response.message}"}

    # 4. 数据库查询
    table_info = get_table_info() # 获取表结构(PRAGMA table_info)

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
        return {"type": "error", "text": f"LLM 调用失败：{sql_response.message}"}

    sql = extract_sql(sql_response.output['text'])
    if not sql:
        return {"type": "error", "text": "无法理解您的问题，请尝试换一种表达方式"}

    result = execute_query(sql)
    if isinstance(result, str):
        return {"type": "error", "text": f"查询出错：{result}"}
    if len(result) == 0:
        return {"type": "list", "data": [], "total": 0, "columns": []}

    # 判断是否为"列出全部"类型的查询
    list_all_keywords = ['有哪些', '有什么', '全部', '所有', '列出', '罗列']
    is_list_all = any(k in question for k in list_all_keywords)

    # 提取列名
    columns = list(result[0].keys()) if result else []

    # 5. 格式化结果 —— 返回结构化 dict，前端自行渲染
    if is_list_all:
        # 列出全部模式：直接返回结构化数据，不经过LLM摘要
        return {
            "type": "list",
            "data": result,
            "total": len(result),
            "columns": columns,
        }
    else:
        # 摘要模式：LLM 总结 + 原始数据一起返回
        format_prompt = f"""用户问题：{question}
SQL查询结果：{str(result[:100])}

请用简洁的自然语言总结这些数据。"""

        summary_text = ""
        format_response = Generation.call(
            model="qwen-turbo",
            prompt=format_prompt,
            temperature=0
        )
        if format_response.status_code == 200:
            summary_text = format_response.output['text']

        return {
            "type": "summary",
            "summary": summary_text,
            "data": result,
            "total": len(result),
            "columns": columns,
        }


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
async def query(request: QueryRequest, current_user: dict | None = Depends(get_optional_current_user)):
    """自然语言查询接口 —— 移动端友好：返回结构化 JSON + 分页"""
    try:
        # 限制 page_size 范围
        page = max(1, request.page)
        page_size = min(max(1, request.page_size), 100)

        result = await handle_assistant_record(request.question, current_user)
        if result is None:
            result = await query_with_llm(request.question)

        # ---- 导出 CSV 模式 ----
        if request.export and isinstance(result, dict) and result.get("type") in ("list", "summary"):
            data = result.get("data", [])
            if data:
                csv_data = format_csv(data)
                return {
                    "success": True,
                    "result": f"导出成功，共 {len(data)} 条数据",
                    "csv": csv_data,
                    "timestamp": datetime.now().isoformat()
                }

        # ---- 结构化数据类型 → 分页切片 ----
        if isinstance(result, dict) and result.get("type") in ("list", "summary"):
            full_data = result.get("data", [])
            total = len(full_data)
            start = (page - 1) * page_size
            end = start + page_size
            paged_data = full_data[start:end]

            return {
                "success": True,
                "type": result["type"],
                "data": paged_data,
                "columns": result.get("columns", []),
                "summary": result.get("summary", ""),
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": (total + page_size - 1) // page_size,
                },
                "timestamp": datetime.now().isoformat(),
            }

        if isinstance(result, dict) and result.get("type") == "record":
            return {
                "success": True,
                "type": "record",
                "text": result.get("text", ""),
                "records": result.get("records", {"trips": [], "bills": []}),
                "timestamp": datetime.now().isoformat(),
            }

        # ---- 知识库 / 天气 / 错误 → 直接透传 ----
        if isinstance(result, dict):
            return {
                "success": True,
                "type": result.get("type", "unknown"),
                "text": result.get("text", ""),
                "timestamp": datetime.now().isoformat(),
            }

        # 兼容旧格式（字符串）
        return {"success": True, "type": "text", "text": str(result), "timestamp": datetime.now().isoformat()}
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
