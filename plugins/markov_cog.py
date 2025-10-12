# Markov chain discord plugin
# Copyright (C) 2024 adversarial

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import discord
from discord import app_commands
from discord.ext import commands

from configparser import ConfigParser
import json
import typing
import os, pathlib

from plugins.lib.markov.markov import markov_trainer
from plugins.lib.markov.markov_manager import markov_manager
from lib.FancyDiscordPrompt import make_ActionOptionPrompt, make_OptionPrompt, make_OptionPromptThenModal

MARKOV_CONFIG_FILENAME = 'markov.ini'

class discord_markov_trainer(markov_trainer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def train_on_channel(self, channel, max_messages = None):
        if not hasattr(channel, 'history'):
            return
        async for message in channel.history(limit = max_messages):
            await self.markov.process_message(message.content, message.id, message.author.id)

    async def train_on_server(self, guild, max_messages = None):
        for c in guild.channels:
            if not hasattr(c, 'history'):
                continue
            try:
                async for message in c.history(limit = max_messages):
                    await self.markov.process_message(message.content, message.id, message.author.id)
                    if max_messages is not None:
                        max_messages -= 1
                        if max_messages < 1:
                            break
            except:
                continue

class MarkovCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.mconfig = { }
        self.mkvcfg = ConfigParser()
        self.mkvcfg.read(MARKOV_CONFIG_FILENAME)
        self.mconfig['filename'] = MARKOV_CONFIG_FILENAME
        self.mconfig['whitelist_servers_only'] = self.mkvcfg.getboolean('settings', 'whitelist_servers_only')
        self.mconfig['whitelist_users_only'] = self.mkvcfg.getboolean('settings', 'whitelist_users_only')
        self.mconfig['guild_whitelist'] = json.loads(self.mkvcfg['whitelists']['guild_ids'])
        self.mconfig['user_whitelist'] = json.loads(self.mkvcfg['whitelists']['user_ids'])
        self.mconfig['guild_blacklist'] = json.loads(self.mkvcfg['blacklists']['guild_ids'])
        self.mconfig['user_blacklist'] = json.loads(self.mkvcfg['blacklists']['user_ids'])

        self.manager = markov_manager()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await self.bot.is_owner(interaction.user) or interaction.user.id == interaction.guild.owner_id:
            return True
        if self.mconfig['whitelist_servers_only'] and interaction.guild_id not in self.mconfig['guild_whitelist']:
            return False
        if self.mconfig['whitelist_users_only'] and interaction.user.id not in self.mconfig['user_whitelist']:
            return False
        if interaction.guild_id in self.mconfig['guild_blacklist'] or interaction.user.id in self.mconfig['user_blacklist']:
            return False
        return super().interaction_check(interaction)   # returns true
    
    def server_check(self, guild_id):
        return ((self.mconfig['whitelist_servers_only'] and guild_id in self.mconfig['guild_whitelist']) 
                or guild_id not in self.mconfig['guild_blacklist'])

    async def cog_load(self):
        await self.manager.connect()

    async def cog_unload(self):
        await self.manager.close()

    @commands.Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds:
            if self.server_check(g.id):
                await self.manager.add_markov(g.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        if self.server_check(guild.id):
            await self.manager.add_markov(guild.id)

    # handles on_message discord loop
    @commands.Cog.listener()
    @commands.guild_only()
    async def on_message(self, msg: discord.Message):
        if msg.guild is None or msg.author.bot:
            return
        if self.server_check(msg.guild.id) and msg.guild.id in self.manager and not msg.author.bot:
            await self.manager.get_markov(msg.guild.id).process_message(msg.content, msg.id, msg.author.id)

    chatbot_group = app_commands.Group(name="chatbot", description="chatbot features")

    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @chatbot_group.command(name = 'speak', description = 'Speak based on a phrase or a random word.')
    async def speak(self, interaction: discord.Interaction, seed: typing.Optional[str]):
        await interaction.response.defer()
        try: 
            msg = await self.manager.get_markov(interaction.guild.id).speak(seed)
            await interaction.followup.send(msg)
        except KeyError:
            await interaction.delete_original_response()
            await interaction.followup.send('Invalid seed. Please try another phrase.', ephemeral = True)

    @app_commands.allowed_installs(guilds = True, users = True)
    @app_commands.allowed_contexts(guilds = True, private_channels = True)
    @chatbot_group.command(name = 'babble', description= 'Speak based on a word, using fuzzy search and guessing what comes before.')
    async def babble(self, interaction: discord.Interaction, seed: str):
        await interaction.response.defer()
        try:
            msg = await self.manager.get_markov(interaction.guild.id).babble(seed)
            await interaction.followup.send(msg)
        except KeyError:
            await interaction.delete_original_response()
            await interaction.followup.send('Invalid seed. Please try another phrase.', ephemeral = True)

    @chatbot_group.command(description="Options for markov chat bot")
    @app_commands.choices(option = [ app_commands.Choice(name = "enable", value = "enable"),
							        app_commands.Choice(name = "disable", value = "disable"),
							        app_commands.Choice(name = "reset", value = "reset"),
                                    app_commands.Choice(name = "import brain", value = "import brain"),
                                    app_commands.Choice(name = "export brain", value = "export brain"),
                                    app_commands.Choice(name = "train on server", value = "train on server"),
                                    app_commands.Choice(name = "train on channel", value = "train on channel"),
                                    app_commands.Choice(name = "train on user", value = "train on user"),
                                    app_commands.Choice(name = "chattiness_level", value = "chattiness_level"),
                                    app_commands.Choice(name = "ban guild", value = "ban guild"),
                                    app_commands.Choice(name = "ban user", value = "ban user"),
                                    app_commands.Choice(name = "unban guild", value = "unban guild"),
                                    app_commands.Choice(name = "unban user", value = "unban user"),
                                    app_commands.Choice(name = "debug", value = "debug")])
    async def settings(self, interaction: discord.Interaction, option: app_commands.Choice[str]):
        settings_handlers = {
            "enable"            : self._handle_enable_server,
            "disable"           : self._handle_disable_server,
            "reset"             : self._handle_reset,
            "import brain"      : self._handle_import_brain,
            "export brain"      : self._handle_export_brain,
            "train on server"   : self._handle_train_on_server,
            "train on channel"  : self._handle_train_on_channel,
            "train on user"     : self._handle_train_on_user,
            "chattiness_level"  : self._handle_chattiness_level,
            "ban guild"         : self._handle_ban_guild,
            "unban guild"       : self._handle_unban_guild,
            "ban user"          : self._handle_ban_user,
            "unban user"        : self._handle_unban_user,
            "debug"             : self._handle_debug
        }
        await settings_handlers[option.value](interaction)
            
    async def _handle_enable_server(self, interaction: discord.Interaction):
        if await self.bot.is_owner(interaction.user):
            guild_options = [discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds]
        elif interaction.user.id == interaction.guild.owner_id:
            guild_options = [ discord.SelectOption(label = interaction.guild.name, value = interaction.guild_id) ]
        else:
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        
        guild = await make_OptionPrompt(interaction, 
                                        title = "Enable", 
                                        description= 'Enable the chatbot in selected server.', 
                                        option_placeholder = 'Select a guild',
                                        options = guild_options)
        if not guild:
            return
        guild_id = int(guild.value)

        if guild_id in self.mconfig['guild_blacklist']:
            self.mconfig['guild_blacklist'].remove(guild_id)
            self.mkvcfg['blacklists']['guild_ids'] = json.dumps(self.mconfig['guild_blacklist'])
            with open(MARKOV_CONFIG_FILENAME, 'w') as cfgfile:
                self.mkvcfg.write(cfgfile)
            await interaction.followup.send(f'Removed guild {guild.label} from chatbot blacklist.', ephemeral = True)
        if self.mconfig['whitelist_servers_only'] is True:
            self.mconfig['guild_whitelist'].append(guild_id)
            self.mkvcfg['whitelists']['guild_ids'] = json.dumps(self.mconfig['guild_whitelist'])
            with open(MARKOV_CONFIG_FILENAME, 'w') as cfgfile:
                self.mkvcfg.write(cfgfile)
            await interaction.followup.send(f'Added guild {guild.label} to chatbot whitelist.', ephemeral = True)

    async def _handle_disable_server(self, interaction: discord.Interaction):
        if await self.bot.is_owner(interaction.user):
            guild_options = [discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds]
        elif interaction.user.id == interaction.guild.owner_id:
            guild_options = [ discord.SelectOption(label = interaction.guild.name, value = interaction.guild_id) ]
        else:
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        
        guild = await make_OptionPrompt(interaction, 
                                        title = "Disable", 
                                        description= 'Disable the chatbot in selected server.', 
                                        option_placeholder = 'Select a guild',
                                        options = guild_options)
        if not guild:
            return
        guild_id = int(guild.value)

        if guild_id in self.mconfig['guild_whitelist']:
            self.mconfig['guild_whitelist'].remove(guild_id)
            self.mkvcfg['whitelists']['guild_ids'] = json.dumps(self.mconfig['guild_whitelist'])
            await interaction.followup.send(f'Removed guild {guild.label} from chatbot whitelist.', ephemeral = True)
        self.mconfig['guild_blacklist'].append(guild_id)
        self.mkvcfg['blacklists']['guild_ids'] = json.dumps(self.mconfig['guild_blacklist'])
        with open(MARKOV_CONFIG_FILENAME, 'w') as cfgfile:
            self.mkvcfg.write(cfgfile)
        await interaction.followup.send(f'Added guild {guild.label} to chatbot blacklist.', ephemeral = True)
        
    async def _handle_train_on_server(self, interaction: discord.Interaction):
        if await self.bot.is_owner(interaction.user):
            guild_options = [discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds]
        elif interaction.user.id == interaction.guild.owner_id:
            guild_options = [ discord.SelectOption(label = interaction.guild.name, value = interaction.guild_id) ]
        else:
            await interaction.response.send_message(f'You must be the owner of the server to use this function.', ephemeral = True)
            return 
        
        guild, target = await make_ActionOptionPrompt(interaction, 
                                                    title = 'Train chatbot on guild', 
                                                    description= 'Choose a guild. This may take some time.', 
                                                    action_placeholder = 'Select a guild to train',
                                                    actions = guild_options,
                                                    option_placeholder = 'Select a guild to train on',
                                                    options = guild_options)
        if not all((guild, target)):
            return
        try:
            await discord_markov_trainer(self.manager.get_markov(int(guild.value))).train_on_server(self.bot.get_guild(int(target.value)))
            await interaction.followup.send(f'Trained {guild.label} on {target.label}.', ephemeral = True)
        except:
            await interaction.followup.send(f'Missing permissions, please give message history access to use this feature.', ephemeral = True)

    async def _handle_train_on_channel(self, interaction: discord.Interaction):
        if await self.bot.is_owner(interaction.user):
            guild_options = [discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds]
        elif interaction.user.id == interaction.guild.owner_id:
            guild_options = [ discord.SelectOption(label = interaction.guild.name, value = interaction.guild_id) ]
        else:
            await interaction.response.send_message(f'You must be the owner of the server to use this function.', ephemeral = True)
            return 
        
        channel_options = [discord.SelectOption(label = c.name, value = str(c.id)) for c in interaction.guild.channels]

        guild, target = await make_ActionOptionPrompt(interaction, 
                                                    title = 'Train chatbot on channel', 
                                                    description= 'Choose a guild and channel. This may take some time.', 
                                                    action_placeholder = 'Select a guild to train',
                                                    actions = guild_options,
                                                    option_placeholder = 'Select a channel to train on',
                                                    options = channel_options)
        if not all((guild, target)):
            return
        try:
            await discord_markov_trainer(self.manager.get_markov(int(guild.value))).train_on_channel(self.bot.get_channel(int(target.value)))
            await interaction.followup.send(f'Trained {guild.label} on {target.label}.')
        except:
            await interaction.followup.send(f'Missing permissions, please give message history access to use this feature.', ephemeral = True)

    async def _handle_train_on_user(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        pass

    async def _handle_chattiness_level(self, interaction: discord.Interaction):
        if await self.bot.is_owner(interaction.user):
            guild_options = [discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds]
        elif interaction.user.id == interaction.guild.owner_id:
            guild_options = [ discord.SelectOption(label = interaction.guild.name, value = interaction.guild_id) ]
        else:
            await interaction.response.send_message(f'You must be the owner of the server to use this function.', ephemeral = True)
            return 
        guild, level = await make_OptionPromptThenModal(interaction, 
                            modal_title= "Chatbot chattiness level",
                            modal_input_label= f'Enter a percent (number between 0-100):',
                            modal_default = '1',
                            title = "Set the chattiness level", 
                            description= 'Select a guild and percent (0-100) of messages to be responded to.', 
                            option_placeholder = 'Select a guild',
                            options = [ discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds ])
        if not all((guild, level)):
            return
        try:
            int_level = int(level)
            if int_level not in range(0, 100):
                raise ValueError
            self.manager.get_markov(int(guild.value)).chattiness = int_level
            await interaction.followup.send(f'Chatbot chattiness successfully set to {int_level} in {guild.label}', ephemeral = True)
        except ValueError:
            await interaction.followup.send(f'{level} is not a valid number between 0 and 100.', ephemeral = True)
        
    async def _handle_ban_guild(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        raise NotImplementedError

    async def _handle_unban_guild(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        raise NotImplementedError

    async def _handle_ban_user(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        raise NotImplementedError
    
    async def _handle_unban_user(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        raise NotImplementedError

    async def _handle_import_brain(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        
        brains_options = [ ]
        brains_folder = pathlib.Path(os.getcwd()).joinpath('chatbot-brains')
        os.makedirs(brains_folder, exist_ok = True)
        for path, subdirs, files in os.walk('chatbot-brains'):
            for name in files:
                brains_options.append(discord.SelectOption(label = name, value = os.path.join(path, name)))

        guild, file = await make_ActionOptionPrompt(interaction, 
                                                    title = 'Import chatbot brain', 
                                                    description= 'Choose a guild. This may take some time.', 
                                                    action_placeholder = 'Select a guild',
                                                    actions = [discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds],
                                                    option_placeholder = 'Select a brain',
                                                    options = brains_options)
        if not all((guild, file)):
            return
        try:
            await self.manager.get_markov(int(guild.value)).brain.import_json(file.value)
            await interaction.followup.send(f'Successfully imported brain file.', ephemeral = True)
        except Exception as e:
            await interaction.followup.send(f'Unable to import file: {e.msg}', ephemeral = True)

    async def _handle_export_brain(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return

        guild, filename = await make_OptionPromptThenModal(interaction, 
                                        modal_title= "Export a server's chatbot brain",
                                        modal_input_label= 'Select a filename:',
                                        modal_default = 'server.brain',
                                        title = "Export a server's chatbot brain. This may take some time.", 
                                        description= 'Select a guild and filename.', 
                                        option_placeholder = 'Select a guild',
                                        options = [ discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds ])
        if not guild or not filename:
            return
        try:
            brains_folder = pathlib.Path(os.getcwd()).joinpath('chatbot-brains')
            os.makedirs(brains_folder, exist_ok = True)
            output_file = brains_folder.joinpath(pathlib.Path(filename))
            await self.manager.get_markov(int(guild.value)).brain.export_json(output_file)
            await interaction.followup.send(f'Successfully exported brain file.', ephemeral = True)
        except Exception as e:
            await interaction.response.send_message(f'Unable to export file: {e.msg}', ephemeral = True)

    async def _handle_reset(self, interaction: discord.Interaction):
        if await self.bot.is_owner(interaction.user):
            guild_options = [discord.SelectOption(label = g.name, value = str(g.id)) for g in self.bot.guilds]
        elif interaction.user.id == interaction.guild.owner_id:
            guild_options = [ discord.SelectOption(label = interaction.guild.name, value = interaction.guild_id) ]
        else:
            await interaction.response.send_message(f'You must be the owner of the server to use this function.', ephemeral = True)
            return 
        
        guild = await make_OptionPrompt(interaction, 
                                        title = "Reset (clear) a server's chatbot", 
                                        description= 'WARNING: this will erase the chatbot for this server. This action cannot be undone.', 
                                        option_placeholder = 'Select a guild',
                                        options = guild_options)
        if not guild:
            return
        await self.manager.get_markov(int(guild.value)).brain.reset()
        await interaction.followup.send(f'Reset successful.', ephemeral = True)

    async def _handle_debug(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(f'You must be the owner to use this function.', ephemeral = True)
            return
        await interaction.response.defer()
        await self.manager.get_markov(interaction.guild_id).brain._dbg()


async def setup(bot: commands.bot):
    await bot.add_cog(MarkovCog(bot = bot))
