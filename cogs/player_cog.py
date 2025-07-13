# cogs/player_cog.py
# import discord
# from discord.ext import commands
import nextcord as discord
from nextcord.ext import commands
import os
import math
import logging
import time
import io
import re
# import tempfile
# import asyncio

# Import from our new local files
from config import AUDIOBOOK_PATH, BOOKS_PER_PAGE
from . import audio_utils
from . import playback_handler

log = logging.getLogger(__name__)

CHAPTERS_PER_PAGE = 25

# --- UI Classes ---

class AudiobookPlayerView(discord.ui.View):
    def __init__(self, author: discord.User, bot: commands.AutoShardedBot):
        super().__init__(timeout=600)
        self.author = author
        self.bot = bot
      
        self.all_items = audio_utils.get_books_and_series(AUDIOBOOK_PATH)
        self.current_page = 0
        self.total_pages = math.ceil(len(self.all_items) / BOOKS_PER_PAGE)
      
        self.selected_series = None  # If user is browsing a series
        self.selection_state = 'items'  # 'items', 'series_books', 'chapters'

        self.current_series_book_page = 0
        self.total_series_book_pages = 1  # Will be set when a series is selected

        self.selected_book_path = None
        self.all_chapters = []
        self.current_chapter_page = 0
        self.total_chapter_pages = 0

        self.selected_chapter_path = None
        self.selected_channel = None
        self.current_chapter_index = -1  # Track current chapter index
      
        # Player state tracking
        self.is_playing = False
        self.is_paused = False  # Add this
        self.pause_start_time = 0  # Add this
        self.current_seek = 0
        self.play_start_time = 0
        self.duration = 0
        self.interaction = None
        self.time_tracker_running = False
        self.message = None  # Add this for webhook updates
      
        self.update_view()

    def update_view(self):
        self.clear_items()
        if self.selection_state == 'items':
            # Show main menu (series + standalone books)
            # Sort all items naturally before paginating
            sorted_items = sorted(self.all_items, key=lambda item: natural_key(item['title']))
            start_index = self.current_page * BOOKS_PER_PAGE
            end_index = start_index + BOOKS_PER_PAGE
            items_on_page = sorted_items[start_index:end_index]
            if items_on_page:
                self.add_item(ItemSelect(
                    items=items_on_page,
                    placeholder=f"Select audiobook or series (Page {self.current_page + 1}/{self.total_pages})",
                    start_index=start_index
                ))
            if self.total_pages > 1:
                self.add_item(PageButton(label="<< Previous", disabled=(self.current_page == 0), direction=-1))
                self.add_item(PageButton(label="Next >>", disabled=(self.current_page >= self.total_pages - 1), direction=1))
        elif self.selection_state == 'series_books':
            # Show books within the selected series
            if self.selected_series and self.selected_series['books']:
                # Sort all books naturally before paginating
                books = sorted(self.selected_series['books'], key=lambda item: natural_key(item['title']))
                books_per_page = 25
                total_pages = math.ceil(len(books) / books_per_page)
                self.total_series_book_pages = total_pages
                start = self.current_series_book_page * books_per_page
                end = start + books_per_page
                self.add_item(SeriesBookSelect(
                    books=books[start:end],  # This is a slice, always ≤25
                    series_title=self.selected_series['title'],
                    start_index=start
                ))
                if total_pages > 1:
                    self.add_item(SeriesBookPageButton(label="<< Previous", disabled=(self.current_series_book_page == 0), direction=-1))
                    self.add_item(SeriesBookPageButton(label="Next >>", disabled=(self.current_series_book_page >= total_pages - 1), direction=1))
            self.add_item(BackButton())
        elif self.selection_state == 'chapters':
            # Show chapters for the selected book
            # Sort chapters by track number (numeric)
            sorted_chapters = sorted(self.all_chapters, key=lambda item: item['track'])
            start_index = self.current_chapter_page * CHAPTERS_PER_PAGE
            end_index = start_index + CHAPTERS_PER_PAGE
            chapters_on_page = sorted_chapters[start_index:end_index]
            if chapters_on_page:
                self.add_item(ChapterSelect(
                    chapters=chapters_on_page,
                    start_index=start_index
                ))
            if self.total_chapter_pages > 1:
                self.add_item(ChapterPageButton(label="<< Prev Page", disabled=(self.current_chapter_page == 0), direction=-1))
                self.add_item(ChapterPageButton(label=f"Page {self.current_chapter_page + 1}/{self.total_chapter_pages}", disabled=True, direction=0))
                self.add_item(ChapterPageButton(label="Next Page >>", disabled=(self.current_chapter_page >= self.total_chapter_pages - 1), direction=1))
            self.add_item(SynopsisButton(book_path=self.selected_book_path))
            self.add_item(BackButton())

    async def safe_edit_message(self, interaction_or_message, **kwargs):
        """Safely edit a message, handling token expiry"""
        try:
            if hasattr(interaction_or_message, 'edit_original_message'):
                await interaction_or_message.edit_original_message(**kwargs)
            else:
                await interaction_or_message.edit(**kwargs)
        except discord.errors.HTTPException as e:
            if e.code == 50027:  # Invalid Webhook Token
                log.warning(f"Webhook token expired, cannot update message: {e}")
                # Remove expired messages from tracking
                if hasattr(self, 'messages'):
                    self.messages.discard(interaction_or_message)
            else:
                raise

    def _show_items_selection(self):
        start_index = self.current_page * BOOKS_PER_PAGE
        end_index = start_index + BOOKS_PER_PAGE
        items_on_page = self.all_items[start_index:end_index]
        self.add_item(ItemSelect(
            items=items_on_page,
            placeholder=f"Select audiobook or series (Page {self.current_page + 1}/{self.total_pages})",
            start_index=start_index
        ))
        if self.total_pages > 1:
            self.add_item(PageButton(label="<< Previous", disabled=(self.current_page == 0), direction=-1))
            self.add_item(PageButton(label="Next >>", disabled=(self.current_page >= self.total_pages - 1), direction=1))

    def _show_series_books(self):
        if not self.selected_series:
            return
        self.add_item(SeriesBookSelect(
            books=self.selected_series['books'],
            series_title=self.selected_series['title']
        ))
        self.add_item(BackButton())

    def _show_chapters(self):
        start_index = self.current_chapter_page * CHAPTERS_PER_PAGE
        end_index = start_index + CHAPTERS_PER_PAGE
        chapters_on_page = self.all_chapters[start_index:end_index]
        self.add_item(ChapterSelect(
            chapters=chapters_on_page,
            start_index=start_index
        ))
        if self.total_chapter_pages > 1:
            self.add_item(ChapterPageButton(label="<< Prev Page", disabled=(self.current_chapter_page == 0), direction=-1))
            self.add_item(ChapterPageButton(label=f"Page {self.current_chapter_page + 1}/{self.total_chapter_pages}", disabled=True, direction=0))
            self.add_item(ChapterPageButton(label="Next Page >>", disabled=(self.current_chapter_page >= self.total_chapter_pages - 1), direction=1))
        self.add_item(SynopsisButton(book_path=self.selected_book_path))
        self.add_item(BackButton())

    def update_player_view(self):
        """Updates the view to show player controls when audio is playing."""
        self.clear_items()
      
        # Row 0: Scrub buttons with pause in the middle
        self.add_item(ScrubButton(label="⏪ 1m", delta=-60))
        self.add_item(ScrubButton(label="⏪ 30s", delta=-30))
      
        # Add pause button in the middle
        is_paused = getattr(self, 'is_paused', False)
        self.add_item(PauseButton(is_paused=is_paused))
      
        self.add_item(ScrubButton(label="⏩ 30s", delta=30))
        self.add_item(ScrubButton(label="⏩ 1m", delta=60))
      
        # Row 1: Track change buttons
        has_previous = self.current_chapter_index > 0
        has_next = self.current_chapter_index < len(self.all_chapters) - 1
      
        self.add_item(TrackButton(label="⏮️ Previous", direction=-1, disabled=not has_previous))
        self.add_item(TrackButton(label="⏭️ Next", direction=1, disabled=not has_next))
      
        # Row 2: Back and Quit buttons
        self.add_item(BackToChaptersButton())
        self.add_item(QuitButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("This is not for you but revela says it's okay", ephemeral=True)
            return True
        return True

class ItemSelect(discord.ui.Select):
    def __init__(self, items: list, placeholder: str, start_index: int):
        options = []
        # Remove the items_to_show limit - the view already handles pagination
        for i, item in enumerate(items):
            emoji = "📚" if item['type'] == 'series' else "📖"
            label = f"{emoji} {item['title']}"
            options.append(discord.SelectOption(
                label=label[:100],
                value=str(i + start_index),
                description=f"by {item['author']}"[:100]
            ))
        super().__init__(placeholder=placeholder, options=options, disabled=not items)

    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0])
        selected_item = self.view.all_items[selected_index]
        if selected_item['type'] == 'series':
            self.view.selected_series = selected_item
            self.view.selection_state = 'series_books'
            self.view.update_view()
            await interaction.response.edit_message(view=self.view)
        else:
            await self._handle_book_selection(interaction, selected_item)

    async def _handle_book_selection(self, interaction, book_item):
        for item in self.view.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        self.placeholder = "Loading chapters, please wait..."
        await interaction.response.edit_message(view=self.view)
        self.view.selected_book_path = book_item['path']
        await self._load_chapters()
        self.view.selection_state = 'chapters'
        self.view.update_view()
        await interaction.edit_original_message(view=self.view)

    async def _load_chapters(self):
        all_filenames = [f for f in os.listdir(self.view.selected_book_path) if f.endswith('.m4b')]
        chapter_data = []
        for filename in all_filenames:
            full_path = os.path.join(self.view.selected_book_path, filename)
            chapter_data.append({
                'filename': filename,
                'title': audio_utils.get_book_title(full_path),
                'track': audio_utils.get_track_number(full_path)
            })
        chapter_data.sort(key=lambda item: item['track'])
        self.view.all_chapters = chapter_data
        self.view.current_chapter_page = 0
        self.view.total_chapter_pages = math.ceil(len(self.view.all_chapters) / CHAPTERS_PER_PAGE)

