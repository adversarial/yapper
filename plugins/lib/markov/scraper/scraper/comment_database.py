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

import sqlite3
import contextlib
from time import sleep
from collections import namedtuple

def open_cursor(query) -> sqlite3.Cursor:
    return contextlib.closing(query)


comment_result = namedtuple('comment_result', ['text', 'timestamp', 'id', 'url'])

class comment_database:
    MAX_RETRIES = 10
    BUFFER_SIZE = 1000

    def __init__(self, database_file, site_name):
        self.database_file = database_file
        self.database = sqlite3.connect(database_file)
        self.site_name = site_name
        self.user_table_name = f'{site_name}_users'
        self.alias_table_name = f'{site_name}_aliases'
        self.comment_table_name = f'{site_name}_comments'

        self._create_user_table()
        self._create_alias_table()
        self._create_comment_table()
        self.database.commit()

    def close(self):
        self.database.close()

    def _create_user_table(self):
        QUERY_CREATE_TABLE = (
            f'CREATE TABLE IF NOT EXISTS "{self.user_table_name}" ('
             'rowid INTEGER PRIMARY KEY AUTOINCREMENT, ' 
             'user_id INTEGER UNIQUE '
             ');'
        )

        with open_cursor(self.database.execute(QUERY_CREATE_TABLE)) as cursor:
            pass

    def _create_alias_table(self):
        QUERY_CREATE_TABLE = (
            f'CREATE TABLE IF NOT EXISTS "{self.alias_table_name}" ('
             'rowid INTEGER PRIMARY KEY AUTOINCREMENT, '
             'alias TEXT UNIQUE, '
             'user_id INTEGER, '
             f'FOREIGN KEY (user_id) REFERENCES "{self.user_table_name}" (user_id) ON DELETE CASCADE'
             ');'
        )
        with open_cursor(self.database.execute(QUERY_CREATE_TABLE)) as cursor:
            pass

    def _create_comment_table(self):
        QUERY_CREATE_TABLE = (
            f'CREATE TABLE IF NOT EXISTS "{self.comment_table_name}" ('
             'rowid INTEGER PRIMARY KEY AUTOINCREMENT, ' 
             'comment_text TEXT, '
             'comment_timestamp INTEGER, '
             'comment_id INTEGER UNIQUE, '
             'comment_url TEXT, '
             'user_id INTEGER, '
            f'FOREIGN KEY (user_id) REFERENCES "{self.user_table_name}" (user_id) ON DELETE CASCADE'
             ');'
        )
        with open_cursor(self.database.execute(QUERY_CREATE_TABLE)) as cursor:
            pass

    def commit(self):
        for i in range(self.MAX_RETRIES):
            try:
                self.database.commit()
                break
            except:
                print('Database is locked or unavailable, waiting 15 seconds and retrying.')
                sleep(15.0)
                continue

    def add_user(self, userid, username, aliases = []):

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

        with open_cursor(self.database.execute(
                            QUERY_ADD_USER, 
                            (userid,))
                        ) as cursor:
            pass

        with open_cursor(self.database.execute(
                            QUERY_ADD_ALIAS, 
                            (userid, username))
                        ) as cursor:
            pass

        for name in aliases:
            with open_cursor(self.database.execute(
                                QUERY_ADD_ALIAS,
                                (userid, name))
                            ) as cursor:
                pass

    def add_comment(self, userid, comment_text, comment_timestamp, comment_id, comment_url):
        
        QUERY_ADD_COMMENT = (
            f'INSERT OR IGNORE INTO "{self.comment_table_name}" '
             '(comment_text, comment_timestamp, comment_id, comment_url, user_id) '
             'VALUES (?, ?, ?, ?, ?);'
        )
        with open_cursor(self.database.execute(
                            QUERY_ADD_COMMENT, 
                            (comment_text, comment_timestamp, comment_id, comment_url, userid))
                        ) as cursor:
            pass

    def get_comments_by_id(self, userid: int, buffer_size = BUFFER_SIZE):

        QUERY_GET_USERID_COMMENTS = (
             'SELECT comment_text, comment_timestamp, comment_id, comment_url '
            f'FROM "{self.comment_table_name}" '
             'WHERE user_id = ?;'
        )

        with open_cursor(self.database.execute(
                            QUERY_GET_USERID_COMMENTS, 
                            (userid,))
                        ) as cursor:
            while(results := cursor.fetchmany(buffer_size)):
                for result in results:
                    yield result
            
    def get_comments_by_username(self, username: str, buffer_size = BUFFER_SIZE):

        QUERY_GET_USERNAME_COMMENTS = (
             'SELECT comment_text, comment_timestamp, comment_id, comment_url '
            f'FROM "{self.comment_table_name}" '
            f'WHERE user_id = (SELECT "{self.alias_table_name}".user_id '
                             f'FROM "{self.alias_table_name}" '
                             #f'JOIN "{self.alias_table_name}" ON "{self.alias_table_name}".user_id '
                              'WHERE alias = ? '
                              ');'
        )

        with open_cursor(self.database.execute(
                            QUERY_GET_USERNAME_COMMENTS, 
                            (username,))
                        ) as cursor:
            while(results := cursor.fetchmany(buffer_size)):
                for result in results:
                    yield comment_result(result)

    def get_comment_count_by_username(self, username: str, buffer_size = BUFFER_SIZE):

        QUERY_GET_USERNAME_COMMENT_COUNT = (
                'SELECT count(*) '
            f'FROM "{self.comment_table_name}" '
            f'WHERE user_id = (SELECT "{self.alias_table_name}".user_id '
                             f'FROM "{self.alias_table_name}" '
                              'WHERE alias = ? '
                              'LIMIT 1 '
                              ');'
        )
        with open_cursor(self.database.execute(
                            QUERY_GET_USERNAME_COMMENT_COUNT, 
                            (username,))
                        ) as cursor:
            return cursor.fetchone()[0]