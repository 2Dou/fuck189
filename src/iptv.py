#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IPTV频道列表生成器
从EPG源获取频道信息并生成M3U8格式的播放列表
"""

import requests
import m3u8
import sys
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import strict_rfc3339
from datetime import datetime
import logging
from pathlib import Path


class IPTVChannelExtractor:
    """IPTV频道信息提取器"""

    def __init__(self, base_url="http://epg.51zmt.top:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        # 频道分类规则
        self.category_rules = {
            '央视': ['CCTV', 'CETV', 'CGTN'],
            '卫视': ['卫视'],
            '少儿': ['少儿', '动画', '卡通',],
            '电影': ['电影', '影院', '院线', '大片', '爱浪漫',
                   '爱喜剧', '爱科幻', '爱院线', '爱历史', '爱悬疑', '爱谍战'],
            '电视剧': ['剧场', '电视剧', '热播', '热门', '经典', '都市', '谍战',
                      '都市剧场', '热门剧场', '经典剧场', '爱旅行', '精彩影视'],
            '四川': ['SCTV', '四川', 'CDTV', '熊猫', '峨眉', '成都'],
        }

        # 过滤关键词
        self.filter_keywords = [
            "单音轨", "画中画", "热门", "直播室", "爱", "92",
            "测试", "备用", "临时", "应急"
        ]

        # 清理关键词
        self.cleanup_keywords = ['超高清', '高清', '-', '标清']

    def fetch(self, url):
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logging.error(f"请求失败 {url}: {e}")
            return None

    def contains_any(self, text, keywords):
        return any(kw in text for kw in keywords)

    def categorize(self, name):
        for cat, kws in self.category_rules.items():
            if self.contains_any(name, kws):
                return cat
        return "其他"

    def load_icons(self):
        icons = []
        content = self.fetch(self.base_url)
        if not content:
            return icons
        soup = BeautifulSoup(content, 'lxml')
        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) < 4:
                continue
            a_tag = tds[0].find('a', href=True)
            if not a_tag or a_tag['href'] == '#':
                continue
            icons.append({
                'id': tds[3].get_text(strip=True),
                'name': tds[2].get_text(strip=True),
                'icon': a_tag['href']
            })
        return icons

    def extract_channels(self):
        channels = []
        content = self.fetch(f"{self.base_url}/sctvmulticast.html")
        if not content:
            return channels
        soup = BeautifulSoup(content, 'lxml')
        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            if not tds or tds[0].get_text(strip=True) == "序号":
                continue
            if len(tds) < 3:
                continue
            channels.append({
                'id': tds[0].get_text(strip=True),
                'name': tds[1].get_text(strip=True),
                'address': tds[2].get_text(strip=True)
            })
        return channels

    def process_channels(self, channels, icons_map):
        processed = []
        for ch in channels:
            name = ch['name']
            if self.contains_any(name, self.filter_keywords):
                continue
            for kw in self.cleanup_keywords:
                name = name.replace(kw, '')
            name = name.strip()

            processed.append({
                'id': ch['id'],
                'name': name,
                'address': ch['address'],
                'tag': self.categorize(name),
                'icon': icons_map.get(name, "")
            })
        return processed

    def build_icons_map(self, icons):
        return {item['name']: urljoin(self.base_url, item['icon']) for item in icons}

    def write_m3u8(self, channels, output_path, use_lan_address=False):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        timestamp = strict_rfc3339.now_to_rfc3339_utcoffset()
        header = (
            f'#EXTM3U name="成都电信IPTV - {timestamp}" '
            f'url-tvg="http://epg.51zmt.top:8000/e.xml,https://epg.112114.xyz/pp.xml"\n\n'
        )

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(header)
            for ch in channels:
                extinf = (
                    f'#EXTINF:-1 tvg-logo="{ch["icon"]}" '
                    f'tvg-id="{ch["id"]}" tvg-name="{ch["name"]}" '
                    f'group-title="{ch["tag"]}",{ch["name"]}\n'
                )
                f.write(extinf)

                if use_lan_address:
                    lan_addr = os.getenv('LAN_ADDRESS', 'http://localhost')
                    stream_url = f'{lan_addr}/rtp/{ch["address"]}\n'
                else:
                    stream_url = f'rtp://{ch["address"]}\n'

                f.write(stream_url)

        logging.info(f"已生成播放列表: {output_path}")

    def run(self, output_with_lan="./m3u8/chengdu_with_lan.m3u8",
                  output_native_rtp="./m3u8/chengdu_native_rtp.m3u8"):
        logging.info("开始提取频道数据...")
        raw_channels = self.extract_channels()
        logging.info(f"原始频道数: {len(raw_channels)}")

        icons = self.load_icons()
        icons_map = self.build_icons_map(icons)

        processed = self.process_channels(raw_channels, icons_map)
        logging.info(f"处理后频道数: {len(processed)}")

        self.write_m3u8(processed, output_with_lan, use_lan_address=True)
        self.write_m3u8(processed, output_native_rtp, use_lan_address=False)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    extractor = IPTVChannelExtractor()
    extractor.run()


if __name__ == "__main__":
    main()
