# markov chain message meta (id) implementation
#
# allows message meta info to be stored to prevent fetching duplicate messages
# an optional user_id and user_alias can be tagged to allow user-based markov chains
# Copyright (C) 2025 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#

import aiosqlite
from collections.abc import Iterable

from plugins.lib.markov.markov_table import markov_table, BUFFER_SIZE

#
#   ****************
#   * user_id (PK) *
#   ****************
class user_id_table(markov_table):

    def __init__(self, 
                id,
                database: aiosqlite.Connection,
                database_filename: str, 
                anonymous = False):
        super().__init__(id, 'user_id', database, database_filename)
    
    async def contains(self, user_id):
        QUERY_CONTAINS_MESSAGE_ID = (
            f'SELECT EXISTS(SELECT rowid FROM "{self.name}" WHERE user_id = ?);'
        ) 

        async with super().query(QUERY_CONTAINS_MESSAGE_ID, (user_id,)) as results:
            return any(results)

    async def init(self):

        QUERY_CREATE_USER_ID_TABLE = (
            f'CREATE TABLE IF NOT EXISTS "{self.name}" '
            'rowid INTEGER PRIMARY KEY AUTOINCREMENT, '
            'user_id INTEGER UNIQUE '
            ');'
        )

        await super().insert(QUERY_CREATE_USER_ID_TABLE)

    async def _internal_insert(self, connection, user_ids, commit = False):
        QUERY_ADD_USER_ID = (
            f'INSERT OR IGNORE INTO "{self.name}" '
            '(user_id) '
            'VALUES (?);'
        )

        if not isinstance(user_ids, Iterable):
            user_ids = (user_ids,)
        
        for user_id in user_ids:
            async with super()._write(connection, QUERY_ADD_USER_ID, (user_id)):
                pass
        if commit:
            async with connection.commit():
                pass

    async def insert(self, user_ids):
        await self._internal_insert(self._get_handle(), user_ids, commit = True)

    async def query(self, user_id = None, buffer_size = BUFFER_SIZE):
        QUERY_GET_USERS = (
            'SELECT (user_id) '
           f'FROM "{self.name}" '
            ';'
        )

        QUERY_GET_USERS_WITH_USERID = (
            'SELECT (user_id) '
            f'FROM "{self.name}" '
            'WHERE user_id = ? '
            ';'
        )

        return super().query(QUERY_GET_USERS_WITH_USERID if user_id else QUERY_GET_USERS, 
                            (user_id if user_id else None, ), 
                            BUFFER_SIZE)