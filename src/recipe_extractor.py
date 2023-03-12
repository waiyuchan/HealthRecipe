import json

from lxml import etree
import requests
from bs4 import BeautifulSoup


def recipe_extractor(recipe_id):
    """
    下厨房菜谱提取器
    :param recipe_id: 下厨房的菜谱ID，比如 `https://www.xiachufang.com/recipe/100561839/`，则菜谱ID为 `100561839`
    :return: JSON格式的菜谱
    """
    url = "https://www.xiachufang.com/recipe/{}/".format(recipe_id)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'
    }
    rsp = requests.get(url, headers=headers)
    html = rsp.text
    soup = BeautifulSoup(html, 'html.parser')
    dom = etree.HTML(html)

    recipe_title = dom.xpath("/html/body/div[4]/div/div/div[1]/div[1]/h1/text()")[0].replace("\n", "").replace(" ", "")
    recipe_material = []
    materials = soup.find_all('table')[0]
    for material in materials.findAll('tr'):
        item = {"name": "", "unit": ""}
        for td in material.findAll('td'):
            if item["name"] == "":
                item["name"] = str_cleaner(td.getText())
            else:
                item["unit"] = str_cleaner(td.getText())
        recipe_material.append(item)

    recipe_methods = []
    methods = soup.find_all(name='div', attrs={"class": "steps"})[0]
    for method in methods.findAll("li"):
        for detail in method.findAll("p"):
            recipe_methods.append(detail.getText())

    recipe = {"xcf_id": recipe_id, "name": recipe_title, "materials": recipe_material, "methods": recipe_methods}
    return recipe


def str_cleaner(string):
    return string.replace("\n", "").replace(" ", "")


def recipe_printer(dict_obj):
    print(json.dumps(dict_obj, ensure_ascii=False))
    print("菜名：{}".format(dict_obj["name"]))
    print()
    print("用料：")
    for item in dict_obj["materials"]:
        print("{} {}".format(item["name"], item["unit"]))
    print()
    print("做法：")
    for i in range(len(dict_obj["methods"])):
        print("{}. {}".format(i + 1, dict_obj["methods"][i]))


if __name__ == '__main__':
    recipe_id = "106605291"
    recipe = recipe_extractor(recipe_id)
    recipe_printer(recipe)
