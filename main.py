import logging
import requests
import feedparser
import sqlite3
import opencc
import time
import os
import re
import threading
from sqlite3 import IntegrityError, OperationalError
from datetime import datetime


converter = opencc.OpenCC('t2s')  # 设置繁简转化

qb_url = 'http://qbittorrent.home.makuro.cn:8082'  # qBittorrent Web UI的URL
username = 'makuro'  # qBittorrent Web UI的用户名
password = 'SRCak2244@'  # qBittorrent Web UI的密码
proxies = {
    'http': 'http://172.16.1.10:10811',
    'https': 'http://172.16.1.10:10811'
}
down_path = "/qbittorrent/anime/data/Anime"
log_path = "/qbittorrent/anime/autoRss/log"
stop_time = 1200  # 每次获取RSS间隔 单位秒


def now_time():
    Time = time.time()
    datetime_obj = datetime.fromtimestamp(Time)
    formatted_date = datetime_obj.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return formatted_date


def today():
    Time = time.time()
    datetime_obj = datetime.fromtimestamp(Time)
    formatted_date = datetime_obj.strftime("%Y-%m-%d")
    return formatted_date


class Log:
    def __init__(self):
        self.day = today()
        self.logger = self.setup_logger()
        self.log_level = 'debug'

    def setup_logger(self):
        log_file = f"{log_path}/{self.day}.log"
        # 创建一个logger对象
        logger = logging.getLogger("my_logger")
        logger.setLevel(logging.DEBUG)
        # 清除现有的处理器，以防止累积
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        # 创建一个文件处理器，将日志写入文件
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        # 创建一个控制台处理器，将日志输出到控制台
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        # 定义日志格式
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        # 将处理器添加到logger对象
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        return logger

    def write_log(self, text, log_type):
        # 输出不同级别的日志
        if self.log_level == "error":
            if log_type == 'info':
                print(f"{now_time()} - INFO - {text}")
            elif log_type == 'error':
                self.logger.error(text)
            elif log_type == 'warning':
                print(f"{now_time()} - WARNING - {text}")
        elif self.log_level == "info":
            if log_type == 'info':
                self.logger.info(text)
            elif log_type == 'error':
                print(f"{now_time()} - ERROR - {text}")
            elif log_type == 'warning':
                self.logger.warning(text)
        elif self.log_level == "debug":
            if log_type == 'info':
                self.logger.info(text)
            elif log_type == 'error':
                self.logger.error(text)
            elif log_type == 'warning':
                self.logger.warning(text)

        elif self.log_level == "critical" and log_type == 'critical':
            self.logger.critical(text)
        # 检查是否开始了新的一天，如果是，则更新日志文件名
        new_day = today()
        if new_day != self.day:
            self.day = new_day
            # 在创建新处理器之前关闭旧的文件处理器
            self.logger.handlers[0].close()
            self.logger = self.setup_logger()


class DB:
    def __init__(self):
        self.conn = sqlite3.connect('db.db')
        self.cursor = self.conn.cursor()

    def select(self, sql):
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()
        self.cursor.close()
        self.conn.close()
        return rows

    def insert(self, sql):
        try:
            self.cursor.execute(sql)
            self.conn.commit()
        except IntegrityError or OperationalError:
            return False
        self.cursor.close()
        self.conn.close()
        return True

    def delete(self, sql):
        self.cursor.close()
        self.conn.close()

    def updata(self, sql):
        self.cursor.execute(sql)
        self.conn.commit()
        self.cursor.close()
        self.conn.close()


