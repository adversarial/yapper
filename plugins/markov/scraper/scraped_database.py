# Comment database handler for web scraper
# Copyright (C) 2024 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.            

# alias and comment table point to user_id table primary key
# 

import aiosqlite
from time import sleep
from collections import namedtuple

from plugins.lib.markov.markov_table import markov_table

comment_result = namedtuple('comment_result', ['text', 'timestamp', 'id', 'url', 'user_id'])
alias_result = namedtuple('alias_result', ['user_id', 'alias_name'])

class scraped_database_table(markov_table):
    MAX_RETRIES = 10
    BUFFER_SIZE = 1000

    def __init__(self, database_filename, group_name):
        super().__init__(id = database_filename, )
        self.database_filename = database_filename
        self.database = aiosqlite.connect(self.database_filename)
        self.group_name = group_name
        self.user_table_name = f'{group_name}_users'
        self.alias_table_name = f'{group_name}_aliases'
        self.comment_table_name = f'{group_name}_comments'

    def close(self):
        self.database.close()

    def commit(self):
        for i in range(self.MAX_RETRIES):
            try:
                self.database.commit()
                break
            except:
                print('Database is locked or unavailable, waiting 15 seconds and retrying.')
                sleep(15.0)
                continue

    async def add_user(self, userid, username, aliases = []):

        QUERY_ADD_USER = (
            f'INSERT OR IGNORE INTO "{self.user_table_name}" '
             '(user_id) '
             'VALUES (?);'
        )

        QUERY_ADD_ALIAS = (
            f'INSERT OR IGNORE INTO "{self.alias_table_name}" '
             '(user_id, alias) '
             'VALUES (?, ?);'
        )

        async with self.database.execute(
                            QUERY_ADD_USER, 
                            (userid,)
                            ):
            pass

        async with self.database.execute(
                            QUERY_ADD_ALIAS, 
                            (userid, username)
                        ):
            pass

        for name in aliases:
            async with self.database.execute(
                                QUERY_ADD_ALIAS,
                                (userid, name)
                            ):
                pass

    async def add_comment(self, userid, comment_text, comment_timestamp, comment_id, comment_url):
        
        QUERY_ADD_COMMENT = (
            f'INSERT OR IGNORE INTO "{self.comment_table_name}" '
             '(comment_text, comment_timestamp, comment_id, comment_url, user_id) '
             'VALUES (?, ?, ?, ?, ?);'
        )
        async with self.database.execute(
                            QUERY_ADD_COMMENT, 
                            (comment_text, comment_timestamp, comment_id, comment_url, userid)
                        ):
            pass

    async def get_comments_by_id(self, userid: int, buffer_size = BUFFER_SIZE):

        QUERY_GET_USERID_COMMENTS = (
             'SELECT (comment_text, comment_timestamp, comment_id, comment_url, user_id) '
            f'FROM "{self.comment_table_name}" '
             'WHERE user_id = ?;'
        )

        async with self.database.execute(
                            QUERY_GET_USERID_COMMENTS, 
                            (userid,)
                        ) as cursor:
            while(results := cursor.fetchmany(buffer_size)):
                for result in results:
                    yield result
            
    async def get_comments_by_username(self, username: str, buffer_size = BUFFER_SIZE):

        QUERY_GET_USERNAME_COMMENTS = (
             'SELECT (comment_text, comment_timestamp, comment_id, comment_url, user_id) '
            f'FROM "{self.comment_table_name}" '
            f'WHERE user_id = (SELECT "{self.alias_table_name}".user_id '
                             f'FROM "{self.alias_table_name}" '
                             #f'JOIN "{self.alias_table_name}" ON "{self.alias_table_name}".user_id '
                              'WHERE alias = ? '
                              ');'
        )

        async with self.database.execute(
                            QUERY_GET_USERNAME_COMMENTS, 
                            (username,)
                        ) as cursor:
            while(results := cursor.fetchmany(buffer_size)):
                for result in results:
                    yield comment_result(result)

    async def get_comment_count_by_username(self, username: str, buffer_size = BUFFER_SIZE):

        QUERY_GET_USERNAME_COMMENT_COUNT = (
             'SELECT count(*) '
            f'FROM "{self.comment_table_name}" '
            f'WHERE user_id = (SELECT "{self.alias_table_name}".user_id '
                             f'FROM "{self.alias_table_name}" '
                              'WHERE alias = ? '
                              'LIMIT 1 '
                              ');'
        )
        async with self.database.execute(
                            QUERY_GET_USERNAME_COMMENT_COUNT, 
                            (username,)
                        ) as cursor:
            return cursor.fetchone()[0]

    # returns comment_result generator
    async def enumerate_comments(self, buffer_size = BUFFER_SIZE):

        QUERY_GET_COMMENTS = (
            'SELECT * '
           f'FROM "{self.comment_table_name} '
            ');'
        )

        async with self.database.execute(
                            QUERY_GET_COMMENTS
        ) as cursor:
            while(results := cursor.fetchmany(buffer_size)):
                for result in results:
                    yield result

    # returns alias_result generator
    async def enumerate_aliases(self, buffer_size = BUFFER_SIZE):

        QUERY_GET_ALIASES = (
            'SELECT alias, user_id '
           f'FROM "{self.alias_table_name}" '
            ');'
        )

        async with self.database.execute(
                            QUERY_GET_ALIASES
        ) as cursor:
            while(results := cursor.fetchmany(buffer_size)):
                    for result in results:
                        yield result
