# markov chain SQLite backend
# Copyright (C) 2024 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

###################################################################################
# SQL implementation
###################################################################################
import aiosqlite
import typing
import contextlib
import json
import hashlib
import random

from plugins.lib.markov.markov_table import markov_table
from markov_brain_table import seed_table, next_state_table
from plugins.lib.markov.id_manager.id_manager import markov_id_manager

class markov_brain:
    def __init__(self,
                 id,
                 database: aiosqlite.Connection,
                 database_filename = None,
                 max_entries = None,
                 copy_seed_table_name = None,
                 copy_next_state_table_name = None):
        self._id = id
        self.database = database
        self.database_filename = database_filename
        self.max_entries = max_entries
        self._lock = contextlib.nullcontext()

        self.copy_seed_table_name = copy_seed_table_name
        self.copy_next_state_table_name = copy_next_state_table_name

        self.seed_table = seed_table(id, database, database_filename)
        self.next_state_table = next_state_table(id, database, database_filename, self.seed_table)

        self.id_manager = markov_id_manager(id, self.database, self.database_filename)        

    async def init(self):
        await self.id_manager.init()
        await self.seed_table.init()
        await self.next_state_table.init()
        if self.copy_seed_table_name and self.copy_next_state_table_name:
            await self._copy(self.copy_seed_table_name, self.copy_next_state_table_name)       
    
    #def __contains__(self, seed):
    #    return seed in self.seed_table
    async def contains(self, seed, user_id = None):
        return await self.seed_table.contains(seed, user_id)

    # multiple threads can use a read connection
    async def _execute_read(self, connection: aiosqlite.Connection, statement, args: typing.Optional[tuple] = None):
        async with connection.execute(statement, parameters = args) as cursor:
            return await cursor.fetchall()
    
    # only one thread can use a write connection though
    # open a connection in the top level function and pass to here
    # call commit at end of procedure that uses this
    async def _execute_write(self, connection: aiosqlite.Connection, statement, args: typing.Optional[tuple] = None):
        async with connection.execute(statement, parameters = args):
            pass
    
    async def _copy(self, source_seed_table_name, source_next_states_table_name):
        QUERY_COPY_SEEDS = (
            f'INSERT INTO "{self.seed_table.name}" (seed) '
            f'SELECT seed FROM "{source_seed_table_name}";'
        ) 

        QUERY_COPY_NEXT_STATES = (
            f'INSERT INTO "{self.next_state_table.name}" (hash, next_state, count, seed_id) '
            f'SELECT hash, next_state, count, seed_id FROM "{source_next_states_table_name}";'
        )

        async with aiosqlite.connect(self.database_filename) as database:
            async with database.executescript(f'DELETE FROM {self.seed_table.name}; DELETE FROM {self.next_state_table.name};'):
                pass
            await database.commit()
            async with database.executescript(QUERY_COPY_SEEDS + QUERY_COPY_NEXT_STATES):
                pass
            await database.commit()
            
    async def _dbg(self):
        print(await self._execute_read(self.database, f'SELECT rowid, seed FROM "{self.seed_table.name}";'))
        print(await self._execute_read(self.database, f'SELECT next_state, count, seed_id FROM "{self.next_state_table.name}";'))

    def id(self):
        return self._id
    
    # searching int is faster than varchar
    # use a hash as primary key. DISTINCT, not actual PK (rowid)
    def kv_hash(self, key, value):
        return hashlib.sha3_256(bytes(f"{key}:{value}", encoding='utf8'), usedforsecurity = False).hexdigest()

    # doesn't commit to allow optimization of entering lists
    async def _internal_add_next_state(self, connection: aiosqlite.Connection, key: str, value: str, msg_id = None, count: int = 1):
        QUERY_ADD_SEED = (
            f'INSERT OR IGNORE INTO "{self.seed_table.name}" (seed) VALUES (?);'
        ) # (seed,)

        QUERY_ADD_SEED_WITH_ID = (
            f'INSERT OR IGNORE INTO "{self.seed_table.name}" (seed, message_id) VALUES (?, ?);'
        )
                
        QUERY_INSERT_OR_INCREMENT_NEXT_STATE = (
            f'INSERT INTO "{self.next_state_table.name}" (hash, next_state, count, seed_id) '
            f'VALUES (?, ?, ?, (SELECT DISTINCT rowid FROM "{self.seed_table.name}" WHERE seed = ?)) '
            'ON CONFLICT(hash) '
            'DO UPDATE SET count = count + ?;'
        ) # (hash, value, count, key, count)
        
        if msg_id is None:
            await self._execute_write(connection, QUERY_ADD_SEED, args = (key,))
        else:
            await self._execute_write(connection, QUERY_ADD_SEED_WITH_ID, args = (key, msg_id))

        await self._execute_write(connection, QUERY_INSERT_OR_INCREMENT_NEXT_STATE, args = (self.kv_hash(key, value), value, count, key, count))

    async def add_next_state(self, key: str, value: str, msg_id = None, count: int = 1):
        with aiosqlite.connect(self.database_filename) as database:
            await self._internal_add_next_state(database, key, value, msg_id, count)
            await database.commit()
    
    async def get_next_states(self, key):

        QUERY_GET_NEXT_STATES = (
            f'SELECT next_state, count FROM "{self.next_state_table.name}" '
            f'WHERE seed_id = (SELECT DISTINCT rowid FROM "{self.seed_table.name}" WHERE seed = ?)'
        ) # (seed,)

        return await self._execute_read(self.database, QUERY_GET_NEXT_STATES, (key,))
  
    # import old version that used in-memory dictionary
    async def import_json(self, filename):
        with open(filename, 'r') as file:
            await self.import_chain(json.load(file))
            
    # import old version that used in-memory dictionary
    async def import_chain(self, chain):
        async with aiosqlite.connect(self.database_filename) as connection:
            for key in chain:
                # todo: batch add
                for value, count in chain[key]:
                    await self._internal_add_next_state(connection, key, value, None, count)
            await connection.commit()

    # export old version that used in-memory dictionary
    async def export_json(self, filename):

        QUERY_GET_ALL_KEYS = f'SELECT seed FROM "{self.seed_table.name}";'

        chain = { }
        keys = await self._execute_read(self.database, QUERY_GET_ALL_KEYS)
        for key in keys:
            values = await self.get_next_states(key[0])
            chain[key[0]] = values
        with open(filename, 'w+') as file:
            json.dump(chain, file)

    async def load(self):
        await self.database.rollback()

    async def dump(self):
        await self.database.commit()

    async def remove(self):
        async with aiosqlite.connect(self.database_filename) as database:
            async with database.executescript(f'DROP TABLE "{self.next_state_table.name}"; DROP TABLE "{self.seed_table.name}";'):
                await database.commit()

    async def reset(self):
        await self.seed_table._clear()
        await self.next_state_table._clear()

    async def get_random_seed(self):

        QUERY_GET_RANDOM_SEED = (
            f'SELECT seed FROM "{self.seed_table.name}" ORDER BY random() LIMIT 1;'
        )

        result = await self._execute_read(self.database, QUERY_GET_RANDOM_SEED)
        if result is not None:
            return result[0][0]
    
    async def get_fuzzy_seed(self, seed, seperator, is_prefix_only = False):

        QUERY_GET_FUZZY_SEED = (
            f'SELECT seed FROM "{self.seed_table.name}" WHERE seed LIKE ? ORDER BY random() LIMIT 1;'
        )

        if random.randint(0, 1) > 0:
            search_str1 = seed + seperator + '_%'
            search_str2 = '%_' + seperator + seed
        else:
            search_str1 = '%_' + seperator + seed
            search_str2 = seed + seperator + '_%'
    
        result = await self._execute_read(self.database, QUERY_GET_FUZZY_SEED, (search_str1,))
        if not result:
            result = await self._execute_read(self.database, QUERY_GET_FUZZY_SEED, (search_str2,))
            if not result:
                raise KeyError
        return result[0][0]

    # because all seeds are unique and don't store a count this isn't an actual markov chain function
    async def get_previous_state(self, seed, forward_seed, seperator, message_id = None):

        QUERY_GUESS_PREVIOUS_SEED = (
           f'SELECT rowid, seed FROM "{self.seed_table.name}" '
            'WHERE seed LIKE ? '
            'AND EXISTS(SELECT next_state '
                       f'FROM "{self.next_state_table.name}" '
                        'WHERE next_state = ? '
                        'AND seed_id = rowid) '
            'ORDER BY random() '
            'LIMIT 1;'
        )

        results = await self._execute_read(self.database, QUERY_GUESS_PREVIOUS_SEED, ('%_' + seperator + seed, forward_seed))
        if not results:
            raise KeyError
        return results[0][1]