class SeriesBookPageButton(discord.ui.Button):
    def __init__(self, label: str, disabled: bool, direction: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=disabled, row=1)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        self.view.current_series_book_page += self.direction
        self.view.update_view()
        await interaction.response.edit_message(view=self.view)

def natural_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

class SeriesBookSelect(discord.ui.Select):
    def __init__(self, books: list, series_title: str, start_index: int = 0):
        # books is already a paginated slice!
        options = [
            discord.SelectOption(
                label=f"📖 {book['title']}"[:100],
                value=str(i + start_index)
            ) for i, book in enumerate(books)
        ]
        super().__init__(
            placeholder=f"Select book from {series_title}",
            options=options,
            disabled=not books
        )
        self.books = books
        self.start_index = start_index

    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0]) - self.start_index
        selected_book = self.books[selected_index]
        # ... rest of your logic ...
        for item in self.view.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        self.placeholder = "Loading chapters, please wait..."
        await interaction.response.edit_message(view=self.view)
        self.view.selected_book_path = selected_book['path']
        await self._load_chapters()
        self.view.selection_state = 'chapters'
        self.view.update_view()
        await interaction.edit_original_message(view=self.view)

    async def _load_chapters(self):
        all_filenames = [f for f in os.listdir(self.view.selected_book_path) if f.endswith('.m4b')]
        chapter_data = []
        for filename in all_filenames:
            full_path = os.path.join(self.view.selected_book_path, filename)
            ffprobe_data = audio_utils._run_ffprobe(full_path)
            chapter_data.append({
                'filename': filename,
                'title': audio_utils.get_book_title_from_data(ffprobe_data, full_path),
                'track': audio_utils.get_track_number_from_data(ffprobe_data, full_path)
            })
        chapter_data.sort(key=lambda item: item['track'])
        self.view.all_chapters = chapter_data
        self.view.current_chapter_page = 0
        self.view.total_chapter_pages = math.ceil(len(self.view.all_chapters) / CHAPTERS_PER_PAGE)

