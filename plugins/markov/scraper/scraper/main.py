# Entrypoint (main) file for webforum scraper
# Copyright (C) 2024 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

from configparser import ConfigParser
import argparse

from redditlike_scraper import redditlike_scraper

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='razor - a web forum scraper',
                                 description='Modular web forum scraper.')
    parser.add_argument('configfilename', nargs = '?', default = 'config.ini', help = 'Specify an optional config file.')
    args = parser.parse_args()

    config = { }
    configfile = ConfigParser()
    configfile.read(args.configfilename)

    config['site_url'] = configfile['Url']['website']
    config['username'] = configfile['Login']['username']
    config['password'] = configfile['Login']['password'] or None
    config['target_username'] = configfile['Target']['username']
    config['database_filename'] = configfile['Database']['filename'] or None

    scraper = redditlike_scraper(site_url = config['site_url'], database_name = config['database_filename'])
    scraper.login(config['username'], config['password'] or None)
    scraper.scrape_user_comments(config['target_username'])
    
    print('Completed.')

#   for comment in scraper.database.get_comments_by_username(config['target_username']):
#        print(comment.text)
#    print(scraper.database.get_comment_count_by_username(config['target_username']))