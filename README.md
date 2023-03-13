# Health Recipe: 养生食谱

![](https://img.shields.io/badge/language-python3-blue.svg)
![](https://img.shields.io/badge/license-Apache_2.0-green.svg)

## 功能目录

- [x] 菜谱数据采集（基于下厨房网站）
  - [x] 菜谱分类
  - [x] 菜谱制作步骤
  - [ ] 材料功效
- [ ] 菜谱知识图谱自动化构建
- [x] 数据持久化存储
  - [x] 菜谱数据存储elasticsearch
  - [ ] 分类数据存储elasticsearch
  - [ ] 数据功效存储至MySQL
  - [ ] 知识图谱数据存储Neo4j
- [ ] 菜谱数据查询&搜索
- [ ] 菜谱过去14天做菜历史
- [ ] 食用反响
- [ ] 菜谱推荐
  - [ ] 随机推荐
  - [ ] 智能推荐（需要设计和构建推荐算法，优先采纳非监督机器学习算法）
    - [ ] 筛除过去14天做过的菜品
    - [ ] 结合天气推荐
    - [ ] 结合时节推荐
    - [ ] 结合食用反响推荐
    - [ ] 根据想吃的食材精准推荐（可选）

## 目标工具
- [x] 下厨房详情菜谱快速提取器
- [x] 下厨房菜谱分类快速提取器
- [ ] 菜谱工具H5版本
- [ ] 菜谱推荐微信小程序（嵌入团团家）

## 菜谱提取器
本提取器主要针对下厨房网站的菜谱内容进行提取。

打开 `recipe_extractor.py` 文件，修改 `recipe_id = ""` 中对菜单id。

比如 `https://www.xiachufang.com/recipe/100561839/` ，则菜谱ID为 `100561839`。

运行后可以得到如下的内容：

```text
菜名：淮山芙蓉汤

用料：
山药 1根
鸡蛋 3个
香菇 3朵
胡萝卜 1根
青菜 3片

做法：
1. 备料：胡萝卜、香菇切成丁山药用刀背打成泥青菜切碎
2. 热锅冷油，放入胡萝卜香菇丁炒香
3. 倒入一大碗水
4. 烧开后倒入山药泥，搅拌均匀，烧开
5. 烧开后，倒入打散的鸡蛋液，一边倒一边搅拌
6. 最后放入青菜碎，放适量盐，出锅👌
```

## 持久化存储方案：Elasticsearch

### 安装Elasticsearch（以macOS为例）

```shell
brew install elasticsearch@6
echo 'export PATH="/usr/local/opt/elasticsearch@6/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
elasticsearch
```

访问 `http://127.0.0.1:9200/` ，如果出现下面的内容说明成功

```json
{
  "name" : "j2wFuqc",
  "cluster_name" : "elasticsearch_brew",
  "cluster_uuid" : "BUpLEjwJTeGoaoqWh8ZYcg",
  "version" : {
    "number" : "6.8.23",
    "build_flavor" : "oss",
    "build_type" : "tar",
    "build_hash" : "4f67856",
    "build_date" : "2022-01-06T21:30:50.087716Z",
    "build_snapshot" : false,
    "lucene_version" : "7.7.3",
    "minimum_wire_compatibility_version" : "5.6.0",
    "minimum_index_compatibility_version" : "5.0.0"
  },
  "tagline" : "You Know, for Search"
}
```

### 安装Kibana（以macOS为例）

```shell
brew install kibana@6
echo 'export PATH="/usr/local/opt/kibana@6/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
kibana
```

访问 `http://localhost:5601/` ，如果可以看到 `Kibana` 的页面说明成功了。