class BookSelect(discord.ui.Select):
    def __init__(self, books: list, placeholder: str, start_index: int):
        options = [discord.SelectOption(label=book['title'], value=str(i + start_index)) for i, book in enumerate(books)]
        super().__init__(placeholder=placeholder, options=options, disabled=not books)

    async def callback(self, interaction: discord.Interaction):
        # Disable all components and show a "loading" message
        for item in self.view.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
      
        self.placeholder = "Loading chapters, please wait..."
      
        # Acknowledge the interaction by immediately editing the message with the disabled UI
        await interaction.response.edit_message(view=self.view)

        # Perform the slow chapter-loading task
        selected_index = int(self.values[0])
        selected_book = self.view.all_items[selected_index]
        self.view.selected_book_path = selected_book['path']
        log.info(f"User selected book index: '{selected_index}'. Path: {self.view.selected_book_path}")

        all_filenames = [f for f in os.listdir(self.view.selected_book_path) if f.endswith('.m4b')]
        chapter_data = []
        for filename in all_filenames:
            full_path = os.path.join(self.view.selected_book_path, filename)
            chapter_data.append({
                'filename': filename,
                'title': audio_utils.get_book_title(full_path),
                'track': audio_utils.get_track_number(full_path)
            })
        chapter_data.sort(key=lambda item: item['track'])
        self.view.all_chapters = chapter_data
      
        self.view.current_chapter_page = 0
        self.view.total_chapter_pages = math.ceil(len(self.view.all_chapters) / CHAPTERS_PER_PAGE)
      
        # Update the view object with the new chapter list UI
        self.view.update_view()

        # Store the active view
        if hasattr(interaction.client, 'get_cog'):
            player_cog = interaction.client.get_cog('PlayerCog')
            if player_cog:
                player_cog.active_views[interaction.guild.id] = self.view
      
        # Edit the message again with the final, complete UI
        await interaction.edit_original_message(view=self.view)

