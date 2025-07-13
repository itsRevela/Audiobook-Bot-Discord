# cogs/playback_handler.py
import nextcord as discord
import asyncio
import logging
import os
import time
from . import audio_utils

log = logging.getLogger(__name__)

async def play_audio(interaction: discord.Interaction, view, seek_time=0, is_scrub=False, is_auto_advance=False):
    # state handling
    log.info(f"Play audio request - Guild: {interaction.guild.name} ({interaction.guild.id}), User: {interaction.user}")
    log.info(f"Current voice clients: {[(vc.guild.name, vc.channel.name if vc.channel else 'None') for vc in interaction.client.voice_clients]}")

    audio_path = view.selected_chapter_path
    log.info(f"Playback requested by {interaction.user} in guild '{interaction.guild.name}' at seek time {seek_time}s.")
    log.debug(f"File path for playback: '{audio_path}'")

    voice_client = discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)

    try:
        # --- Connection Logic ---
        if not voice_client or not voice_client.is_connected():
            if not view.selected_channel:
                log.error("No voice channel selected for connection.")
                if not is_auto_advance:
                    await interaction.followup.send("Please select a voice channel first!", ephemeral=True)
                return
                
            log.info(f"Connecting to '{view.selected_channel.name}' ({view.selected_channel.id}).")
            
            # Disconnect any existing connection first
            if voice_client:
                await voice_client.disconnect(force=True)
                await asyncio.sleep(1)

            # Connect with timeout
            voice_client = await view.selected_channel.connect(timeout=20.0, reconnect=False)
            log.info("Successfully connected to voice channel.")
            
            # Wait for connection to stabilize
            await asyncio.sleep(2)
        elif voice_client.channel != view.selected_channel:
            # Move to different channel if needed
            await voice_client.move_to(view.selected_channel)
            if view.selected_channel:
                log.info(f"Moved to channel: {view.selected_channel.name}")
            else:
                log.info("Moved to voice channel (channel reference not set)")

        # --- Stop Existing Playback (Robust Wait) ---
        if voice_client.is_playing() or voice_client.is_paused():
            log.info("Voice client is currently playing or paused. Stopping current playback.")
            view.manual_stop = True
            voice_client.stop()
            # Wait until the client is actually stopped (max 2 seconds)
            for _ in range(20):
                await asyncio.sleep(0.1)
                if not voice_client.is_playing() and not voice_client.is_paused():
                    break
            else:
                log.warning("Voice client did not stop after 2 seconds, proceeding anyway.")
        else:
            log.info("Voice client appears to be idle.")

        # --- Get audio duration and set up tracking ---
        duration = audio_utils.get_duration(audio_path)
        view.current_seek = seek_time
        view.play_start_time = time.time()
        view.is_playing = True
        view.is_paused = False
        view.pause_start_time = 0
        view.duration = duration
        view.interaction = interaction
        view.manual_stop = False

        # --- Create the message content ---
        chapter_title = audio_utils.get_book_title(audio_path)
        book_title = os.path.basename(os.path.dirname(view.selected_book_path))
        elapsed_str = audio_utils.format_time(seek_time)
        duration_str = audio_utils.format_time(duration)

        message = f"▶️ Now playing: **{chapter_title}** from *{book_title}*\n`{elapsed_str} / {duration_str}`"

        # Update the view to show player controls (only if not scrubbing)
        if not is_scrub:
            view.update_player_view()

        await safe_update_message(interaction, view, message, is_auto_advance)

        # --- Audio Source Creation and Playback ---
        log.info(f"Preparing to create FFmpeg audio source for: {audio_path} at {seek_time}s")
    
        # Create audio source with seeking if needed
        if seek_time > 0:
            ffmpeg_options = f"-vn -ss {seek_time}"
            source = discord.FFmpegPCMAudio(audio_path, options=ffmpeg_options)
        else:
            source = discord.FFmpegPCMAudio(audio_path)
    
        log.info("Successfully created FFmpeg audio source.")

        if not voice_client.is_connected():
            log.error("Voice client disconnected while audio was being prepared. Aborting playback.")
            if not is_auto_advance:
                await interaction.followup.send("Sorry, I was disconnected from the voice channel while preparing the audio.", ephemeral=True)
            return
    
        log.info(f"Initiating playback on voice client for guild {interaction.guild.id}.")

        def after_play(error):
            if error:
                log.error(f'Player error: {error}')
                view.is_playing = False
            else:
                log.info(f"Playback finished for file: {audio_path}")
                view.is_playing = False
          
                # Check manual_stop flag BEFORE any resets
                should_auto_advance = not getattr(view, 'manual_stop', False)
              
                if should_auto_advance:
                    log.info("Natural playback end detected, attempting auto-advance")
                    loop = view.bot.loop
                    asyncio.run_coroutine_threadsafe(auto_advance_chapter(view), loop)
                else:
                    log.info("Manual stop detected, skipping auto-advance")
                    # Reset manual_stop only after checking it
                    view.manual_stop = False

        voice_client.play(source, after=after_play)

        # Only reset manual_stop if playback started successfully AND this wasn't a manual stop
        if not getattr(view, 'manual_stop', False):
            view.manual_stop = False
            log.info("Playback started successfully, reset manual_stop flag")
        else:
            log.info("Playback started after manual stop, keeping manual_stop flag")

        # Update Discord presence
        try:
            presence_text = audio_utils.format_presence_text(
                audio_path, 
                view.selected_book_path, 
                elapsed_seconds=seek_time
            )
            activity = discord.Activity(type=discord.ActivityType.listening, name=presence_text)
            await view.bot.change_presence(activity=activity)
            log.info(f"Updated presence: {presence_text}")
        except Exception as e:
            log.warning(f"Failed to update presence: {e}")

        # Start time tracker task (only if not already running)
        if not hasattr(view, 'time_tracker_running') or not view.time_tracker_running:
            view.time_tracker_running = True
            asyncio.create_task(update_time_tracker(view))

    except discord.errors.ConnectionClosed as e:
        log.error(f"Voice connection closed: {e}")
        if not is_auto_advance:
            await interaction.followup.send("Voice connection failed. This might be a Discord server issue. Try again in a moment.", ephemeral=True)
    except asyncio.TimeoutError:
        log.error("Connection to voice channel timed out.")
        if not is_auto_advance:
            await interaction.followup.send("I couldn't connect to the voice channel in time. Please try again.", ephemeral=True)
    except Exception:
        log.exception("An unexpected error occurred during audio connection or playback.")
        if not is_auto_advance:
            await interaction.followup.send("Sorry, I couldn't play that file. An unexpected error occurred.", ephemeral=True)

