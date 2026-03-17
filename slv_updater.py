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
    """从 iShares 官网抓取库存和份额数据"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    try:
        response = requests.get(SOURCE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # --- 1. 抓取库存 (Ounces in Trust) ---
        target_ounces = soup.find(string=re.compile(r'Ounces in Trust'))
        # --- 2. 抓取份额 (Shares Outstanding) ---
        target_shares = soup.find(string=re.compile(r'Shares Outstanding'))

        if not target_ounces or not target_shares:
            print("错误: 页面上未找到关键数据标签。")
            return None, None, None

        def extract_info(label_node):
            """提取日期和紧随其后的数值"""
            container = label_node.find_parent().find_parent().get_text(separator=" ", strip=True)
            # 提取日期
            date_match = re.search(r'([A-Z][a-z]{2}\s\d{1,2},\s202\d)', container)
            if not date_match: return None, None
            
            raw_date = date_match.group(1)
            # 提取数值 (在日期之后寻找带逗号的数字)
            text_after_date = container.split(raw_date)[1]
            val_match = re.search(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?)', text_after_date)
            val = float(val_match.group(1).replace(",", "")) if val_match else None
            return raw_date, val

        date_str_o, ounces = extract_info(target_ounces)
        date_str_s, shares = extract_info(target_shares)

        # 校验日期是否一致（确保是同一天的数据）
        if date_str_o != date_str_s:
            print(f"警告: 库存日期({date_str_o})与份额日期({date_str_s})不匹配！")

        date_obj = datetime.datetime.strptime(date_str_o, "%b %d, %Y")
        formatted_date = date_obj.strftime("%Y-%m-%d")

        print(f"--- 提取成功 ---")
        print(f"日期: {formatted_date} | 库存: {ounces} | 份额: {shares}")
        return formatted_date, ounces, shares

    except Exception as e:
        print(f"抓取异常: {e}")
        return None, None, None

def write_to_notion(date, ounces, shares):
    """将数据写入 Notion"""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # 查重
    query_url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    query_payload = {"filter": {"property": "Date", "date": {"equals": date}}}
    check_res = requests.post(query_url, headers=headers, json=query_payload)
    
    if check_res.status_code == 200 and len(check_res.json().get("results", [])) > 0:
        print(f"通知: Notion 中已存在 {date} 的记录，跳过。")
        return

    # 写入数据
    create_url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Date": {"date": {"start": date}},
            "Ounces In trus": {"number": ounces},
            "Shares Outstanding": {"number": shares} # 注意：此处名称须与 Notion 列表名严格一致
        }
    }
    
    res = requests.post(create_url, headers=headers, json=payload)
    if res.status_code == 200:
        print(f"成功写入 Notion 表格！")
    else:
        print(f"Notion 写入失败: {res.text}")

if __name__ == "__main__":
    d, o, s = get_slv_data()
    if d and o and s:
        write_to_notion(d, o, s)
    else:
        print("由于抓取数据不完整，脚本已终止。")
        sys.exit(1)