class ChapterSelect(discord.ui.Select):
    def __init__(self, chapters: list, start_index: int):
        options = []
        for i, item in enumerate(chapters):
            label_text = (item['title'][:97] + '...') if len(item['title']) > 100 else item['title']
            options.append(discord.SelectOption(label=label_text, value=str(i + start_index)))
      
        super().__init__(placeholder="2. Select a chapter to play...", options=options, disabled=not chapters)

    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0])
        selected_chapter_info = self.view.all_chapters[selected_index]
    
        self.view.selected_chapter_path = os.path.join(self.view.selected_book_path, selected_chapter_info['filename'])
        self.view.current_chapter_index = selected_index

        # Store the active view
        if hasattr(interaction.client, 'get_cog'):
            player_cog = interaction.client.get_cog('PlayerCog')
            if player_cog:
                player_cog.active_views[interaction.guild.id] = self.view

        log.info(f"User selected chapter file: {self.view.selected_chapter_path} (index: {selected_index})")
        self.disabled = True
    
        voice_client = discord.utils.get(self.view.bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_connected():
            # FIX: Set selected_channel when already connected
            if not self.view.selected_channel:
                self.view.selected_channel = voice_client.channel
            await interaction.response.defer()
            await playback_handler.play_audio(interaction, self.view)
        else:
            self.view.clear_items()
            self.view.add_item(ChannelSelect(guild=interaction.guild))
            await interaction.response.edit_message(view=self.view)

class ChannelSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        channels = [ch for ch in guild.voice_channels if ch.permissions_for(guild.me).connect]
        options = [discord.SelectOption(label=ch.name, value=str(ch.id)) for ch in channels]
        super().__init__(placeholder="Connect to which voice channel?", options=options, disabled=not channels)

    async def callback(self, interaction: discord.Interaction):
        # Update active view reference
        if hasattr(self.view.bot, 'get_cog'):
            player_cog = self.view.bot.get_cog('PlayerCog')
            if player_cog:
                player_cog.active_views[interaction.guild.id] = self.view

        self.view.selected_channel = self.view.bot.get_channel(int(self.values[0]))
        await interaction.response.defer()
        await playback_handler.play_audio(interaction, self.view)

class ScrubButton(discord.ui.Button):
    def __init__(self, label: str, delta: int):
        super().__init__(label=label, style=discord.ButtonStyle.primary, row=0)
        self.delta = delta

    async def callback(self, interaction: discord.Interaction):
        player_cog = self.view.bot.get_cog('PlayerCog')
        guild_id = interaction.guild.id

        # Always use the shared view
        if player_cog and guild_id in player_cog.active_views:
            view = player_cog.active_views[guild_id]
        else:
            view = self.view

        # Use shared view for calculations
        if view.is_paused:
            current_elapsed = view.current_seek + (view.pause_start_time - view.play_start_time)
        else:
            current_elapsed = view.current_seek + (time.time() - view.play_start_time)
        
        new_seek = max(0, min(current_elapsed + self.delta, view.duration))
        
        log.info(f"Scrubbing from {current_elapsed:.1f}s to {new_seek:.1f}s (delta: {self.delta}s)")
        
        view.manual_stop = True
        
        await interaction.response.defer()
        await playback_handler.play_audio(interaction, view, seek_time=new_seek, is_scrub=True)

class TrackButton(discord.ui.Button):
    def __init__(self, label: str, direction: int, disabled: bool = False):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=1, disabled=disabled)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        player_cog = self.view.bot.get_cog('PlayerCog')
        guild_id = interaction.guild.id

        # Always use the shared view
        if player_cog and guild_id in player_cog.active_views:
            view = player_cog.active_views[guild_id]
        else:
            view = self.view

        new_index = view.current_chapter_index + self.direction
      
        if new_index < 0 or new_index >= len(view.all_chapters):
            await interaction.response.send_message("No more chapters in that direction!", ephemeral=True)
            return
      
        view.manual_stop = True
      
        new_chapter = view.all_chapters[new_index]
        view.selected_chapter_path = os.path.join(view.selected_book_path, new_chapter['filename'])
        view.current_chapter_index = new_index
      
        log.info(f"Track change: {self.direction} to chapter {new_index}: {new_chapter['title']}")
      
        await interaction.response.defer()
        await playback_handler.play_audio(interaction, view, seek_time=0)