async def safe_update_message(interaction: discord.Interaction, view, message: str, is_auto_advance: bool = False):
    """Safely update message, handling token expiry gracefully"""
    try:
        # Try to edit the original interaction message first
        await interaction.edit_original_message(content=message, view=view)
        
        # Store the message reference for future updates
        try:
            original_message = await interaction.original_message()
            if not hasattr(view, 'messages'):
                view.messages = set()
            view.messages.add(original_message)
            view.message = original_message
            log.info(f"Added original message to tracking (total: {len(view.messages)})")
        except Exception as e:
            log.warning(f"Could not get original response message for tracking: {e}")
            
    except discord.errors.HTTPException as e:
        if e.status == 401 and e.code == 50027:
            # Token expired - send new message to channel instead
            log.warning("Interaction token expired, sending new message to channel")
            try:
                new_message = await interaction.channel.send(content=message, view=view)
                
                # Update tracking with new message
                if not hasattr(view, 'messages'):
                    view.messages = set()
                view.messages.add(new_message)
                view.message = new_message
                log.info("Successfully sent new message after token expiry")
                
            except Exception as fallback_error:
                log.error(f"Failed to send fallback message: {fallback_error}")
        else:
            # Re-raise other HTTP exceptions
            raise
    except Exception as e:
        log.error(f"Unexpected error updating message: {e}")
        if not is_auto_advance:
            raise

