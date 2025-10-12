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

#    message_id table
#  *******************
#  * message_id (PK) *
#  * user_id         *
#  *******************
class message_id_table(markov_table):
    def __init__(self, 
                id,
                database: aiosqlite.Connection,
                database_filename: str,
                user_id_table: markov_table):
        super().__init__(id, 'message_id', database, database_filename)
        self.user_id_table = user_id_table

    async def init(self):

        QUERY_CREATE_ID_TABLE = (
           f'CREATE TABLE IF NOT EXISTS "{self.name}" ('
            'rowid INTEGER PRIMARY KEY AUTOINCREMENT, ' 
            'message_id INTEGER UNIQUE, '
            'user_id INTEGER, '
           f'FOREIGN KEY (user_id) REFERENCES "{self.user_id_table.name}" (user_id) ON DELETE CASCADE'
            ');'
        )

        await super().insert(QUERY_CREATE_ID_TABLE)

    async def contains(self, message_id, user_id = None):
        QUERY_CONTAINS_MESSAGE_ID = (
            f'SELECT EXISTS(SELECT rowid FROM "{self.name}" WHERE message_id = ?);'
        ) # (seed,)

        QUERY_USERID_CONTAINS_MESSAGEID = (
            f'SELECT EXISTS(SELECT rowid FROM "{self.name}" '
            'WHERE message_id = ? '
            'AND user_id = ?)'
            ';'
        )

        return any(await super().query(QUERY_USERID_CONTAINS_MESSAGEID if user_id else QUERY_CONTAINS_MESSAGE_ID,
                                    (message_id, user_id) if user_id else (message_id,),))

    async def _internal_insert(self, connection, messages_users_ids, commit = False):
        QUERY_ADD_MESSAGE = (
            f'INSERT OR IGNORE INTO "{self.msg_id_table.name}" '
            '(message_id, user_id) '
            'VALUES (?, ?)'
            ';'
        )

        if not isinstance(messages_users_ids, Iterable):
            messages_users_ids = (messages_users_ids,)

        for message_id, user_id in messages_users_ids:
            async with super()._write(connection, QUERY_ADD_MESSAGE, (message_id, user_id)):
                pass
        if commit:
            await connection.commit()

    # silently fails on duplicate
    # pass (message_id, user_id) pairs
    async def insert(self, messages_users_ids):
        async with self._get_handle() as connection:
            await self._internal_insert(connection, messages_users_ids, commit = True)

    # returns iterable of message_ids assosciated with user_id or all ids if None
    async def query(self, user_id = None, buffer_size = BUFFER_SIZE):
        QUERY_GET_MESSAGES = (
            'SELECT (message_id) '
           f'FROM "{self.name}"'
           ';'
        )

        QUERY_GET_USER_MESSAGES = (
            'SELECT (message_id) '
           f'FROM "{self.name}" '
            'WHERE user_id = ?'
            ';'
        )

        return await super().query(QUERY_GET_USER_MESSAGES if user_id else QUERY_GET_MESSAGES,
                                   (user_id,) if user_id else None,
                                   BUFFER_SIZE)