import asyncio
import os
import tempfile

import io

class SynopsisButton(discord.ui.Button):
    def __init__(self, book_path: str):
        super().__init__(label="Show Synopsis", style=discord.ButtonStyle.secondary, row=2)
        self.book_path = book_path

    async def callback(self, interaction: discord.Interaction):
        log.info(f"Synopsis button clicked by {interaction.user} for book: {self.book_path}")
        await interaction.response.defer(ephemeral=True)
        synopsis_text = audio_utils.get_synopsis(self.book_path)
        header = "### Synopsis\n"
        truncation_note = "\n\n... (truncated)"
        max_length = 2000 - len(header)
        if len(synopsis_text) + len(header) > 2000:
            allowed = 2000 - len(header) - len(truncation_note)
            synopsis_text = synopsis_text[:allowed] + truncation_note

        # Try to extract cover image from the first chapter file
        chapter_files = sorted([f for f in os.listdir(self.book_path) if f.endswith('.m4b')])
        
        if chapter_files:
            first_chapter_path = os.path.join(self.book_path, chapter_files[0])
            # Extract cover image as bytes (no temp file)
            cover_bytes = audio_utils.extract_cover_image(first_chapter_path)
            
            if cover_bytes:
                cover_file = discord.File(io.BytesIO(cover_bytes), filename="cover.jpg")
                await interaction.followup.send(
                    content=f"{header}{synopsis_text}",
                    file=cover_file,
                    ephemeral=True
                )
            else:
                # No cover found, send without image
                await interaction.followup.send(
                    content=f"{header}{synopsis_text}",
                    ephemeral=True
                )
        else:
            # No chapter files found
            await interaction.followup.send(
                content=f"{header}{synopsis_text}",
                ephemeral=True
            )

