# cogs/audio_utils.py
import os
import subprocess
import json
import logging
from mutagen.mp4 import MP4

log = logging.getLogger(__name__)

def _run_ffprobe(file_path: str) -> dict:
    """Runs ffprobe on a file and returns the JSON output."""
    try:
        if os.name == 'nt' and not file_path.startswith('\\\\?\\'):
            file_path = '\\\\?\\' + os.path.abspath(file_path)
        # log.info(f"Running ffprobe on: {file_path} (length: {len(file_path)})")
        command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            check=True, 
            encoding='utf-8',
            timeout=10
        )
        return json.loads(result.stdout)
    except FileNotFoundError:
        log.critical("!!! ffprobe not found! Make sure FFmpeg is installed and in your system's PATH. !!!")
        return {}
    except subprocess.TimeoutExpired:
        log.error(f"ffprobe timed out for file {file_path}")
        return {}
    except subprocess.CalledProcessError as e:
        log.error(f"ffprobe failed for file {file_path}: {e.stderr}")
        return {}
    except json.JSONDecodeError:
        log.error(f"Failed to decode JSON from ffprobe for file {file_path}")
        return {}

def get_book_title_from_data(data, file_path):
    tags = data.get('format', {}).get('tags', {})
    title = tags.get('title', tags.get('TITLE'))
    if title:
        return title
    return os.path.basename(file_path)

def get_track_number_from_data(data, file_path):
    tags = data.get('format', {}).get('tags', {})
    track_str = tags.get('track', tags.get('TRACK'))
    if track_str:
        try:
            return int(track_str.split('/')[0])
        except (ValueError, IndexError):
            log.warning(f"Could not parse track number '{track_str}' for {file_path}.")
            return 0
    return 0

def get_book_title(file_path: str) -> str:
    """Gets the title from a media file's metadata using ffprobe."""
    data = _run_ffprobe(file_path)
    tags = data.get('format', {}).get('tags', {})
    title = tags.get('title', tags.get('TITLE'))
  
    if title:
        return title
    return os.path.basename(file_path)

def get_synopsis(book_path: str) -> str:
    """Gets the synopsis from the first chapter file of a book using ffprobe."""
    log.debug(f"Attempting to get synopsis for book path: {book_path}")
    try:
        chapter_files = sorted([f for f in os.listdir(book_path) if f.endswith('.m4b')])
        if not chapter_files:
            log.warning(f"No .m4b files found in {book_path} to get synopsis from.")
            return "No chapter files found to read synopsis from."

        first_chapter_file = chapter_files[0]
        full_path = os.path.join(book_path, first_chapter_file)
        log.debug(f"Selected file for synopsis lookup: {full_path}")

        data = _run_ffprobe(full_path)
        if not data:
            log.error(f"ffprobe returned no data for synopsis file: {full_path}")
            return "Could not read metadata from chapter file."

        tags = data.get('format', {}).get('tags', {})
        synopsis = tags.get('synopsis', tags.get('description', tags.get('comment')))
      
        if synopsis:
            log.info(f"Successfully found synopsis for {book_path}.")
            return synopsis.replace('\\n', '\n')
        else:
            log.warning(f"No synopsis, description, or comment tag found for {full_path}.")
            return "No synopsis available in the file's metadata."

    except Exception as e:
        log.error(f"An unexpected error occurred while getting synopsis for {book_path}: {e}", exc_info=True)
        return "An error occurred while trying to retrieve the synopsis."

def extract_cover_image(file_path, output_path=None):
    """
    Extracts the embedded cover image from an .m4b file.
    If output_path is given, saves the image there and returns the path.
    Otherwise, returns the image bytes (or None if not found).
    """
    try:
        audio = MP4(file_path)
        if 'covr' in audio:
            cover = audio['covr'][0]
            if output_path:
                with open(output_path, "wb") as img:
                    img.write(cover)
                return output_path
            return cover  # bytes
        else:
            return None
    except Exception as e:
        log.error(f"Failed to extract cover image from {file_path}: {e}")
        return None

def get_track_number(file_path: str) -> int:
    """Gets the track number from a media file's metadata using ffprobe."""
    data = _run_ffprobe(file_path)
    tags = data.get('format', {}).get('tags', {})
    track_str = tags.get('track', tags.get('TRACK'))
  
    if track_str:
        try:
            return int(track_str.split('/')[0])
        except (ValueError, IndexError):
            log.warning(f"Could not parse track number '{track_str}' for {file_path}.")
            return 0
    return 0

