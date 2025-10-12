# Webforum scraper for reddit clone like sites
# Copyright (C) 2024 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from scraper import forum_scraper
from urllib import error
from urllib.parse import urlparse, urlunparse

import json

from site_user import site_user

class redditlike_scraper(forum_scraper):
    def __init__(self, site_url, database_name = None, username_prefix = '@'):
        return super().__init__(site_url, database_name)
        self.username_prefix = username_prefix

    def is_logged_in(self):
        try: 
            # if we try to open the login page it should redirect us to the homepage
            login_page = self.site_url() + 'login'
            login_response = self.browser.open(login_page)
            current_path = urlparse(login_response.geturl()).path
            return current_path == '/' or current_path == ''
        except error.HTTPError as e:
            print(f'Error accessing {e.geturl()}: {e.reason}:  {e.status}.')
        return False

    def login_from_credentials(self, username, passwd):
        login_page = self.site_url() + 'login/'
        try:
            self.browser.open(login_page)
        except error.HTTPError as e:
            if e.code == 403:
                print(f'Recieved {e.code}: {e.reason} when trying to access login page at {login_page}')
            raise
        
        self.browser.select_form(nr = 0)
        self.browser["username"] = username
        self.browser["password"] = passwd
        
        login_response = self.browser.submit()
        return login_response.geturl() == self.site_url()
    
    def get_profile_url(self, username):
        return f'{self.site_url()}{self.username_prefix}{username}/comments/'
    
    def get_profile_comment_page_url(self, username, i):
        return f'{self.site_url()}{self.username_prefix}{username}/comments?page={str(i)}'
    
    def get_profile_max_page(self, soup):
        return self.get_search_max_page(soup)
    
    def get_search_max_page(self, soup):
        max_page = 1 # iterate over next page buttons, [1][2][3][...][max_page]
        for link in soup.find('ul', attrs = {'class' : 'pagination'}).findAll('a', attrs = {'class' : 'page-link'}):
            try:
                max_page = max(int(link.text), max_page)
            except ValueError:
                continue
        return max_page
    
    def get_search_comment_page_url(self, username, i = None):        
        return f'{self.site_url()}search/comments/?q=author%3A{username}' + (f'&page={i}' if i else '')
    
    def get_comment_bodies(self, soup):
        return soup.findAll('div', attrs = {'class' : 'comment-body'})
    
    def get_commenter_info(self, comment_body_soup) -> site_user:
        commenter = comment_body_soup.find('div', attrs = {'class' : 'user-info'}).find('a', attrs = {'class' : 'user-name'})
        if not commenter: # anonymous comment
            commenter_meta = { 'username' : 'Anonymous', 'id': '0', 'original_usernames': '' }
        else:
            commenter_meta = json.loads(commenter['data-pop-info'])

        aliases = []
        if commenter_meta['original_usernames']:
            alias_str = commenter_meta['original_usernames'].removeprefix('Reserved Usernames:')
            reserved_names = alias_str.split(', ')
            for name in reserved_names:
                aliases.append(name.strip().removeprefix(f'{self.username_prefix}'))
    
        return site_user(commenter_meta['username'], commenter_meta['id'], aliases)
    
    def get_comment_id(self, comment_body_soup) -> int:
        comment_id_meta = comment_body_soup.find('a', attrs = {'class' : 'vertical-align'})
        return int(comment_id_meta.text.removeprefix('#'))
    
    def get_comment_url(self, comment_body_soup) -> str:
        comment_id_meta = comment_body_soup.find('a', attrs = {'class' : 'vertical-align'})
        return comment_id_meta['href']
        
    def get_comment_timestamp(self, comment_body_soup) -> int:
        comment_timestamp_meta = comment_body_soup.find('span', attrs = {'class' : 'time-stamp'})['data-onmouseover'] # timestamp(this, 'utc_unix_stamp')
        return int(comment_timestamp_meta.removeprefix('timestamp(').removesuffix(')').split()[1].replace("'", "")) # ignore "this, " -> utc_unix_stamp
            #comment_date = datetime.datetime.fromtimestamp(float(comment_date), tz = datetime.UTC)

    def get_comment_contents(self, comment_body_soup):
        return comment_body_soup.find('div', attrs = {'class' : 'comment-text'}).findAll('p')
    
    def is_contents_quote(self, p):
        return p.parent.name == 'blockquote'