class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="<< Back", style=discord.ButtonStyle.grey, row=2)

    async def callback(self, interaction: discord.Interaction):
        if self.view.selection_state == 'chapters':
            # Coming from chapters - go back to either series books or main items
            if self.view.selected_series:
                # We're in a series, go back to series book selection
                self.view.selection_state = 'series_books'
                self.label = "<< Back to Series"
            else:
                # We're in a standalone book, go back to main items
                self.view.selection_state = 'items'
                self.view.selected_book_path = None
                self.label = "<< Back to Book List"
            
            # Clear chapter data
            self.view.all_chapters = []
            self.view.current_chapter_page = 0
            self.view.total_chapter_pages = 0
            self.view.current_chapter_index = -1
            
        elif self.view.selection_state == 'series_books':
            # Coming from series book selection - go back to main items
            self.view.selection_state = 'items'
            self.view.selected_series = None
            self.label = "<< Back to Book List"
        
        self.view.update_view()
        await interaction.response.edit_message(view=self.view)

class BackToChaptersButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="<< Back to Chapters", style=discord.ButtonStyle.grey, row=2)

    async def callback(self, interaction: discord.Interaction):
        player_cog = self.view.bot.get_cog('PlayerCog')
        guild_id = interaction.guild.id

        # Always use the shared view
        if player_cog and guild_id in player_cog.active_views:
            view = player_cog.active_views[guild_id]
        else:
            view = self.view

        # Stop playback and mark as manual stop
        voice_client = discord.utils.get(self.view.bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_playing():
            view.manual_stop = True
            voice_client.stop()
      
        view.is_playing = False
        view.is_paused = False
        view.pause_start_time = 0
        view.time_tracker_running = False

        # Clear Discord presence
        try:
            await self.view.bot.change_presence(activity=None)
            log.info("Cleared presence - returned to chapters")
        except Exception as e:
            log.warning(f"Failed to clear presence: {e}")

        # Clear the active view
        if player_cog and guild_id in player_cog.active_views:
            del player_cog.active_views[guild_id]

        self.view.update_view()
        
        # Safe message editing with error handling
        try:
            await interaction.response.edit_message(content="Select a chapter to play:", view=self.view)
        except discord.errors.NotFound:
            # Message was deleted or interaction expired
            log.warning("Could not edit message - message not found or interaction expired")
        except discord.errors.HTTPException as e:
            # Handle other HTTP errors, like invalid token
            log.warning(f"Failed to edit message when returning to chapters: {e}")

class PageButton(discord.ui.Button):
    def __init__(self, label: str, disabled: bool, direction: int):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, disabled=disabled, row=1)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        # Update active view reference
        if hasattr(self.view.bot, 'get_cog'):
            player_cog = self.view.bot.get_cog('PlayerCog')
            if player_cog:
                player_cog.active_views[interaction.guild.id] = self.view

        self.view.current_page += self.direction
        self.view.update_view()
        await interaction.response.edit_message(view=self.view)

class ChapterPageButton(discord.ui.Button):
    def __init__(self, label: str, disabled: bool, direction: int):
        super().__init__(label=label, style=discord.ButtonStyle.primary, disabled=disabled, row=1)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        player_cog = self.view.bot.get_cog('PlayerCog')
        guild_id = interaction.guild.id

        # Always use the shared view for state changes
        if player_cog and guild_id in player_cog.active_views:
            view = player_cog.active_views[guild_id]
        else:
            view = self.view

        # Update the chapter page on the shared view
        view.current_chapter_page += self.direction
        view.update_view()
        
        # Update the UI on the current panel (self.view)
        await interaction.response.edit_message(view=self.view)