class qbittorrent:
    @staticmethod
    def login():
        login_url = f'{qb_url}/api/v2/auth/login'
        login_data = {'username': username, 'password': password}
        session = requests.Session()
        response = session.post(login_url, data=login_data)
        return response, session

    @staticmethod
    def add_torrent(save_path, torrent_file, quarter):
        # 登录qBittorrent Web UI

        if not os.path.exists(save_path):
            os.makedirs(save_path)
            time.sleep(1)
            os.chmod(save_path, 0o777)

        response, session = qbittorrent.login()
        if response.status_code == 200:
            # 添加下载任务
            add_url = f'{qb_url}/api/v2/torrents/add'
            with open(torrent_file, 'rb') as f:
                files = {'torrents': f}
                data = {
                    'savepath': save_path,
                    'autoTMM': 'false',  # 禁用自动分类
                    'paused': 'false',  # 立即开始下载
                    # 'skip_checking': 'true',  # 跳过文件校验
                    'category': f'autoRSS {quarter}',
                    'tags': quarter
                }

                response = session.post(add_url, data=data, files=files)
            if response.status_code == 200:
                return True
            else:
                Log().write_log(f"添加下载任务失败: {response.text}", 'error')
        else:
            Log().write_log(f"登录失败: {response.text}", 'error')
            Log().write_log(response.status_code, 'error')

    @staticmethod
    def get_torrent_list():
        torrent_list = []
        response, session = qbittorrent.login()
        if response.status_code == 200:
            get_list_url = f'{qb_url}/api/v2/torrents/info'
            torrent_web_list = session.get(get_list_url).json()
            for i in torrent_web_list:
                torrent_list.append(i['name'])

            return torrent_list

        else:
            print('err')


def nyaa_ANI_torrent():
    res_url = DB().select("SELECT rss_url FROM rss_url WHERE rss_name = 'ani'")[0][0]

    response = requests.get(res_url, proxies=proxies)
    feed_content = response.content

    # 解析 RSS feed
    feed = feedparser.parse(feed_content)

    for entry in feed.entries:
        number_of_words = None
        torrent_url = entry.link
        torrent_url = torrent_url[torrent_url.rfind('/') + 1:]
        torrent_url = torrent_url[:torrent_url.find('.')]

        torrent_title = entry.title
        if '/' in torrent_title:
            title = torrent_title[torrent_title.find('/') + 1:]
            title = title[:title.find('-')].replace(' ', '')

        else:
            title = torrent_title[:torrent_title.find('-') - 1]
            title = title[title.find(']') + 1:].replace(' ', '')
        number_of_words = torrent_title[torrent_title.find('-'):]
        number_of_words = number_of_words[:number_of_words.find('[')].replace('-', '').replace(' ', '')

        anime_title = converter.convert(title)

        release_time = datetime.strptime(entry.get('published', 'No published time'),
                                         '%a, %d %b %Y %H:%M:%S %z').replace(tzinfo=None)

        if '第十季' in torrent_title:
            season = 10
        elif '第九季' in torrent_title:
            season = 9
        elif '第八季' in torrent_title:
            season = 8
        elif '第七季' in torrent_title:
            season = 7
        elif '第六季' in torrent_title:
            season = 6
        elif '第五季' in torrent_title:
            season = 5
        elif '第四季' in torrent_title:
            season = 4
        elif '第三季' in torrent_title:
            season = 3
        elif '第二季' in torrent_title:
            season = 2
        else:
            season = 1

        if '第十季' in torrent_title:
            anime_title = anime_title.replace('第十季', '')
        elif '第九季' in torrent_title:
            anime_title = anime_title.replace('第九季', '')
        elif '第八季' in torrent_title:
            anime_title = anime_title.replace('第八季', '')
        elif '第七季' in anime_title:
            anime_title = anime_title.replace('第七季', '')
        elif '第六季' in anime_title:
            anime_title = anime_title.replace('第六季', '')
        elif '第五季' in anime_title:
            anime_title = anime_title.replace('第五季', '')
        elif '第四季' in anime_title:
            anime_title = anime_title.replace('第四季', '')
        elif '第三季' in anime_title:
            anime_title = anime_title.replace('第三季', '')
        elif '第二季' in anime_title:
            anime_title = anime_title.replace('第二季', '')
        elif '第一季' in anime_title:
            anime_title = anime_title.replace('第一季', '')

        if number_of_words in ('01', '特别篇'):
            year = str(release_time.year)
            month = str(release_time.month)

            if month in ('12', '1', '2'):
                month = 'A'
            elif month in ('3', '4', '5'):
                month = 'B'
            elif month in ('6', '7', '8'):
                month = 'C'
            elif month in ('9', '10', '1'):
                month = 'D'

            if month == '12':
                year = str(int(year) + 1)
            year = year[2:]

            quarter = f"{year}{month}"

            sql = f'''INSERT INTO "main"."anime_quarter" ("anime_name", "quarter") VALUES ('{anime_title}', '{quarter}');'''
            DB().insert(sql)

        sql = f'''INSERT INTO "main"."rss_torrent" 
        ("rss_group", "torrent_url", "anime_title", "number_of_words", "status", "season", "release_time", "torrent_from")
         VALUES ('ANI', '{torrent_url}', '{anime_title}', '{number_of_words}', 0, {season}, '{release_time}', 'nyaa');'''
        if DB().insert(sql):
            Log().write_log(f'已更新订阅 - ANI - {anime_title} - 第{season}季 - 第{number_of_words}集', 'info')
            auto_download(torrent_url, 'nyaa', anime_title, number_of_words, season)
        else:
            # Log().write_log(f'订阅无新内容,休眠{stop_time}秒', 'info')
            return False


