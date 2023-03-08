from lxml import etree
import requests
from bs4 import BeautifulSoup


def recipe_extractor(recipe_id):
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


recipe = recipe_extractor("100561839")
print(recipe)
