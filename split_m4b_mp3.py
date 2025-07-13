# split_m4b_mp3.py
import tkinter as tk
from tkinter import filedialog
from mutagen.mp4 import MP4
from mutagen.id3 import ID3
import os
import subprocess
import re
import sys
import json
import multiprocessing

# --- Performance Tuning Configuration ---
CPU_CORES = os.cpu_count()
MAX_CONCURRENT_JOBS = max(1, CPU_CORES // 2) 
# --- End of Configuration ---

def sanitize_filename(name):
    """Removes characters that are invalid for file/folder names."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def get_source_metadata(filepath, file_ext):
    """
    SIMPLIFIED: Reads metadata from the source file. Cover art is now handled by FFmpeg.
    """
    metadata = {
        'author': 'Unknown Author', 'album': 'Unknown Album', 'album_artist': None,
        'genre': None, 'year': None, 'comment': None
    }
    try:
        if file_ext == '.m4b':
            audio = MP4(filepath).tags
            metadata['author'] = audio.get('©ART', ['Unknown Author'])[0]
            metadata['album'] = audio.get('©alb', [os.path.splitext(os.path.basename(filepath))[0]])[0]
            metadata['album_artist'] = audio.get('aART', [metadata['author']])[0]
            metadata['genre'] = audio.get('©gen', [None])[0]
            metadata['year'] = audio.get('©day', [None])[0]
            metadata['comment'] = audio.get('©cmt', [None])[0]
        elif file_ext == '.mp3':
            audio = ID3(filepath)
            metadata['author'] = str(audio.get('TPE1', 'Unknown Author'))
            metadata['album'] = str(audio.get('TALB', os.path.splitext(os.path.basename(filepath))[0]))
            metadata['album_artist'] = str(audio.get('TPE2', metadata['author']))
            metadata['genre'] = str(audio.get('TCON', '')) or None
            metadata['year'] = str(audio.get('TDRC', str(audio.get('TYER', '')))) or None
            if 'COMM::XXX' in audio:
                metadata['comment'] = audio['COMM::XXX'].text[0]
    except Exception as e:
        print(f"Warning: Could not read all tags from {filepath}. Error: {e}")
  
    metadata['author'] = sanitize_filename(metadata['author'])
    metadata['album'] = sanitize_filename(metadata['album'])
    return metadata

def retag_m4b_file(output_path, source_metadata, chapter_title, chapter_num, total_chapters):
    """
    SIMPLIFIED: Writes the metadata tags. Cover art is no longer handled here.
    """
    try:
        new_file = MP4(output_path)
        # We don't delete tags, as FFmpeg has already copied most of them. We just add/overwrite.
        new_file.tags['©ART'] = source_metadata['author']
        new_file.tags['©alb'] = source_metadata['album']
        new_file.tags['©nam'] = chapter_title
        new_file.tags['trkn'] = [(chapter_num, total_chapters)]
        if source_metadata.get('album_artist'):
            new_file.tags['aART'] = source_metadata['album_artist']
        if source_metadata.get('year'):
            new_file.tags['©day'] = source_metadata['year']
        if source_metadata.get('genre'):
            new_file.tags['©gen'] = source_metadata['genre']
        if source_metadata.get('comment'):
            new_file.tags['©cmt'] = source_metadata['comment']
        new_file.save()
        print(f"     [SUCCESS] Finished Chapter {chapter_num}/{total_chapters}: {os.path.basename(output_path)}")
    except Exception as e:
        print(f"     [ERROR] Failed to re-tag chapter {chapter_num}. Error: {e}")

def process_single_chapter(args):
    """A dedicated function to process one chapter."""
    filepath, file_ext, output_dir, source_metadata, chapter, chapter_num, total_chapters, threads_per_job = args

    start_time = chapter['start_time']
    end_time = chapter['end_time']
    chapter_title = chapter.get('tags', {}).get('title', f"Chapter {chapter_num}")
    sanitized_chapter_title = sanitize_filename(chapter_title)
    output_filename = f"{chapter_num:03d} - {sanitized_chapter_title}.m4b"
    output_path = os.path.join(output_dir, output_filename)

    print(f"  -> Starting Chapter {chapter_num}/{total_chapters}: {chapter_title}")

    # --- OVERHAULED FFmpeg COMMAND ---
    ffmpeg_command = [
        'ffmpeg', '-i', filepath, '-ss', str(start_time), '-to', str(end_time),
        '-map', '0:a', '-map', '0:v?', # Map audio and optional video (cover)
        '-c:v', 'copy' # Copy the video (cover) stream directly
    ]
  
    if file_ext == '.m4b':
        ffmpeg_command.extend(['-c:a', 'copy']) # Copy the audio stream
    else:
        print(f"     (Re-encoding MP3 to AAC for Chapter {chapter_num} using {threads_per_job} threads)")
        ffmpeg_command.extend(['-c:a', 'aac', '-b:a', '64k', '-threads', str(threads_per_job)])
  
    ffmpeg_command.extend(['-y', '-loglevel', 'error', output_path])
  
    try:
        subprocess.run(ffmpeg_command, check=True, text=True, encoding='utf-8', errors='ignore')
    except subprocess.CalledProcessError:
        print(f"     [ERROR] FFmpeg failed for chapter {chapter_num}. Skipping.")
        return

    retag_m4b_file(output_path, source_metadata, chapter_title, chapter_num, total_chapters)

def split_audiobook():
    """Main function to select and split audiobooks into chapters."""
    root = tk.Tk()
    root.withdraw()

    print("Opening file explorer to select the ROOT audiobook directory...")
    input_root_dir = filedialog.askdirectory(
        title="Select the folder containing your audiobooks"
    )

    if not input_root_dir:
        print("No directory selected. Exiting.")
        return

    # --- NEW: Robust Logging Section ---
    print("\n" + "-"*40)
    print(f"Scanning for audiobooks in: {input_root_dir}")
    print("-" * 40)
    
    filepaths = []
    skipped_file_count = 0
    valid_extensions = ('.m4b', '.mp3')
    
    for dirpath, _, filenames in os.walk(input_root_dir):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            if filename.lower().endswith(valid_extensions):
                print(f"  [FOUND]   {full_path}")
                filepaths.append(full_path)
            else:
                print(f"  [SKIPPED] Ignoring non-audio file: {full_path}")
                skipped_file_count += 1
    
    print("-" * 40)
    print(f"Scan Complete. Found {len(filepaths)} audiobook(s). Skipped {skipped_file_count} other file(s).")
    print("-" * 40 + "\n")
    # --- END: Robust Logging Section ---

    if not filepaths:
        print(f"No audiobooks (.m4b or .mp3) found to process. Exiting.")
        return

    print("Opening file explorer to select an output directory...")
    output_base_dir = filedialog.askdirectory(title="Select Output Folder (or Cancel to use source folder)")

    if output_base_dir:
        print(f"Selected output destination: {output_base_dir}")
    else:
        print("No output folder selected. Chapters will be saved next to their source files.")

    for filepath in filepaths:
        print(f"\n{'='*60}")
        print(f"Processing: {os.path.basename(filepath)}")
        print(f"Located at: {os.path.dirname(filepath)}")
        print(f"{'='*60}")

        file_ext = os.path.splitext(filepath)[1].lower()
        if file_ext not in valid_extensions:
            print(f"Unsupported file type: {file_ext}. Skipping.")
            continue

        source_metadata = get_source_metadata(filepath, file_ext)
        base_path = output_base_dir if output_base_dir else os.path.dirname(filepath)
        output_dir = os.path.join(base_path, source_metadata['author'], source_metadata['album'])
      
        print(f"Author: {source_metadata['author']}\nAudiobook: {source_metadata['album']}\nOutputting to: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)

        try:
            ffprobe_command = ['ffprobe', '-v', 'error', '-print_format', 'json', '-show_chapters', '-i', filepath]
            result = subprocess.run(ffprobe_command, capture_output=True, text=True, check=True, encoding='utf-8')
            chapters = json.loads(result.stdout).get('chapters', [])
            if not chapters:
                print("ffprobe found no embedded chapter data. Cannot split this file. Skipping.")
                continue
        except Exception as e:
            print(f"Error getting chapters with ffprobe: {e}. Skipping.")
            continue

        total_chapters = len(chapters)
        threads_per_job = max(1, CPU_CORES // MAX_CONCURRENT_JOBS)
        print(f"Found {total_chapters} chapters. Starting parallel processing...")
        print(f"Configuration: {MAX_CONCURRENT_JOBS} concurrent jobs, with up to {threads_per_job} threads per job.")

        jobs = []
        for i, chapter in enumerate(chapters):
            args = (filepath, file_ext, output_dir, source_metadata, chapter, i + 1, total_chapters, threads_per_job)
            jobs.append(args)

        with multiprocessing.Pool(processes=MAX_CONCURRENT_JOBS) as pool:
            pool.map(process_single_chapter, jobs)

        print(f"\nFinished processing {os.path.basename(filepath)}.")

if __name__ == "__main__":
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        subprocess.run(['ffprobe', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n--- FFmpeg/FFprobe NOT FOUND ---")
        print("This script requires FFmpeg to be installed and accessible in your system's PATH.")
        sys.exit(1)

    split_audiobook()