class PauseButton(discord.ui.Button):
    def __init__(self, is_paused: bool = False):
        label = "▶️ Resume" if is_paused else "⏸️ Pause"
        super().__init__(label=label, style=discord.ButtonStyle.success, row=0)
        self.is_paused = is_paused

    async def callback(self, interaction: discord.Interaction):
        player_cog = self.view.bot.get_cog('PlayerCog')
        guild_id = interaction.guild.id

        # Always use the shared view
        if player_cog and guild_id in player_cog.active_views:
            view = player_cog.active_views[guild_id]
        else:
            view = self.view

        voice_client = discord.utils.get(self.view.bot.voice_clients, guild=interaction.guild)
      
        if not voice_client or not voice_client.is_connected():
            if view.is_paused:
                await interaction.response.send_message("Reconnecting to voice channel...", ephemeral=True)
                pause_duration = time.time() - view.pause_start_time
                resume_time = view.current_seek + pause_duration
                await playback_handler.play_audio(interaction, view, seek_time=resume_time)
                return
            else:
                await interaction.response.send_message("Not connected to voice!", ephemeral=True)
                return
      
        if voice_client.is_paused():
            voice_client.resume()
            view.is_paused = False
            pause_duration = time.time() - view.pause_start_time
            view.play_start_time += pause_duration
            log.info(f"Resumed playback (was paused for {pause_duration:.1f}s)")
        elif voice_client.is_playing():
            voice_client.pause()
            view.is_paused = True
            view.pause_start_time = time.time()
            log.info("Paused playback")
        else:
            await interaction.response.send_message("Nothing is currently playing!", ephemeral=True)
            return
      
        # Update presence
        try:
            if view.is_paused:
                presence_text = audio_utils.format_presence_text(
                    view.selected_chapter_path,
                    view.selected_book_path,
                    is_paused=True
                )
            else:
                current_elapsed = view.current_seek + (time.time() - view.play_start_time)
                presence_text = audio_utils.format_presence_text(
                    view.selected_chapter_path,
                    view.selected_book_path,
                    elapsed_seconds=current_elapsed
                )
            
            activity = discord.Activity(type=discord.ActivityType.listening, name=presence_text)
            await self.view.bot.change_presence(activity=activity)
        except Exception as e:
            log.warning(f"Failed to update presence on pause/resume: {e}")

        # Update the button and view
        self.view.update_player_view()
        await interaction.response.edit_message(view=self.view)

class QuitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🚪 Quit", style=discord.ButtonStyle.danger, row=2)

    async def callback(self, interaction: discord.Interaction):
        player_cog = self.view.bot.get_cog('PlayerCog')
        guild_id = interaction.guild.id

        # Always use the shared view
        if player_cog and guild_id in player_cog.active_views:
            view = player_cog.active_views[guild_id]
        else:
            view = self.view

        # Stop playback and mark as manual stop
        voice_client = discord.utils.get(self.view.bot.voice_clients, guild=interaction.guild)
        if voice_client:
            if voice_client.is_playing() or voice_client.is_paused():
                view.manual_stop = True
                voice_client.stop()
          
            await voice_client.disconnect()
            log.info(f"Bot disconnected from voice channel by {interaction.user}")
      
        # Reset all player state
        view.is_playing = False
        view.is_paused = False
        view.pause_start_time = 0
        view.time_tracker_running = False
        view.current_seek = 0
        view.play_start_time = 0
        view.duration = 0

        # --- CLEANUP ---
        if hasattr(view, 'messages'):
            view.messages.clear()
        view.message = None
        # -----------------

        # Clear Discord presence
        try:
            await self.view.bot.change_presence(activity=None)
            log.info("Cleared presence - user quit")
        except Exception as e:
            log.warning(f"Failed to clear presence on quit: {e}")
        
        # Clear the active view
        if player_cog and guild_id in player_cog.active_views:
            del player_cog.active_views[guild_id]

        self.view.clear_items()
      
        # Safe message editing with error handling
        try:
            await interaction.response.edit_message(
                content="👋 Disconnected from voice channel. Use `/audiobook` to start again.",
                view=None
            )
        except discord.errors.NotFound:
            # Message was deleted or interaction expired
            log.warning("Could not edit message - message not found or interaction expired")
        except discord.errors.HTTPException as e:
            # Handle other HTTP errors, like invalid token
            log.warning(f"Failed to edit message on quit: {e}")

