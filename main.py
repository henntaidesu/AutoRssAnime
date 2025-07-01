import logging
import sys
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
import pymysql


converter = opencc.OpenCC('t2s')  # 设置繁简转化

qb_url = 'http://qbittorrent.home.makuro.cn:8082'  # qBittorrent Web UI的URL
username = 'makuro'  # qBittorrent Web UI的用户名
password = 'SRCak2244@'  # qBittorrent Web UI的密码
proxies = {
    'http': 'http://172.16.1.10:10811',
    'https': 'http://172.16.1.10:10811'
}
down_path = "/qbittorrent/vcbs/nvme_data/Anime"

current_dir = os.path.dirname(os.path.abspath(__file__))
log_path = f"{current_dir}/log"
torrent_path = f"{current_dir}/torrent"
os.makedirs(log_path, exist_ok=True) 
os.makedirs(torrent_path, exist_ok=True) 

stop_time = 1200  # 每次获取RSS间隔 单位秒

mysql_host = '172.16.1.22'
mysql_port = 3306
mysql_user = 'makuro'
mysql_password = 'SRCak2244@'
mysql_database = 'autoRss'

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
        self.db = pymysql.connect(host=mysql_host, port=mysql_port, user=mysql_user,
                                  password=mysql_password, database=mysql_database)
        self.logger = Log()

    @staticmethod
    def TR_sql(sql):
        return sql.replace("'None'", "NULL")

    def insert(self, sql):
        try:
            sql = self.TR_sql(sql)
            cursor = self.db.cursor()
            cursor.execute(sql)
            self.db.commit()
            self.db.close()
            return True
        except Exception as e:
            if "PRIMARY" in str(e):
                # self.print_log.write_log(f"重复数据", 'info')
                return False
            elif "timed out" in str(e):
                self.logger.write_log("连接数据库超时", 'error')
            else:
                self.logger.write_log(f"错误 {sql}", 'error')
                return False

    def update(self, sql):
        try:
            sql = self.TR_sql(sql)
            cursor = self.db.cursor()
            cursor.execute(sql)
            self.db.commit()
            cursor.close()
            return True
        except Exception as e:
            if "timed out" in str(e):
                self.logger.write_log("连接数据库超时", 'error')
            elif "PRIMARY" in str(e):
                # self.print_log.write_log(f"重复数据", 'info')
                return '重复数据'
            else:
                self.logger.write_log(f'{sql}', 'error')
            return False
        finally:
            if hasattr(self, 'db') and self.db:
                self.db.close()

    def select(self, sql):
        try:
            sql = self.TR_sql(sql)
            cursor = self.db.cursor()
            cursor.execute(sql)
            result = cursor.fetchall()
            cursor.close()
            return True, result
        except Exception as e:
            if "timed out" in str(e):
                self.logger.write_log("连接数据库超时", 'error')
            else:
                self.logger.write_log(f'{sql}', 'error')
        finally:
            if hasattr(self, 'db') and self.db:
                self.db.close()


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
    def get_qbittorrent_torrent_list():
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
    # Log().write_log(f"启动", 'warning')
    res_url = 'https://nyaa.si/?page=rss&u=ANiTorrent'
    response = requests.get(res_url, proxies=proxies, timeout=10)
    feed_content = response.content

    # 解析 RSS feed
    feed = feedparser.parse(feed_content)
    limit = 1
    for entry in feed.entries:
        limit += 1
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

        number_of_words = re.sub(r'\[[^\]]*\]', '', torrent_title)
        try:
            number_of_words = int(number_of_words[number_of_words.rfind('-') + 1:].lstrip().rstrip())
        except ValueError:
            Log().write_log(f'集数转化错误', 'error')
            if number_of_words == '特别篇':
                number_of_words = -1
            else:
                Log().write_log(f'集数转化错误 ---- {number_of_words}', 'error') 
                number_of_words = -2

        anime_title = converter.convert(title)

        release_time = datetime.strptime(entry.get('published', 'No published time'),
                                         '%a, %d %b %Y %H:%M:%S %z').replace(tzinfo=None)

        # 默认 season 值
        season = 1

        # 中文季数标签（按优先顺序）
        cn_seasons = ['第十季', '第九季', '第八季', '第七季', '第六季',
                    '第五季', '第四季', '第三季', '第二季', '第一季']

        # 英文季数标签（按优先顺序）
        en_seasons = ['Season10', 'Season9', 'Season8', 'Season7', 'Season6',
                    'Season5', 'Season4', 'Season3', 'Season2', 'Season1']

        # 提取 season
        for i, tag in enumerate(cn_seasons):
            if tag in torrent_title:
                season = 10 - i
                break
        else:
            for i, tag in enumerate(en_seasons):
                if tag in torrent_title:
                    season = 10 - i
                    break

        # 清理 anime_title 中的中文标签
        for tag in cn_seasons:
            if tag in anime_title:
                anime_title = anime_title.replace(tag, '')

        # 清理 anime_title 中的英文标签
        for tag in en_seasons:
            if tag in anime_title:
                anime_title = anime_title.replace(tag, '')
        
        # Log().write_log(f"{anime_title} ---  {number_of_words}", 'warning')

        try:
            if number_of_words in (1, -1):
                year = release_time.year
                month = release_time.month

                if month == 12:
                    year += 1
                    season_code = 'A'
                elif month in (1, 2):
                    season_code = 'A'
                elif month in (3, 4, 5):
                    season_code = 'B'
                elif month in (6, 7, 8):
                    season_code = 'C'
                else:
                    season_code = 'D'

                quarter = f"{str(year)[2:]}{season_code}"

                sql = f'''INSERT INTO `anime_quarter` (`anime_name`, `quarter`, `season`) VALUES ('{anime_title}', '{quarter}', '{season}')'''
                DB().insert(sql)
        except Exception as e:
            Log().write_log(f'季度计算错误 - {anime_title} - {number_of_words} - {release_time}', 'error')

        sql = f'''INSERT INTO `rss_torrent`
        (`rss_group`, `torrent_url`, `anime_title`, `number_of_words`, `status`, `season`, `release_time`, `torrent_from`)
         VALUES ('ANI', '{torrent_url}', '{anime_title}', {number_of_words}, 0, {season}, '{release_time}', 'nyaa');'''
        if DB().insert(sql):
            Log().write_log(f'已更新订阅 - ANI - {anime_title} - 第{season}季 - 第{number_of_words}集', 'info')
            # auto_download(torrent_url, 'nyaa', anime_title, number_of_words, season)
        else:
            auto_download(limit)
            # Log().write_log(f'订阅无新内容,休眠{stop_time}秒', 'info')
            return False
    
    


