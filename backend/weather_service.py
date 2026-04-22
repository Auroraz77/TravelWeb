"""
天气服务模块
使用气象局官方 API 获取实时天气
"""

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 气象局 API JWT Token
JWT_TOKEN = "eyJhbGciOiJFZERTQSIsImtpZCI6IlQ0Qjk5QkVNRFIiLCJ0eXAiOiJKV1QifQ.eyJpYXQiOjE3NzY4MTQyNzIsImV4cCI6MTc3NjgyNTEwMiwic3ViIjoiNEcyRDRXRjk1NSJ9.xwkVqCNoqEVUOiG9N1Ql5VpPuVdwlRJscheLFP1sOA1dxj3imraGNAZTygadWIyeiUzhblQ4T81E-Ry8he1hBw"

# API 基础 URL
BASE_URL = "https://my6e4fnaqq.re.qweatherapi.com"


def geo_lookup(location_name: str) -> dict:
    """
    通过地名获取坐标和 Location ID

    Args:
        location_name: 地区名称，如 "上海"、"北京"、"陕西西安碑林区"

    Returns:
        {"success": True, "name": "上海", "lon": 121.4, "lat": 31.2, "id": "101020100"}
        或 {"success": False, "error": "..."}
    """
    url = f"{BASE_URL}/geo/v2/city/lookup"
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}"
    }
    params = {
        "location": location_name
    }

    try:
        response = requests.get(url, headers=headers, params=params, verify=False, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "200" and data.get("location"):
                location = data["location"][0]
                return {
                    "success": True,
                    "name": location.get("name", location_name),
                    "lon": location.get("lon"),
                    "lat": location.get("lat"),
                    "id": location.get("id")
                }
            else:
                return {
                    "success": False,
                    "error": f"未找到该地区: {location_name}",
                    "code": data.get("code")
                }
        else:
            return {
                "success": False,
                "error": f"HTTP错误: {response.status_code}",
                "message": response.text
            }
    except Exception as e:
        return {
            "success": False,
            "error": "请求异常",
            "message": str(e)
        }


def get_weather_now(location: str) -> dict:
    """
    获取实时天气

    Args:
        location: 地区/城市名称，如 "上海"、"北京"、"101010100"

    Returns:
        天气信息字典
    """
    url = f"{BASE_URL}/v7/weather/now"
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}"
    }
    params = {
        "location": location
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "200":
                return {
                    "success": True,
                    "location": data.get("location", {}).get("name", location),
                    "temp": data.get("now", {}).get("temp", "N/A"),
                    "feelsLike": data.get("now", {}).get("feelsLike", "N/A"),
                    "text": data.get("now", {}).get("text", "N/A"),  # 天气状况
                    "windDir": data.get("now", {}).get("windDir", "N/A"),  # 风向
                    "windSpeed": data.get("now", {}).get("windSpeed", "N/A"),  # 风速
                    "humidity": data.get("now", {}).get("humidity", "N/A"),  # 湿度
                    "precip": data.get("now", {}).get("precip", "N/A"),  # 降水量
                    "pressure": data.get("now", {}).get("pressure", "N/A"),  # 气压
                    "vis": data.get("now", {}).get("vis", "N/A"),  # 能见度
                    "cloud": data.get("now", {}).get("cloud", "N/A"),  # 云量
                    "updateTime": data.get("updateTime", "N/A"),
                }
            else:
                return {
                    "success": False,
                    "error": f"API返回错误码: {data.get('code')}",
                    "message": data.get("message", "未知错误")
                }
        else:
            return {
                "success": False,
                "error": f"HTTP错误: {response.status_code}",
                "message": response.text
            }
    except Exception as e:
        return {
            "success": False,
            "error": "请求异常",
            "message": str(e)
        }


def get_weather_forecast(location: str, days: int = 3) -> dict:
    """
    获取天气预报

    Args:
        location: 地区/城市名称
        days: 预报天数，默认3天

    Returns:
        天气预报字典
    """
    url = f"{BASE_URL}/v7/weather/{days}d"
    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}"
    }
    params = {
        "location": location
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "200":
                daily = data.get("daily", [])
                forecast = []
                for day in daily:
                    forecast.append({
                        "date": day.get("fxDate", ""),
                        "textDay": day.get("textDay", "N/A"),  # 白天天气
                        "textNight": day.get("textNight", "N/A"),  # 夜间天气
                        "tempMax": day.get("tempMax", "N/A"),  # 最高温度
                        "tempMin": day.get("tempMin", "N/A"),  # 最低温度
                        "humidity": day.get("humidity", "N/A"),  # 湿度
                        "precip": day.get("precip", "N/A"),  # 降水量
                        "windDir": day.get("windDirDay", "N/A"),  # 白天风向
                        "windSpeed": day.get("windSpeedDay", "N/A"),  # 白天风速
                    })
                return {
                    "success": True,
                    "location": data.get("location", {}).get("name", location),
                    "forecast": forecast
                }
            else:
                return {
                    "success": False,
                    "error": f"API返回错误码: {data.get('code')}",
                    "message": data.get("message", "未知错误")
                }
        else:
            return {
                "success": False,
                "error": f"HTTP错误: {response.status_code}",
                "message": response.text
            }
    except Exception as e:
        return {
            "success": False,
            "error": "请求异常",
            "message": str(e)
        }


if __name__ == "__main__":
    # 测试天气查询
    print("测试实时天气查询...")
    result = get_weather_now("上海")
    print(result)

    print("\n测试天气预报查询...")
    result = get_weather_forecast("上海")
    print(result)
