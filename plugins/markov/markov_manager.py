# Markov chain frontend for managing multiple models
# Copyright (C) 2024 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import aiosqlite
from logging import log

from plugins.lib.markov.markov import markov
from plugins.lib.markov.markov_brain import markov_brain

class markov_manager:
    DEFAULT_MARKOV_DB_FILE = 'markov.db'

    def __init__(self,
                 database_filename = DEFAULT_MARKOV_DB_FILE):
        self.database_filename = database_filename
        self.database = None
        self.markovs = []

    def __contains__(self, id):
        return any([m.brain.id() for m in self.markovs if m.brain.id() == id]) or False

    async def connect(self):
        self.database = await aiosqlite.connect(self.database_filename)
        await self.database.set_trace_callback(log)

    async def close(self):
        await self.database.commit()
        await self.database.close()

    def get_markov(self, id) -> markov:
        return next(filter(lambda m: m.brain.id() == id, self.markovs), None)

    async def add_markov(self, id, root_id = None, max_entries = None) -> markov:
        root = self.get_markov(root_id)
        seed_table = root.brain.seed_table_name if root else None
        next_state_table = root.brain.next_state_table_name if root else None

        if id not in self:
            m = markov(markov_brain(id = id, 
                                        database = self.database,
                                        database_filename = self.database_filename, 
                                        copy_seed_table_name = seed_table,
                                        copy_next_state_table_name = next_state_table))
            await m.brain.init()
            self.markovs.append(m)
        return self.get_markov(id)
    
    async def remove_brain(self, id):
        m = self.get_markov(id)
        await m.brain.remove()
        self.markovs.remove(m)