import requests
from bs4 import BeautifulSoup
import datetime
import os
import re
import sys

# 从 GitHub Secrets 中读取配置
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
SOURCE_URL = "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund"

def get_slv_data():
    """从 iShares 官网抓取权威数据并精准提取"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(SOURCE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. 定位包含 "Ounces in Trust" 的文本块
        target_label = soup.find(string=re.compile(r'Ounces in Trust'))
        if not target_label:
            print("错误: 页面上未找到 'Ounces in Trust' 标签。")
            return None, None

        # 获取该标签周围的完整文本内容
        container_text = target_label.find_parent().find_parent().get_text(separator=" ", strip=True)
        print(f"原始抓取文本: {container_text}")

        # 2. 提取日期 (格式: Mar 11, 2026)
        date_match = re.search(r'([A-Z][a-z]{2}\s\d{1,2},\s202\d)', container_text)
        if not date_match:
            print("错误: 无法提取日期。")
            return None, None
        
        raw_date_str = date_match.group(1)
        date_obj = datetime.datetime.strptime(raw_date_str, "%b %d, %Y")
        formatted_date = date_obj.strftime("%Y-%m-%d")

        # 3. 提取数值 (核心修复：跳过日期，寻找带逗号的大数字)
        # 逻辑：在日期字符串出现之后的位置寻找数值
        parts = container_text.split(raw_date_str)
        if len(parts) < 2:
            print("错误: 文本结构异常，无法定位数值位置。")
            return None, None
        
        text_after_date = parts[1]
        # 匹配 499,592,395.30 这种格式（必须包含至少一个逗号，防止误抓单一数字）
        value_match = re.search(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', text_after_date)
        
        if not value_match:
            print(f"错误: 在日期之后未发现有效盎司数值。剩余文本: {text_after_date}")
            return None, None

        # 清洗数值：移除逗号并转为浮点数
        ounces_value = float(value_match.group(1).replace(",", ""))

        print(f"--- 提取成功 ---")
        print(f"日期: {formatted_date}")
        print(f"盎司: {ounces_value}")
        return formatted_date, ounces_value

    except Exception as e:
        print(f"抓取异常: {e}")
        return None, None

def write_to_notion(date, ounces):
    """将数据安全写入 Notion"""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # 1. 查重：检查该日期是否已有记录
    query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    query_payload = {"filter": {"property": "Date", "date": {"equals": date}}}
    check_res = requests.post(query_url, headers=headers, json=query_payload)
    
    if check_res.status_code == 200:
        results = check_res.json().get("results", [])
        if len(results) > 0:
            print(f"通知: Notion 中已存在 {date} 的记录，跳过。")
            return
    else:
        print(f"Notion 查询失败: {check_res.text}")
        return

    # 2. 写入数据
    create_url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Date": {"date": {"start": date}},
            "Ounces In trus": {"number": ounces}  # 确保 Notion 中此列为数字属性
        }
    }
    
    res = requests.post(create_url, headers=headers, json=payload)
    if res.status_code == 200:
        print(f"成功写入 Notion 表格！")
    else:
        print(f"Notion 写入失败: {res.status_code} - {res.text}")

if __name__ == "__main__":
    d, o = get_slv_data()
    if d and o:
        write_to_notion(d, o)
    else:
        print("由于抓取数据不完整，脚本已终止。")
        sys.exit(1)