async def auto_advance_chapter(view):
    """Auto-advances to the next chapter when current chapter finishes."""
    try:
        # Check if there's a next chapter
        next_chapter = audio_utils.get_next_chapter(view.all_chapters, view.current_chapter_index)
      
        if next_chapter:
            log.info(f"Auto-advancing to next chapter: {next_chapter['title']}")
          
            # Update to next chapter
            view.current_chapter_index += 1
            view.selected_chapter_path = os.path.join(view.selected_book_path, next_chapter['filename'])
          
            await play_audio(view.interaction, view, seek_time=0, is_auto_advance=True)

            # Update presence for new chapter
            try:
                presence_text = audio_utils.format_presence_text(
                    view.selected_chapter_path, 
                    view.selected_book_path
                )
                activity = discord.Activity(type=discord.ActivityType.listening, name=presence_text)
                await view.bot.change_presence(activity=activity)
            except Exception as e:
                log.warning(f"Failed to update presence during auto-advance: {e}")
        else:
            log.info("Reached end of audiobook. Returning to chapter list.")
          
            # Update UI to show chapter list
            view.is_playing = False
            view.time_tracker_running = False

            # Clear presence when audiobook ends
            try:
                await view.bot.change_presence(activity=None)
                log.info("Cleared presence - audiobook finished")
            except Exception as e:
                log.warning(f"Failed to clear presence: {e}")

            view.update_view()
          
            await safe_channel_message(
                view, 
                "🎉 Audiobook finished! Select another chapter to continue."
            )
            
    except Exception as e:
        log.error(f"Error in auto-advance: {e}")
        view.is_playing = False
        view.time_tracker_running = False

async def safe_channel_message(view, content: str):
    """Send a message to the channel, bypassing interaction tokens entirely"""
    try:
        # Try to update existing tracked messages first
        if hasattr(view, 'messages') and view.messages:
            messages_to_remove = set()
            updated_any = False
            
            for message in list(view.messages):
                try:
                    await message.edit(content=content, view=view)
                    updated_any = True
                    break  # Successfully updated one message, that's enough
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    messages_to_remove.add(message)
            
            # Clean up expired messages
            view.messages -= messages_to_remove
            
            if updated_any:
                return
        
        # Fallback: send new message to channel
        if hasattr(view, 'interaction') and view.interaction.channel:
            new_message = await view.interaction.channel.send(content=content, view=view)
            
            # Track the new message
            if not hasattr(view, 'messages'):
                view.messages = set()
            view.messages.add(new_message)
            view.message = new_message
            log.info("Sent new message to channel as fallback")
            
    except Exception as e:
        log.error(f"Failed to send safe channel message: {e}")

async def update_time_tracker(view):
    """Updates the time display for all tracked messages"""
    while view.is_playing and view.time_tracker_running:
        try:
            # Calculate current progress
            if view.is_paused:
                current_elapsed = view.current_seek + (view.pause_start_time - view.play_start_time)
            else:
                current_elapsed = view.current_seek + (time.time() - view.play_start_time)
            
            # Get current chapter and book info
            chapter_title = audio_utils.get_book_title(view.selected_chapter_path)
            book_title = os.path.basename(os.path.dirname(view.selected_book_path))
            elapsed_str = audio_utils.format_time(current_elapsed)
            duration_str = audio_utils.format_time(view.duration)
            
            status_emoji = "⏸️" if view.is_paused else "▶️"
            new_content = f"{status_emoji} Now playing: **{chapter_title}** from *{book_title}*\n`{elapsed_str} / {duration_str}`"
            
            # Update all tracked messages
            if hasattr(view, 'messages'):
                messages_to_remove = set()
                for message in list(view.messages):
                    try:
                        await message.edit(content=new_content, view=view)
                    except discord.NotFound:
                        messages_to_remove.add(message)
                        log.debug("Removed expired message from tracking")
                    except discord.Forbidden:
                        messages_to_remove.add(message)
                        log.debug("Removed forbidden message from tracking")
                    except discord.HTTPException as e:
                        if "Invalid Webhook Token" in str(e) or e.code == 50027:
                            messages_to_remove.add(message)
                            log.warning("Webhook token expired - removing message from tracking")
                        else:
                            log.warning(f"Failed to update message: {e}")
                    except Exception as e:
                        log.warning(f"Unexpected error updating message: {e}")
                
                # Remove expired/invalid messages
                view.messages -= messages_to_remove
                
                if messages_to_remove:
                    log.info(f"Cleaned up {len(messages_to_remove)} expired messages (remaining: {len(view.messages)})")

            # Fallback for backward compatibility
            elif view.message:
                try:
                    await view.message.edit(content=new_content, view=view)
                except discord.HTTPException as e:
                    if "Invalid Webhook Token" in str(e) or e.code == 50027:
                        log.warning("Main message webhook token expired - clearing reference")
                        view.message = None
                    else:
                        log.warning(f"Failed to update main message: {e}")
                except Exception as e:
                    log.warning(f"Failed to update main message: {e}")
            
        except Exception as e:
            log.error(f"Error in time tracker: {e}")
        
        await asyncio.sleep(5)  # Update every 5 seconds
    
    log.info("Time tracker stopped")