# --- Main Cog Class ---

class PlayerCog(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.active_views = {}  # key: guild.id, value: AudiobookPlayerView
        if not os.path.exists(AUDIOBOOK_PATH):
            os.makedirs(AUDIOBOOK_PATH)
            log.warning(f"The '{AUDIOBOOK_PATH}' directory did not exist. I've created it for you.")

    @discord.slash_command(name="audiobook", description="Starts the interactive audiobook player.")
    async def audiobook(self, interaction: discord.Interaction):
        log.info(f"'/audiobook' command invoked by {interaction.user} in guild '{interaction.guild.name}'.")
        view = AudiobookPlayerView(interaction.user, self.bot)
        if not view.all_items:
            await interaction.response.send_message("I couldn't find any audiobooks! Make sure your folders are set up correctly.", ephemeral=True)
            return
        await interaction.response.send_message("Please choose an audiobook from the list.", view=view, ephemeral=True)

    @discord.slash_command(name="stop", description="Stops audio playback and disconnects the bot.")
    async def stop(self, interaction: discord.Interaction):
        log.info(f"'/stop' command invoked by {interaction.user} in guild '{interaction.guild.name}'.")
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_connected():
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            await voice_client.disconnect()
            
            # --- CLEANUP TRACKED MESSAGES ---
            view = self.active_views.get(interaction.guild.id)
            if view:
                if hasattr(view, 'messages'):
                    view.messages.clear()
                view.message = None
                del self.active_views[interaction.guild.id]
            # --------------------------------
            
            await interaction.response.send_message("🚪 Playback stopped and disconnected.", ephemeral=True)
        else:
            await interaction.response.send_message("I'm not currently in a voice channel.", ephemeral=True)

    @discord.slash_command(name="controls", description="Reopen the audiobook player controls panel.")
    async def controls(self, interaction: discord.Interaction):
        log.info(f"'/controls' command invoked by {interaction.user} in guild '{interaction.guild.name}'.")
        
        # Try to get the active view for this guild
        view = self.active_views.get(interaction.guild.id)
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        
        if not view or not voice_client or (not voice_client.is_playing() and not voice_client.is_paused()):
            await interaction.response.send_message("No audiobook is currently playing. Use `/audiobook` to start one.", ephemeral=True)
            return
        
        # **NEW: Refresh the view's interaction context**
        view.interaction = interaction  # Update to the fresh interaction
        
        # Calculate current elapsed time
        if view.is_paused:
            elapsed = view.current_seek + (view.pause_start_time - view.play_start_time)
        else:
            elapsed = view.current_seek + (time.time() - view.play_start_time)
        
        # Get current chapter and book info
        chapter_title = audio_utils.get_book_title(view.selected_chapter_path)
        book_title = os.path.basename(os.path.dirname(view.selected_book_path))
        elapsed_str = audio_utils.format_time(elapsed)
        duration_str = audio_utils.format_time(view.duration)

        # Update the view to show current player controls
        view.update_player_view()
        
        status_emoji = "⏸️" if view.is_paused else "▶️"
        message = f"{status_emoji} Now playing: **{chapter_title}** from *{book_title}*\n`{elapsed_str} / {duration_str}`"
        
        # Send the controls using the refreshed view
        await interaction.response.send_message(message, view=view, ephemeral=True)
        
        # **NEW: Track this message for live updates**
        try:
            new_message = await interaction.original_message()
            # Initialize messages set if it doesn't exist
            if not hasattr(view, 'messages'):
                view.messages = set()
            view.messages.add(new_message)
            log.info(f"Added new controls message to tracking (total: {len(view.messages)})")
        except Exception as e:
            log.warning(f"Could not track new controls message: {e}")

# Updated setup function for discord.py
def setup(bot: commands.AutoShardedBot):
    bot.add_cog(PlayerCog(bot))