import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import sys

# 从环境变量读取 Secrets
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SOURCE_URL = "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund"

def get_slv_data():
    """针对 Key Facts 布局优化的抓取逻辑"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(SOURCE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. 寻找包含 "Ounces in Trust" 的区块
        # 我们先找到这个文字所在的标签
        target_label = soup.find(string=re.compile(r'Ounces in Trust'))
        if not target_label:
            print("Error: 未能在页面找到 'Ounces in Trust' 文字")
            return None, None

        # 2. 向上找两层，拿到包含“标题、日期、数值”的完整容器文本
        container_text = target_label.find_parent().find_parent().get_text(separator=" ", strip=True)
        print(f"抓取到的原始文本区域: {container_text}")

        # 3. 使用正则表达式提取数据
        # 提取日期 (匹配格式如: Mar 11, 2026)
        date_match = re.search(r'([A-Z][a-z]{2}\s\d{1,2},\s202\d)', container_text)
        # 提取数值 (匹配 499,592,395.30 这种带逗号和点的数字)
        value_match = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', container_text.split("Trust")[-1])

        if not date_match or not value_match:
            print(f"正则匹配失败。日期匹配: {date_match}, 数值匹配: {value_match}")
            return None, None

        # 4. 格式化数据
        raw_date = date_match.group(1)
        # 转换为 Notion 的 YYYY-MM-DD
        date_obj = datetime.datetime.strptime(raw_date, "%b %d, %Y")
        formatted_date = date_obj.strftime("%Y-%m-%d")

        # 清洗数值中的逗号
        ounces_value = float(value_match.group(1).replace(",", ""))

        print(f"提取结果 -> 日期: {formatted_date}, 盎司: {ounces_value}")
        return formatted_date, ounces_value

    except Exception as e:
        print(f"抓取过程发生异常: {e}")
        return None, None

def write_to_notion(date, ounces):
    """写入数据到 Notion 数据库"""
    if not date or not ounces: return

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # 查重逻辑：如果该日期已存在则跳过
    query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    query_payload = {"filter": {"property": "Date", "date": {"equals": date}}}
    check_res = requests.post(query_url, headers=headers, json=query_payload)
    
    if check_res.status_code == 200 and len(check_res.json().get("results", [])) > 0:
        print(f"通知: {date} 的记录已在 Notion 中，跳过写入。")
        return

    # 写入新记录
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
        print(f"成功! 已存入 Notion: {date}")
    else:
        print(f"Notion 接口错误: {res.status_code} - {res.text}")

if __name__ == "__main__":
    d, o = get_slv_data()
    if d and o:
        write_to_notion(d, o)
    else:
        print("程序终止: 数据不完整。")
        sys.exit(1) # 告诉 GitHub Actions 运行失败了