def get_books_and_series(audiobook_path: str) -> list:
    """
    Scans the audiobook directory and returns a list of:
      - Standalone books (Author/Book)
      - Series (Author/Series/Book)
    Each entry is either:
      {'type': 'book', 'title': ..., 'path': ..., 'author': ...}
      or
      {'type': 'series', 'title': ..., 'path': ..., 'author': ..., 'books': [...]}
    """
    items = []
    if not os.path.exists(audiobook_path):
        return items

    for author_name in os.listdir(audiobook_path):
        author_path = os.path.join(audiobook_path, author_name)
        if not os.path.isdir(author_path):
            continue

        for item_name in os.listdir(author_path):
            item_path = os.path.join(author_path, item_name)
            if not os.path.isdir(item_path):
                continue

            # Check if this is a book (contains .m4b files) or a series (contains subfolders)
            has_m4b = any(f.endswith('.m4b') for f in os.listdir(item_path))
            has_subdirs = any(os.path.isdir(os.path.join(item_path, f)) for f in os.listdir(item_path))

            if has_m4b and not has_subdirs:
                # Standalone book: Author/Book
                items.append({
                    'type': 'book',
                    'title': item_name,
                    'path': item_path,
                    'author': author_name
                })
            elif has_subdirs:
                # Series: Author/Series/Book
                books_in_series = []
                for book_name in os.listdir(item_path):
                    book_path = os.path.join(item_path, book_name)
                    if os.path.isdir(book_path):
                        books_in_series.append({
                            'title': book_name,
                            'path': book_path
                        })
                if books_in_series:
                    items.append({
                        'type': 'series',
                        'title': item_name,
                        'path': item_path,
                        'author': author_name,
                        'books': books_in_series
                    })

    items.sort(key=lambda x: x['title'])
    log.info(f"Found {len(items)} items (books and series).")
    return items

def get_duration(file_path: str) -> float:
    """Returns the duration of the audio file in seconds."""
    data = _run_ffprobe(file_path)
    duration_str = data.get('format', {}).get('duration', '0')
    try:
        return float(duration_str)
    except (ValueError, TypeError):
        log.warning(f"Could not parse duration for {file_path}")
        return 0.0

def format_time(seconds: float) -> str:
    """Formats seconds as HH:MM:SS.000."""
    if seconds < 0:
        seconds = 0
    ms = int((seconds - int(seconds)) * 1000)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"

def get_chapter_index_by_path(chapters: list, chapter_path: str) -> int:
    """Returns the index of a chapter in the chapters list by its file path."""
    for i, chapter in enumerate(chapters):
        if chapter_path.endswith(chapter['filename']):
            return i
    return -1

def get_next_chapter(chapters: list, current_index: int) -> dict:
    """Returns the next chapter info, or None if at the end."""
    if current_index < len(chapters) - 1:
        return chapters[current_index + 1]
    return None

def get_previous_chapter(chapters: list, current_index: int) -> dict:
    """Returns the previous chapter info, or None if at the beginning."""
    if current_index > 0:
        return chapters[current_index - 1]
    return None

def format_presence_text(chapter_path: str, book_path: str, elapsed_seconds: float = None, is_paused: bool = False) -> str:
    """
    Formats text for Discord presence/status display.
    Returns a concise string suitable for bot status.
    """
    chapter_title = get_book_title(chapter_path)
    book_title = os.path.basename(book_path)
    
    # Truncate long titles to fit Discord's presence limits (128 chars max)
    if len(chapter_title) > 30:
        chapter_title = chapter_title[:27] + "..."
    if len(book_title) > 25:
        book_title = book_title[:22] + "..."
    
    base_text = f"{chapter_title} - {book_title}"
    
    if is_paused:
        return f"⏸️ {base_text}"
    elif elapsed_seconds is not None:
        # Show progress for longer content
        if elapsed_seconds > 300:  # 5+ minutes, show time
            elapsed_str = format_time(elapsed_seconds)
            return f"🎧 {base_text} ({elapsed_str})"
    
    return f"🎧 {base_text}"