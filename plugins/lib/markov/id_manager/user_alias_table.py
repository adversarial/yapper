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
    
#       alias table
#    *****************
#    *    alias      *
#    * user_id (FK)  *
#    *****************
class user_alias_table(markov_table):
    def __init__(self, 
                id,
                database: aiosqlite.Connection,
                database_filename: str,
                id_table: markov_table):
        self.user_id_table = id_table
        super().__init__(id, 'user_alias', database, database_filename)

    async def contains(self, alias):
        QUERY_CONTAINS_ALIAS = (
            f'SELECT EXISTS(SELECT rowid FROM "{self.name}" WHERE alias = ?);'
        ) 

        return bool(await super()._read(self.database, QUERY_CONTAINS_ALIAS, (alias,))[0])

    async def init(self):
        QUERY_CREATE_ALIAS_TABLE = (
           f'CREATE TABLE IF NOT EXISTS "{self.name}" ('
            'rowid INTEGER PRIMARY KEY AUTOINCREMENT, '
            'alias TEXT, '
            'user_id INTEGER, '
           f'FOREIGN KEY (user_id) REFERENCES "{self.user_id_table.name}" (user_id) ON DELETE CASCADE'
            ');'
        )

        await super().insert(QUERY_CREATE_ALIAS_TABLE)

    async def _internal_insert(self, connection, user_id, aliases, commit = False):
        QUERY_ADD_USER_ALIAS = (
           f'INSERT INTO "{self.name}" '
            '(alias, user_id) '
            'VALUES (?, ?)'
        )

        if not isinstance(aliases, Iterable):
            aliases = (aliases,)

        for alias in aliases:
            await self._write(connection, QUERY_ADD_USER_ALIAS, (alias, user_id))
        
        if commit:
            await connection.commit()

    async def insert(self, user_id, aliases, buffer_size):
        await self._internal_insert(self._get_handle(), user_id, aliases, True)

    # no args -> enumerates all in (alias, user_id) pairs
    # both args -> bool if contains
    # user_id -> enumerates aliases of a user_id in (alias, user_id) pairs
    # alias -> enumerate user_ids of an alias in (alias, user_id) pairs
    # 
    # can be used to enumerate aliases by matching user_id and vice versa
    # or be used to enumerate all or check if record exists
    async def query(self, alias = None, user_id = None, case_sensitive = True):

        QUERY_ENUMERATE_ALIASES = (
            f'SELECT alias, user_id FROM "{self.name}";'
        )

        QUERY_HAS_ALIAS = (
            'SELECT EXISTS(SELECT alias, user_id '
            f'FROM "{self.name}") '
            'WHERE alias = ?'
            'AND user_id = ?'
            ');'
        )

        QUERY_SEARCH_USERID = (
            f'SELECT alias FROM "{self.name}" WHERE user_id = ?;'
        )

        QUERY_HAS_ALIAS_NOCASE = (
            'SELECT EXISTS(SELECT alias, user_id '
            f'FROM "{self.name}") '
            'WHERE alias = ? COLLATE NOCASE '
            'AND user_id = ? '
            ');'
        )

        QUERY_SEARCH_ALIAS = (
            'SELECT alias, user_id '
            f'FROM "{self.name}" '
            'WHERE alias = ?;'
        )

        if not user_id and not alias:
            return super().query(QUERY_ENUMERATE_ALIASES)
        elif alias and user_id:
            return (await super().query(QUERY_HAS_ALIAS if case_sensitive else QUERY_HAS_ALIAS_NOCASE, (alias, user_id))) is not None
        elif user_id:
            return super().query(QUERY_SEARCH_USERID, (user_id,))
        elif alias:
            return super().query(QUERY_SEARCH_ALIAS, (alias,)) 