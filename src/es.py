from elasticsearch import Elasticsearch


class ES:

    def __init__(self):
        self.es = Elasticsearch("http://localhost:9200")
        self.es.indices.create(index='menu', ignore=400)

    def insert(self, menu_item=None, menu_items=None):
        if menu_items is not None:
            bulk_data = []
            for item in menu_items:
                bulk_data.append({
                    '_index': 'menu',
                    '_type': '_doc',
                    '_id': item['xcf_id'],
                    '_source': item
                })
            self.es.bulk(index='menus', body=bulk_data, refresh=True)
        self.es.index(index='menu', id=menu_item['xcf_id'], doc_type='doc', body=menu_item)


if __name__ == '__main__':
    data = {
        "xcf_id": "106605291",
        "name": "淮山芙蓉汤",
        "materials": [
            {"name": "山药", "unit": "1根"},
            {"name": "鸡蛋", "unit": "3个"},
            {"name": "香菇", "unit": "3朵"},
            {"name": "胡萝卜", "unit": "1根"},
            {"name": "青菜", "unit": "3片"}
        ],
        "methods": [
            "备料：胡萝卜、香菇切成丁山药用刀背打成泥青菜切碎",
            "热锅冷油，放入胡萝卜香菇丁炒香",
            "倒入一大碗水",
            "烧开后倒入山药泥，搅拌均匀，烧开",
            "烧开后，倒入打散的鸡蛋液，一边倒一边搅拌",
            "最后放入青菜碎，放适量盐，出锅👌"
        ]
    }
    ES().insert(menu_item=data)