def auto_download(torrent_id, torrent_from, anime_title, number_of_words, season):
    # sql = f"SELECT * FROM rss_torrent WHERE status = '0'"
    # data = DB().select(sql)
    # for i in data:
    #     print(i)
    #     torrent_id = i[1]
    #     torrent_from = i[2]
    #     anime_title = i[3]
    #     number_of_words = i[4]
    #     season = i[6]

    sql = f'''SELECT quarter FROM "anime_quarter" WHERE anime_name = "{anime_title}"'''
    quarter = DB().select(sql)
    if quarter:
        quarter = quarter[0][0]
        if torrent_from == 'nyaa':
            torrent_url = f'''https://nyaa.si/download/{torrent_id}.torrent'''
        save_path = f"{down_path}/{quarter}/{anime_title}/Season {season}"

        response = requests.get(torrent_url, proxies=proxies)
        torrent_file = f'torrent/{torrent_id}.torrent'
        with open(torrent_file, 'wb') as f:
            f.write(response.content)

        if qbittorrent().add_torrent(save_path, torrent_file, quarter):
            # Log().write_log(f'添加QB成功 - {anime_title} - 第{season}季 - 第{number_of_words}集', 'info')
            sql = f'''UPDATE "main"."rss_torrent" SET  "status" = '1' WHERE "torrent_url" = '{torrent_id}';'''
            DB().updata(sql)
        os.remove(torrent_file)
    else:
        Log().write_log(f'无匹配 - {anime_title} - 第{season}季 - 第{number_of_words}集', 'warning')


def robot(message):
    try:
        requests.get(f"http://172.16.1.1:3000/send_group_msg?group_id=&message={message}")
        time.sleep(1)
        requests.get(f"http://172.16.1.1:3000/send_private_msg?user_id=&message={message}")
    except Exception as e:
        Log().write_log(e, 'error')


class main:
    @staticmethod
    def new_torrent():
        torrent_old_list = qbittorrent().get_torrent_list()
        while True:
            torrent_new_list = qbittorrent().get_torrent_list()
            new_torrent = [item for item in torrent_new_list if item not in torrent_old_list]

            if new_torrent:
                for i in new_torrent:
                    if 'ANi' in i:
                        title = re.sub(r'\[.*?\]', '', i).replace(' ', '')
                    else:
                        anime_title = i

                    anime_title = converter.convert(title)
                    robot(f'已获取 - {anime_title}')
                    Log().write_log(f'已获取新番剧 - {anime_title}', 'info')

                torrent_old_list = torrent_new_list
            else:
                if len(torrent_new_list) < len(torrent_old_list):
                    torrent_old_list = torrent_new_list
                time.sleep(10)

    @staticmethod
    def get_Rss():
        Log().write_log('程序启动', 'info')
        while True:
            nyaa_ANI_torrent()
            time.sleep(stop_time)


thread1 = threading.Thread(target=main().new_torrent)
thread2 = threading.Thread(target=main().get_Rss)
thread1.start()
thread2.start()