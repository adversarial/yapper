# markov chain SQLite table schemas
# Copyright (C) 2024 adversarial

# init: pass a unique <id>      used as exclusive ID
#                     <name>,   name for output
#                     <connection> ie aoisqlite.connect(<database_filename>)
#                     [database filename] a name for the database file

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import aiosqlite
from plugins.lib.markov.markov_table import markov_table
from plugins.lib.markov.id_manager.id_manager import message_id_table

class seed_table(markov_table):
    def __init__(self, 
                 id,
                 database: aiosqlite.Connection,
                 database_filename: str,
                 msg_id_table: message_id_table):
        super().__init__(id, 'seed', database, database_filename)
        self.msg_id_table = msg_id_table


    async def contains(self, seed, user_id = None):
        QUERY_CONTAINS_SEED = (
            f'SELECT EXISTS(SELECT rowid FROM "{self.name}" WHERE seed = ?);'
        ) # (seed,)

        if user_id is not None:
            pass
        #return (await self.query(QUERY_USERID_CONTAINS_SEED, (seed,  user_id)))[0]
        else:
            return (await self.query(QUERY_CONTAINS_SEED, (seed,)))[0]

    async def init(self):

        QUERY_CREATE_SEED_TABLE = (
           f'CREATE TABLE IF NOT EXISTS "{self.name}" ('
            'rowid INTEGER PRIMARY KEY AUTOINCREMENT, ' 
            'seed TEXT UNIQUE, '
            'message_id INTEGER '
           f'FOREIGN KEY (message_id) REFERENCES "{self.msg_id_table.name}" (message_id) ON DELETE CASCADE'
            ');'
        )

        await self.insert(QUERY_CREATE_SEED_TABLE)

class next_state_table(markov_table):
    def __init__(self, id, database, database_filename, seed_table: markov_table):
        self.seed_table = seed_table
        super().__init__(id, 'next_states', database, database_filename)
    
    # value should be a tuple ('key', 'value')
    # def __contains__(self, value):
    async def contains(self, value, database):
        QUERY_CONTAINS_NEXT_STATE = (
            f'SELECT EXISTS(SELECT rowid FROM "{self.name}" '
             'WHERE next_state = ? '
            f'AND seed_id = (SELECT DISTINCT rowid FROM "{self.seed_table.name}" WHERE seed = ?));'
        ) # (seed,)

        seed, next_state = value
        async with database.execute(QUERY_CONTAINS_NEXT_STATE, (next_state, seed)) as cursor:
            return bool((await cursor.fetchone())[0])
        
    async def init(self):

        QUERY_CREATE_NEXT_STATE_TABLE = (
            f'CREATE TABLE IF NOT EXISTS "{self.name}" ('
             'rowid INTEGER PRIMARY KEY AUTOINCREMENT, '
             'hash TEXT UNIQUE, '
             'next_state TEXT, '
             'count INTEGER, '
             'seed_id INTEGER, '
            f'FOREIGN KEY (seed_id) REFERENCES "{self.seed_table.name}" (rowid)'
            ');'
        )

        await self.insert(QUERY_CREATE_NEXT_STATE_TABLE)