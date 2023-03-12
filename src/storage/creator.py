import time

from src.storage.es import ES
from src.collection.recipe_extractor import recipe_extractor


def get_xcf_id_list_from_txt(file_path):
    """
    获取下厨房菜谱id列表
    :param file_path: 文件路径
    :return: 下厨房菜谱id列表
    """
    with open(file_path, "r") as f:
        lines = f.readlines()
    return [line.strip() for line in lines]


class Creator(object):
    """ 菜谱创建器 """

    def __init__(self):
        self.es = ES()
        self.re = recipe_extractor

    def extract(self, xcf_id):
        return self.re(xcf_id)

    def es_insert(self, xcf_id):
        """
        单条插入
        :param xcf_id: 下厨房菜谱id
        """
        self.es.insert(menu_item=self.extract(xcf_id))

    def es_batch_insert(self, xcf_id_list):
        """
        批量插入
        :param xcf_id_list: 下厨房菜谱id列表
        """
        for xcf_id in xcf_id_list:
            self.es_insert(xcf_id)
            time.sleep(2)  # 避免高频访问下厨房网站


if __name__ == '__main__':
    xcf_id_list = get_xcf_id_list_from_txt("../../data/menu.txt")
    Creator().es_batch_insert(xcf_id_list)
