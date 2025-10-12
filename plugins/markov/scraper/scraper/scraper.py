# Abstract base class for webforum scraper
# Copyright (C) 2024 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import mechanize, http.cookiejar
from bs4 import BeautifulSoup

import json
import random
import datetime, dateutil
from urllib import error
from urllib.parse import urlparse, urlunparse
from time import sleep
from email.utils import parsedate_to_datetime
from typing import Type

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:53.0) Gecko/20100101 Firefox/53.0",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.0; Trident/5.0; Trident/5.0)",
    "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.2; Trident/6.0; MDDCJS)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.79 Safari/537.36 Edge/14.14393"
]

referers = [
    "https://www.google.com",
    "https://www.bing.com",
    "https://www.duckduckgo.com",
    "https://www.yandex.ru"
]

from comment_database import comment_database
from site_user import site_user

# abstract base class for site-specific scrapers
class forum_scraper:

    def site_name(self):
        return self._site_name
    
    def site_url(self) -> str:
        return self._site_url
    
    def is_logged_in(self):
        raise NotImplementedError

    def login_from_credentials(self, username, passwd):
        raise NotImplementedError
    
    def get_profile_url(self, username):
        raise NotImplementedError
    
    def get_profile_comment_page_url(self, username, i):
        raise NotImplementedError
    
    def get_search_comment_page_url(self, username, i = None):
        raise NotImplementedError

    def get_search_max_page(self, soup):
        raise NotImplementedError
    
    def get_comment_bodies(self, soup):
        raise NotImplementedError

    def get_commenter_info(self, comment_body_soup) -> site_user:
        raise NotImplementedError
    
    def get_comment_url(self, comment_body_soup) -> str:
        raise NotImplementedError

    def get_comment_id(self, comment_body_soup) -> int:
        raise NotImplementedError

    def get_comment_timestamp(self, comment_body_soup) -> int:
        raise NotImplementedError
    
    def get_comment_contents(self, comment_body_soup):
        raise NotImplementedError
    
    def is_contents_quote(self, p):
        raise NotImplementedError
    
    def __init__(self, site_url: str, database_name = None):
        self.browser: mechanize.Browser = mechanize.Browser()
        self.browser.set_handle_robots(False)
        self.browser.addheaders = [('User-Agent', random.choice(user_agents)), ('Referer', random.choice(referers)) ]

        # override to change how many times a page that returns an error is retried
        self.MAX_RETRIES = 10
        # override to change default delay when given 429: ERROR TOO MANY REQUESTS is sent without a requested time
        self.RETRY_DELAY = 15.0 # seconds
        self.MAX_REQUESTED_RETRY_DELAY = 1000.0 # seconds

        # override to change how often pages are requested
        self.REQUEST_DELAY = 15.0 # seconds

        # '/' ending in url
        self._site_url = site_url if urlparse(site_url).path else site_url + "/"
        self._site_name = urlparse(site_url).hostname.split('.')[-2] # can be in form 'www.site.com' or 'site.com' and will retrieve 'site'

        self.database = comment_database(f'{database_name or self.site_name()}.db', self.site_name())

        self.logged_in_user = None

    def login(self, username, passwd = None):
        self.cookie_file = f'{username}-cookie.txt'
        self.cookies = http.cookiejar.LWPCookieJar(self.cookie_file)
        self.browser.set_cookiejar(self.cookies)

        if self.login_from_cookie(username):
            print(f'Logged via cookie as {username}.')
            self.logged_in_user = username
            return True
        else:
            if not passwd:
                raise ValueError('Error logging in: password not supplied.')
            if self.login_from_credentials(username, passwd):
                self.browser.cookiejar.save(self.cookie_file, ignore_discard = True, ignore_expires = True)
                self.logged_in_user = username
                print(f'Logged in via credentials as {username}.')
                return True
            else:
                print(f'Could not log in as {username}.')
                raise ValueError(f'Error logging in as {username}: incorrect credentials.')

    def login_from_cookie(self, username):
        try:
            self.browser.cookiejar.load(ignore_discard = True, ignore_expires = True)
            return self.is_logged_in()
        except (OSError, http.cookiejar.LoadError) as e:
            print(f'Could not open cookie file {self.cookie_file}, error {e.errno}: {e.strerror}')
        return False

    def scrape_user_comments(self, username, detailed = False):
        if not self.logged_in_user:
            raise AssertionError('User profiles can only be accessed when logged in.')
        
        search_url = self.get_search_comment_page_url(username)
        #search_url = self.get_profile_url(username)
        for i in range(self.MAX_RETRIES):
            try:
                profile_response = self.browser.open(search_url)
                break
            except error.HTTPError as e:
                if e.code == 403:
                    print('This profile is private.')
                    raise
                elif e.code == 429:
                    self._handle_too_many_requests(e, i)
                    continue
                elif e.code == 404:
                    print(f'{e.code}: {e.status} encountered when searching {username}.')
                    raise

        user_comment_soup = BeautifulSoup(profile_response.read(), features = 'html5lib')
        max_page = self.get_search_max_page(user_comment_soup)
        
        print(f'{username} has {max_page} pages of comments...')
        for i in range(1, max_page + 1):
            sleep(self.REQUEST_DELAY * (random.random() * 0.5))
            print('.', end = '')
            page_url = self.get_search_comment_page_url(username, i)
            #page_url = self.get_profile_comment_page_url(username, i)
            self._parse_comment_page(page_url, detailed = detailed)
        print('\nParsing comments complete.')
    
    def _scrape_comment_callback(self, comment_text: str, comment_date: int, comment_id: int, comment_url: str, commenter_info: site_user):
        self.database.add_user(commenter_info.id, commenter_info.name, commenter_info.aliases)
        self.database.add_comment(commenter_info.id, comment_text, comment_date, comment_id, comment_url)

    def _parse_comment_contents(self, soup_item):
        extract = []
        if soup_item.text:
            extract.append(soup_item.text)
        elif soup_item.has_attr('href'): # <a/img href=<url> >
            extract.append(soup_item['href'])
        elif soup_item.has_attr('src'): # <img src=<path> >
            extract.append(soup_item['src'])
        elif soup_item.has_attr('alt'): # <img alt=<name> >
            extract.append(soup_item['alt'])
        elif soup_item.name == 'lite-youtube': # <lite-youtube videoid=123456abc>
            extract.append(f'youtube.com/watch?v={soup_item['videoid']}')
        elif soup_item.name == 'span':   # ignore formatting
            for i in soup_item.contents:
                extract += self._parse_comment_contents(i)
        else:
            extract.append('☐')
        return extract

    def _parse_comment_page(self, page_url, comment_callback = _scrape_comment_callback, detailed = False):
        retries = 10
        for i in range(retries):
            try:
                page_response = self.browser.open(page_url)
                break
            except error.HTTPError as e:
                self._handle_too_many_requests(e, i)
                continue

        comment_soup = BeautifulSoup(page_response.read(), features = 'html5lib')
        comment_bodies = self.get_comment_bodies(comment_soup)

        for c in comment_bodies:
            commenter_info = self.get_commenter_info(c)
            comment_url = self.get_comment_url(c)
            comment_id = self.get_comment_id(c)
            comment_date = self.get_comment_timestamp(c)

            comment_text = [ ]
            for p in self.get_comment_contents(c):
                contents = []
                for item in p.contents:
                    extract = self._parse_comment_contents(item)
                    contents += extract
                contents = ' '.join(contents)
                if self.is_contents_quote(p):
                    contents = f'> "{contents}"'
                comment_text.append(contents)
            comment_text = '\n'.join(comment_text)
            comment_callback(self, comment_text, comment_date, comment_id, comment_url, commenter_info)
        self.database.commit()

    def _handle_too_many_requests(self, e: error.HTTPError, i = 0):
        retry_after = self.RETRY_DELAY
        if hasattr(e, 'headers'):
            requested_delay = e.headers.get('Retry-After')
            if requested_delay:
                try:
                    retry_after = int(requested_delay) 
                except ValueError: # wasn't seconds
                    try:
                        retry_after = (parsedate_to_datetime(requested_delay).astimezone(dateutil.tzlocal()) - datetime.datetime.now()).total_seconds()
                        if retry_after < 1 or retry_after > 10000:
                            retry_after = self.RETRY_DELAY
                    except: # wasnt a valid timestamp
                        pass
        retry_after = retry_after * (2 ** i)
        print(f'Error accessing {e.geturl()}: {e.reason} ({e.status}) trying again in {retry_after} seconds.')
        sleep(retry_after * (random.random() + 0.5))  # Exponential backoff