# def auto_download(torrent_id, torrent_from, anime_title, number_of_words, season):
    #     pass

def auto_download(limit):
    sql = f"SELECT * FROM rss_torrent WHERE status = '0' order by release_time desc limit {limit + 1}"
    flag, data = DB().select(sql)
    for i in data:
        print(i)
        torrent_id = i[1]
        torrent_from = i[2]
        anime_title = i[3]
        number_of_words = i[4]
        season = i[6]
        sql = f'''SELECT quarter FROM `anime_quarter` WHERE anime_name = "{anime_title}"'''
        flag, quarter = DB().select(sql)
        if quarter:
            quarter = quarter[0][0]
            if torrent_from == 'nyaa':
                torrent_url = f'''https://nyaa.si/download/{torrent_id}.torrent'''
            save_path = f"{down_path}/{quarter}/{anime_title}/Season {season}"

            response = requests.get(torrent_url, proxies=proxies)
            torrent_file = f'{torrent_path}/{torrent_id}.torrent'
            try:
                with open(torrent_file, 'wb') as f:
                    f.write(response.content)
            except FileNotFoundError:
                Log().write_log(f'下载种子错误 url - {torrent_url}', 'error')

            if qbittorrent().add_torrent(save_path, torrent_file, quarter):
                Log().write_log(f'添加QB成功 - {anime_title} - 第{season}季 - 第{number_of_words}集', 'info')
                sql = f'''UPDATE `rss_torrent` SET  `status` = '1' WHERE `torrent_url` = '{torrent_id}';'''
                DB().update(sql)
            # os.remove(torrent_file)
        else:
            Log().write_log(f'无匹配 - {anime_title} - 第{season}季 - 第{number_of_words}集', 'warning')


def robot(message):
    try:
        requests.get(f"http://172.16.1.19:3000/send_group_msg?group_id=971990897&message={message}")
        # if req.status_code == 200:
        #     if req.json()['status'] == 'ok':
        #         Log().write_log(f"OK - {message}", 'error')
        # time.sleep(1)

        # for _ in range(3):
        #     req = requests.get(f"http://172.16.1.19:3000/send_private_msg?user_id=498791444&message={message}")
        #     if req.status_code == 200:
        #         if req.json()['status'] == 'ok':
        #             Log().write_log(f"OK - {message}", 'info')
        #             break
        #     else:
        #         Log().write_log(f"{req.status_code} - {message}", 'error')
    except Exception as e:
        Log().write_log(e, 'error')


# nyaa_ANI_torrent()


class main:
    @staticmethod
    def new_torrent():
        torrent_old_list = qbittorrent().get_qbittorrent_torrent_list()
        while True:
            torrent_new_list = qbittorrent().get_qbittorrent_torrent_list()
            new_torrent = [item for item in torrent_new_list if item not in torrent_old_list]

            if new_torrent:
                for i in new_torrent:
                    anime_title = i

                    replacements = ['[ANi] ', '[1080P]', '[Baha]', '[Nekomoe kissaten]', '[BDRip]', '[JPSC]',
                                    '.mp4', '[WEB-DL]', '[AAC AVC]', '[CHT]', '[Bilibili]', '[CHT CHS]', '（仅限港澳台）']
                    anime_title = str(anime_title)
                    for item in replacements:
                        anime_title = anime_title.replace(item, '')

                    
                    anime_title = converter.convert(anime_title)
                    robot(f'已获取 - {anime_title}')
                    Log().write_log(f'已获取新番剧 - {anime_title}', 'info')

                torrent_old_list = torrent_new_list
            else:
                if len(torrent_new_list) < len(torrent_old_list):
                    torrent_old_list = torrent_new_list
                time.sleep(3)

    @staticmethod
    def get_Rss():
        Log().write_log('程序启动', 'info')
        while True:
            nyaa_ANI_torrent()
            time.sleep(stop_time)


def start():
    try:
        thread1 = threading.Thread(target=main().new_torrent)
        thread2 = threading.Thread(target=main().get_Rss)
        thread1.start()
        time.sleep(3)
        thread2.start()
        # robot('autoRss 启动')
    except Exception as e:
        Log().write_log(e, 'error')
        start()

start()


