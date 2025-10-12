# markov chain SQLite table schemas base class
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
import typing

BUFFER_SIZE = 1024

class markov_table:
    TABLE_BASE_NAME = 'markov'

    def __init__(self, 
                 id,
                 name,
                 database: aiosqlite.Connection,
                 database_filename: str):
        self.name = str(id) + markov_table.TABLE_BASE_NAME + name
        self.database = database
        self.database_filename = database_filename

    async def __contains__(self, **kwargs):
        raise NotImplementedError

    # useful for async variable initialization
    async def init(self):
        pass
    
    async def _drop(self):
        QUERY_DROP_TABLE = ( 
            f'DROP TABLE "{self.name}";'
        )

        await self.insert(QUERY_DROP_TABLE)

    async def _clear(self):
        QUERY_CLEAR_TABLE = (
            f'DELETE FROM "{self.name}";'
        )

        await self.insert(QUERY_CLEAR_TABLE)

    # default read statement
    # statement: string of sqlite
    # args: tuple of values
    async def query(self, statement, args: typing.Optional[tuple] = None, buffer_size = BUFFER_SIZE):
        async with self.database.execute(statement, parameters = args) as cursor:
            while(results := cursor.fetchmany(buffer_size)):
                for result in results:
                    yield result

    # default write statement
    # due to sqlite being meant for single thread app, should open a new handle every write commit to ensure integrity
    async def insert(self, statement, args: typing.Optional[tuple] = None):
        async with self._get_handle() as connection:
            async with self._write(connection, statement, args) as cursor:
                cursor.commit()
        
        #async with aiosqlite.connect(self.database_filename) as database:
        #    async with database.execute(statement, parameters = args):
        #        await database.commit()

    # multiple threads can use a read connection
    async def _read(self, connection: aiosqlite.Connection, statement, args: typing.Optional[tuple] = None, buffer_size = BUFFER_SIZE):
        async with connection.execute(statement, parameters = args) as cursor:
            while(results := cursor.fetchmany(buffer_size)):
                for result in results:
                    yield result

    # opens a new connection for writing (required in SQLite for syncing)
    # eg. async with _get() as conn:
    async def _get_handle(self):
         return await aiosqlite.connect(self.database_filename)

    # only one thread can use a write connection though
    # open a connection in the top level function and pass to here
    # call connection.commit at end of batch or use transactions
    async def _write(self, connection: aiosqlite.Connection, statement, args: typing.Optional[tuple] = None):
        return await connection.execute(statement, parameters = args)