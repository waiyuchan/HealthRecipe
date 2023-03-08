import scrapy


class CategorySpider(scrapy.Spider):
    name = "menu"
    allowed_domains = ["xiachufang.com"]
    start_urls = [
        "https://www.xiachufang.com/category/"
    ]

    def start_requests(self):
        yield self.parse()

    def parse(self, response, **kwargs):
        pass
