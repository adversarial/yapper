# Markov chain text parser and generator
# Copyright (C) 2024 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import string
import re
import numpy
import aiosqlite

from collections import deque

from plugins.lib.markov.markov_brain import markov_brain

# don't post urls or commands
FORBIDDEN_WORD_FILTER = [ 'https://', 'http://', '.com', '.net', '.org' ]
def is_bad_word(word):
    return any(forbidden in word.lower() for forbidden in FORBIDDEN_WORD_FILTER) or (word[0] in string.punctuation and (word[0] != '\"' or word[0] != '\''))

# removes punctuation 
def strip_surrounding_punctuation(word):
    word = word.strip()
    for l in reversed(word):
        if l not in string.ascii_letters + string.digits:
            word = word.removesuffix(l)
        else:
            break
    for l in word:
        if l not in string.ascii_letters + string.digits:
            word = word.removeprefix(l)
        else:
            break
    return word

# only want strings made of letters and numbers
def normalize_string(word):
    return ' '.join(re.findall('(?:^|(?<= ))[a-zA-Z0-9]+(?= |$)', strip_surrounding_punctuation(word)))

class markov:
    TERMINAL_PHRASE = '<stop>'
    SEPERATOR = ' '
    
    def __init__(self,
                 brain: markov_brain,
                 chain_length = 2,              # number of words in seed
                 max_output_words = 100,
                 max_database_entries = None):
        
        self.chattiness = 1
        self.brain = brain
        self.chain_length = chain_length
        self.MAX_OUTPUT_WORDS = max_output_words
        self.max_database_entries = max_database_entries
        self.rng = numpy.random.default_rng()

    # generate a dictionary entry from chain
    #   [ 'the', 'quick', 'brown', 'fox' ] -> [ 'the quick', 'brown' ], ...
    # then check if the key exists, if so add weights to values
    #   e.g. [ 'the quick', 'bird' ] ->
    #   [ 'the quick', [ ['brown', 3], ['bird', 1] ]
    async def process_message(self, message, message_id, author_id):
        for word in message.split():
             if is_bad_word(word):
                return
        
        async with aiosqlite.connect(self.brain.database_filename) as database:
            for words in self._split_message(message):
                key = self.SEPERATOR.join(words[:-1])
                value = words[-1]
                await self.brain._internal_add_next_state(database, key, value, message_id)            
            await database.commit()
        
        self.brain.id_manager.add_message(message_id, author_id)

    # generate lists of chain_length of sets of characters
    # [ 'the', 'quick', 'brown', 'fox', TERMINAL_PHRASE ] -> 
    #       [ 'the', 'quick', 'brown' ]
    #       [ 'quick', 'brown', 'fox' ]
    #       [ 'brown', 'fox', TERMINAL_PHRASE ]
    def _split_message(self, message):
        if len(words := message.split()) < self.chain_length:
            return
        
        words = list(map(normalize_string, words))
        if len(words) < self.chain_length:
            return
        words.append(self.TERMINAL_PHRASE)

        for i in range(len(words) - self.chain_length):
            yield words[i:i + self.chain_length + 1] # + 1 is the key

    # Raises KeyError if seed is invalid or cannot find prompt
    # Try beginning and end of string as seed
    # Form sentence by appending next chain[seed] until terminal string is reached
    # Due to circular_dict pushing out terminal strings, sometimes a KeyError may be thrown while forming
    async def generate_message(self, seed, max_words = None):
        message = seed
        for _ in range(max_words or self.MAX_OUTPUT_WORDS):
            # Turn counts into probability and sample random next word
            # seed [ 'the quick' ], chain[seed] [ ('brown', 3), ('bird', 1) ] -> 
            #   values [ 'brown', 'bird' ] counts [ 3, 1 ] -> p [ 0.75, 0.25 ]
            if not (next_states := await self.brain.get_next_states(seed)):
                break
            values, counts = map(list, zip(*next_states))
            p = [c / sum(counts) for c in counts]
            next_word = self.rng.choice(values, p = p)
            if next_word == self.TERMINAL_PHRASE:
                break
            message += ' ' + next_word
            
            # Drop first word of key, add sampled value
            # remove first word and append next word to form new key
            # [ 'the quick' ] [ 'brown' ] -> [ 'quick brown' ]
            next_key = seed.split()[1:self.chain_length]
            next_key.append(next_word)
            seed = self.SEPERATOR.join(next_key)
        return message
    
    # Tries to form a prefix to a markov text chain by forming previous states - DOES NOT INCLUDE SEED to allow appending
    # Is not the same as an actual markov chain because the previous state is randomly chosen, no weights are applied
    async def generate_reverse_message(self, seed, max_words = 10):
        # drop last word of key
        # [ 'brown fox' ] [ 'brown' ] -> [ 'quick brown' ]
        forward_seed = seed.split()[-1]
        prompt = self.SEPERATOR.join(seed.split()[:self.chain_length - 1])
        message = deque()
        for _ in range(max_words or self.MAX_OUTPUT_WORDS):
            # Drop last word of key and try to find matching keys
            # [ 'lazy dog' ] -> [ 'lazy' ] -> [ 'the lazy' ]
            try:
                prev_seed = await self.brain.get_previous_state(prompt, forward_seed, self.SEPERATOR)
            except KeyError:
                break
            if prev_seed == prompt: # due to no terminal at beginning this may loop infinitely, todo?
                break
            forward_seed = prev_seed.split()[-1]
            prev_state = prev_seed.split()[:self.chain_length - 1]
            message.appendleft(' '.join(prev_state))
            prompt = self.SEPERATOR.join(prev_state)
        return ' '.join(message)

    
    # Raises KeyError if seed is invalid
    # Turns a string into a string of self.chain_length words that is a valid seed
    async def string_to_seed(self, seed):
        seed = list(map(normalize_string, seed.split()))

        if len(seed) == self.chain_length:
            seed = self.SEPERATOR.join(seed)
            #if seed not in self.brain:
            if not await self.brain.contains(seed):
                raise KeyError(f"Invalid seed \'{seed}\' not found in chain.")
            
        elif len(seed) < self.chain_length:
            seed = await self.brain.get_fuzzy_seed(self.SEPERATOR.join(seed), self.SEPERATOR)

        elif len(seed) > self.chain_length:
            # try beginning and end of string as seed
            end_seed = self.SEPERATOR.join(seed[-self.chain_length:])
            beg_seed = self.SEPERATOR.join(seed[:self.chain_length])
            #if end_seed in self.brain:
            if not await self.brain.contains(end_seed):
                seed = end_seed
            #elif beg_seed in self.brain:
            if not await self.brain.contains(beg_seed):
                seed = beg_seed
            else:
                raise KeyError(f"Invalid seed \'{' '.join(seed)}\' not found in chain.")
        
        return seed
    
    # Raises KeyError if seed is invalid
    # Generates a few messages and returns the longest
    async def speak(self, seed = None, tries = 10):
        random_seed = False
    
        if seed is None:
            random_seed = True
        else:
            seed = await self.string_to_seed(seed.strip())

        longest_message = ''
        for _ in range(1, tries):
            if random_seed:
                seed = await self.brain.get_random_seed()

            message = await self.generate_message(seed)
            if len(message.split()) > self.MAX_OUTPUT_WORDS:
                continue
            if len(message.split()) > len(longest_message.split()):
                longest_message = message
        return longest_message

    async def babble(self, seed = None, tries = 10):
        random_seed = False

        if seed is None:
            random_seed = True
        else:
            seed = await self.string_to_seed(seed.strip())

        longest_message = ''

        for _ in range(tries):
            if random_seed:
                seed = await self.brain.get_random_seed()
            
            # picks smallest number among 3 randomly generated [0-1]s so seed is near beginning
            before_seed_amt = int(min(self.rng.random(size = 3)) * self.MAX_OUTPUT_WORDS)
            after_seed_amt = self.MAX_OUTPUT_WORDS - before_seed_amt

            message = await self.generate_reverse_message(seed, max_words = before_seed_amt)
            message += ' ' + await self.generate_message(seed, max_words = after_seed_amt)
            if len(message.split()) > self.MAX_OUTPUT_WORDS:
                continue
            if len(message.split()) > len(longest_message.split()):
                longest_message = message
        return longest_message

class markov_trainer:
    def __init__(self, mkv: markov):
        self.markov = mkv

    async def train_on_file(self, filename, max_characters = None):
        if max_characters is None:
            max_characters = -1 # full file
        with open(filename, 'r') as file:
            for line in file.readlines(max_characters):
                await self.mkv.process_message(line)

