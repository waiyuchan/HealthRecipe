import json
import re
from bs4 import BeautifulSoup

with open("../../data/category.html") as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')
result = {}
content = soup.find('div', attrs={'class': 'block-bg p40 font16'})
content_list = content.find_all('div', attrs={'class': 'cates-list clearfix has-bottom-border pb20 mb20'})

for c in content_list:
    # 处理第一层目录
    left_content = c.find("div", attrs={'class': 'cates-list-info ml15 float-left'})
    first_level = left_content.text.replace("\n", "").replace(" ", "")
    result[first_level] = {}

    # 处理子目录和具体类别
    right_content = c.find("div", attrs={'class': 'cates-list-all clearfix'})

    # 获取子目录标签列表
    second_levels = right_content.find_all("h4", attrs={'class': 'font16'})

    # 获取类别列表
    items = right_content.find_all("ul", attrs={'class': 'has-bottom-border'})
    for x, y in enumerate(second_levels):
        second_level = y.text.replace("\n", "").replace(" ", "")
        url = y.find("a").get("href") if y.find("a") is not None else ""
        result[first_level][second_level] = {"url": url, "items": []}
        for i in items[x].find_all("li"):
            if i is not None:
                item_name = re.sub(r"[\d\.]+", '', i.text.replace("\n", "").replace(" ", ""))
                item_url = i.find("a").get("href")
                new_item = {"name": item_name, "url": item_url}
                result[first_level][second_level]["items"] = new_item

print(json.dumps(result, ensure_ascii=False, indent=2))
with open("../../data/category.json", "w") as f:
    f.write(json.dumps(result, ensure_ascii=False))
