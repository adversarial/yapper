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

# interact with this module through the markov_id class
# > add_message((m, u | None))
# > add_message(((m, u | None), (m2, u2)))
# > get_messages(u | None)
# > get

#
#   Each table allows inserting
#
#    message_id table                                   user_alias table
#  *******************          user_id table          *****************
#  * message_id (PK) *         ****************        * alias         *
#  * user_id         * ------> * user_id (PK) * <----- * user_id       *
#  *******************         ****************        *****************
#   > insert(m, u)             > insert(u)             > insert(a, u)
#   > query(u | None)          > query(u | None)       > query(u)
#   > contains(m, u | None)    > contains(u)           > contains(a, u | None)

# user_id is Nullable which will result in no user_id or user_alias tables   

# id_manager
#   > add_message(id, user id, user aliases[])
#   > get_messages(), get_users(), get_user_aliases()

# table methods:
#   contains(alias) 
#   has(user_id, alias)
#   insert(user_id, alias)
#   get(user_id, alias)
#   remove(user_id, alias)     

import aiosqlite
from collections.abc import Iterable

from plugins.lib.markov.markov_table import markov_table

import message_id_table as message_id_table
import user_alias_table as user_alias_table
import user_id_table as user_id_table

# front facing class
class markov_id_manager:

    def __init__(self, id, database: aiosqlite.Connection, database_filename: str, anonymous = False):
        self.id = id
        self.database = database
        self.database_filename = database_filename
        self._anonymous = anonymous

        self.DEFAULT_ANONYMOUS_USERID = 1

        self.user_id_table = user_id_table(id, database, database_filename)
        self.msg_id_table = message_id_table(id, database, database_filename, self.user_id_table)
        self.alias_table = user_alias_table(id, database, database_filename, self.user_id_table)

    async def init(self):
            await self.user_id_table.init()
            await self.msg_id_table.init()
            await self.alias_table.init()

    async def anonymous_mode(self) -> bool:
        return self._anonymous
    
    async def has_message(self, message_id, user_id = None):
        await self.msg_id_table.contains(message_id, user_id)

    async def _add_message_internal(self, msg_id_connection, user_id_connection, alias_id_connection,
                                    message_id, user_id, aliases = [],
                                    commit = False):
            
            if not isinstance(aliases, Iterable):
                aliases = (aliases,)

            await self.user_id_table._internal_insert(user_id_connection, user_id)
            await self.msg_id_table._internal_insert(msg_id_connection, message_id, user_id)
            if any(aliases):
                await self.alias_table._internal_insert(alias_id_connection, user_id, aliases)
            if commit:
                await user_id_connection.commit()
                await msg_id_connection.commit()
                if any(aliases):
                    await alias_id_connection.commit()

    async def add_message(self, message_id, user_id = None, aliases = []):
        
        if self.anonymous_mode():
            user_id = self.DEFAULT_ANONYMOUS_USERID
            aliases = []

        async with self.user_id_table._get_handle() as uid_handle, \
                   self.message_id_table._get_handle() as mid_handle, \
                   self.user_alias_table._get_handle() as aid_handle:
        
            self._add_message_internal(mid_handle, uid_handle, aid_handle, 
                                    message_id, user_id, aliases, 
                                    commit = True)

    async def get_messages(self, user_id = None):
        
        if self.anonymous_mode():
            user_id = self.DEFAULT_ANONYMOUS_USERID

        return self.msg_id_table.query(user_id)
    
    async def import_scraper_dump(self, database_source_filename, group_name):
        from plugins.lib.markov.scraper.scraped_database import scraped_database_table

        database_src = scraped_database_table(database_source_filename, group_name)
        try:
            async with self.user_id_table._get_handle() as uid_handle, \
                   self.message_id_table._get_handle() as mid_handle, \
                   self.user_alias_table._get_handle() as aid_handle:
        
                if not self.anonymous_mode():
                    for alias, user_id in database_src.enumerate_aliases():
                        self.alias_table._internal_insert(aid_handle, alias, user_id)

                for comment in database_src.enumerate_comments():
                    user_id = comment.user_id if not self.anonymous_mode() else self.DEFAULT_ANONYMOUS_USERID
                    self._add_message_internal(mid_handle, uid_handle, aid_handle, 
                                            comment.id, user_id, None, 
                                            commit = False)

                await uid_handle.commit()
                await mid_handle.commit()
                await aid_handle.commit()

                return True
            
        except Exception as e:
            print(f'Failed to import {database_source_filename}.\n{e}')
            raise e
        
# markov chain doesn't prevent duplicate message consumption
# alternate class to make implementation easier
class dummy_id_manager(markov_table):

    def __init__(self, id, database, database_filename):
        self.id = id
        self.database = None
        self.database_filename = None

    async def init(self):
        pass

    async def has_message(self, message_id):
        return False

    async def add_message(self, message_id, user_id, aliases = []):
        pass

    async def get_messages(self, user_id = None):
        return None
