import requests
from bs4 import BeautifulSoup
import datetime
import os
import sys

# 从环境变量读取 Secrets
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SOURCE_URL = "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund"

def get_slv_data():
    """从 iShares 官网抓取权威数据"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(SOURCE_URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 逻辑：定位包含 "Ounces in Trust" 的标签
        # iShares 页面通常在 holdings 部分的 data-item 中
        ounces_label = soup.find(text=lambda t: t and "Ounces in Trust" in t)
        if not ounces_label:
            print("Error: 无法在页面上找到 'Ounces in Trust' 标签。数据获取中 (N/A)")
            return None, None

        # 提取数值 (去掉逗号)
        value_div = ounces_label.find_parent().find("span", class_="data")
        ounces_value = float(value_div.text.strip().replace(",", ""))

        # 提取日期 (格式通常为 as of Mar 11, 2026)
        date_span = ounces_label.find_parent().find("span", class_="as-of-date")
        date_str = date_span.text.replace("as of", "").strip()
        # 转换为 Notion 要求的 YYYY-MM-DD
        date_obj = datetime.datetime.strptime(date_str, "%b %d, %2026")
        formatted_date = date_obj.strftime("%Y-%m-%d")

        return formatted_date, ounces_value

    except Exception as e:
        print(f"数据抓取失败: {e}")
        return None, None

def write_to_notion(date, ounces):
    """写入数据到 Notion 数据库"""
    if not date or not ounces:
        return

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # 1. 检查日期是否已存在（查重）
    query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    query_payload = {
        "filter": {"property": "Date", "date": {"equals": date}}
    }
    check_res = requests.post(query_url, headers=headers, json=query_payload)
    
    if check_res.status_code == 200 and len(check_res.json().get("results", [])) > 0:
        print(f"日期 {date} 的记录已存在，跳过写入。")
        return

    # 2. 写入新记录
    create_url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Date": {"date": {"start": date}},
            "Ounces In trus": {"number": ounces} 
        }
    }
    
    res = requests.post(create_url, headers=headers, json=payload)
    if res.status_code == 200:
        print(f"成功更新: {date} | {ounces} Ounces")
    else:
        print(f"写入失败: {res.text}")

if __name__ == "__main__":
    date_val, ounces_val = get_slv_data()
    if date_val:
        write_to_notion(date_val, ounces_val)
    else:
        print("未获取到有效数据，程序退出。")
        sys.exit(0)
