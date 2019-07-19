import scrapy
from scrapy.crawler import CrawlerProcess
import cfscrape
from elasticsearch import Elasticsearch
import js2xml
from js2xml.utils.vars import get_vars
import json
import re

class AnimeSpider(scrapy.Spider):
    name = "AnimeSpider"
    base_url = "https://animeflv.net/"
    es = Elasticsearch(hosts="localhost")
    def start_requests(self):
        url = self.base_url+"browse?order=added"
        token,agent = cfscrape.get_tokens(url=url)
        self.token = token
        self.agent = agent
        yield scrapy.Request(url=url,callback=self.parse, cookies=token, headers={'User-Agent': agent})

    def parse(self,response):
        for a in response.xpath('.//article[@class="Anime alt B"]'):
            name = a.xpath(".//a/@href").extract_first()
            yield response.follow(self.base_url+name,callback=self.AnimeData,
                                cookies=self.token,
                                headers={'User-Agent': self.agent})
        next_page = response.xpath('//a[@rel="next"]/@href').extract()
        if next_page:
            yield response.follow(self.base_url+next_page[0],callback=self.parse,
                                  cookies=self.token,
                                  headers={'User-Agent': self.agent})
    def AnimeData(self,res):
        data = {}
        data["id"] = int(re.findall("\/[0-9]+\/",res.request.url)[0][1:-1])
        data["rating"] = float(res.xpath('//span[@id="votes_prmd"]/text()').extract_first())
        data["description"] = res.xpath('//div[@class="Description"]/p/text()').extract_first()
        data["img"] = res.xpath('//figure//img/@src').extract_first()
        data["genre"] = [g.xpath('text()').extract_first() for g in res.xpath('//nav[@class="Nvgnrs"]//a')]
        data["type"] = res.xpath('//span[contains(@class,"Type")]/text()').extract_first()
        data["web_state"] = res.xpath('//p[contains(@class,"AnmStts")]//span/text()').extract_first()
        data["votes"] = int(res.xpath('//span[@id="votes_nmbr"]/text()').extract_first())
        script = res.xpath('//script[contains(., "var anime_info")]/text()').extract_first()
        script_vars = get_vars(js2xml.parse(script))
        anime_info = script_vars["anime_info"]
        data["name"] = anime_info[1]
        episodes_info = sorted(script_vars["episodes"])
        data["episodes_num"] = len(episodes_info)
        episodes = {}
        for e in episodes_info:
            episodes[e[0]] = {"link":"https://animeflv.net/ver/%s/%s-%s"%(e[1],anime_info[2],e[0]),
                             "img": "https://cdn.animeflv.net/screenshots/%s/%s/th_3.jpg"%(anime_info[0],e[0])}
        animeRel = []
        for a in res.xpath('//ul[contains(@class,"ListAnmRel")]//li'):
            aid = re.findall("\/[0-9]+\/",a.xpath('a/@href').extract_first())[0][1:-1]
            atype = a.xpath('text()').extract_first()
            name = a.xpath('a/text()').extract_first()
            animeRel.append({"id":aid,"name":name,"type":atype})
        data["animeRel"] = animeRel
        data["episodes"] = episodes
        try:
            res = self.es.index(index="animeflv",doc_type="anime",body=data,id=data["id"])
        except Exception as e:
            with open("animes/%s.json"%data["id"],'w') as f:
                json.dump(data,f)
                f.write(str(e))
proc = CrawlerProcess()
proc.crawl(AnimeSpider)
proc.start()
