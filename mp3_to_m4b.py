# mp3_to_m4b.py
import tkinter as tk
from tkinter import filedialog
from mutagen.id3 import ID3
from mutagen.mp4 import MP4, MP4Cover
import os
import subprocess
import re
import sys
import tempfile
from natsort import natsorted

def check_dependencies():
    """Checks if FFmpeg and ffprobe are installed and in the system's PATH."""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, text=True)
        subprocess.run(['ffprobe', '-version'], capture_output=True, check=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n--- FFmpeg/FFprobe NOT FOUND ---")
        print("This script requires FFmpeg to be installed and accessible in your system's PATH.")
        print("Please install it and try again.")
        sys.exit(1)
    print("FFmpeg and ffprobe found.")

def sanitize_filename(name):
    """Removes characters that are invalid for file/folder names."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def parse_chapter_title(filename):
    """Extracts a clean chapter title from a filename."""
    title = os.path.splitext(filename)[0]
    title = re.sub(r'^\d+\s*[-.]?\s*', '', title)
    return title.strip()

def get_mp3_metadata(filepath):
    """Reads metadata and cover art from the first MP3 file."""
    metadata = {'author': 'Unknown Author', 'album': 'Unknown Album', 'cover_data': None}
    try:
        audio = ID3(filepath)
        metadata['author'] = sanitize_filename(str(audio.get('TPE1', 'Unknown Author')))
        metadata['album'] = sanitize_filename(os.path.basename(os.path.dirname(filepath)))
        
        if 'APIC:' in audio:
            metadata['cover_data'] = audio['APIC:'].data
        print(f"  - Found Metadata: Author='{metadata['author']}', Album='{metadata['album']}'")
        if metadata['cover_data']:
            print("  - Found embedded cover art.")
        else:
            print("  - No embedded cover art found in the first MP3.")
            
    except Exception as e:
        print(f"Warning: Could not read tags from {filepath}. Using defaults. Error: {e}")
    return metadata

def get_audio_duration(filepath):
    """Gets the duration of an audio file in seconds using ffprobe."""
    command = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', filepath
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error getting duration for {filepath}: {e}")
        return 0.0

def hms_to_seconds(t):
    """Converts HH:MM:SS.ss time string to seconds."""
    h, m, s = map(float, t.split(':'))
    return h * 3600 + m * 60 + s

def combine_chapters_to_m4b():
    """Main function to orchestrate the combination process."""
    root = tk.Tk()
    root.withdraw()

    print("Opening file explorer to select the FOLDER containing your MP3 chapters...")
    input_dir = filedialog.askdirectory(title="Select the folder of MP3 chapters")
    if not input_dir:
        print("No directory selected. Exiting."); return

    print("\nOpening file explorer to select the OUTPUT directory...")
    output_base_dir = filedialog.askdirectory(title="Select Output Folder")
    if not output_base_dir:
        print("No output folder selected. Exiting."); return

    print(f"\nProcessing folder: {input_dir}")

    mp3_files = natsorted([os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.lower().endswith('.mp3')])
    if not mp3_files:
        print("No MP3 files found in the selected directory. Exiting."); return
    
    print(f"Found {len(mp3_files)} MP3 files. Preparing to combine...")

    source_metadata = get_mp3_metadata(mp3_files[0])
    
    output_dir = os.path.join(output_base_dir, source_metadata['author'], source_metadata['album'])
    os.makedirs(output_dir, exist_ok=True)
    final_output_path = os.path.join(output_dir, f"{source_metadata['album']}.m4b")
    print(f"Output will be saved to: {final_output_path}")

    print("\nGenerating chapter map...")
    total_duration = 0.0
    ffmpeg_metadata_content = ";FFMETADATA1\n"
    
    temp_dir = tempfile.gettempdir()
    concat_list_filename = os.path.join(temp_dir, "concat_list.txt")
    metadata_filename = os.path.join(temp_dir, "metadata.txt")
    temp_audio_filename = os.path.join(temp_dir, "temp_audio.m4a")

    try:
        with open(concat_list_filename, 'w', encoding='utf-8') as concat_list_file:
            for i, mp3_file in enumerate(mp3_files):
                safe_path = mp3_file.replace("\\", "/").replace("'", "'\\''")
                concat_list_file.write(f"file '{safe_path}'\n")
                
                duration = get_audio_duration(mp3_file)
                end_time = total_duration + duration
                chapter_title = parse_chapter_title(os.path.basename(mp3_file))
                print(f"  - Chapter {i+1:02d}: '{chapter_title}' (Duration: {duration:.2f}s)")
                
                start_ms = int(total_duration * 1000)
                end_ms = int(end_time * 1000)
                
                ffmpeg_metadata_content += f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_ms}\nEND={end_ms}\ntitle={chapter_title}\n"
                total_duration = end_time
        
        print(f"\nTotal audiobook duration: {total_duration:.2f} seconds")

        with open(metadata_filename, 'w', encoding='utf-8') as meta_file:
            meta_file.write(ffmpeg_metadata_content)

        # --- REVISED FFmpeg LOGIC with PROGRESS BAR ---
        print("\n[Step 1/3] Combining and converting audio to AAC...")
        combine_command = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_filename,
            '-c:a', 'aac', '-b:a', '128k', '-vn', '-progress', 'pipe:1', temp_audio_filename
        ]
        
        # Use Popen to capture real-time output
        process = subprocess.Popen(combine_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', errors='ignore')
        
        for line in process.stdout:
            time_match = re.search(r"out_time=(\d{2}:\d{2}:\d{2}\.\d+)", line)
            if time_match:
                elapsed_time_str = time_match.group(1)
                elapsed_seconds = hms_to_seconds(elapsed_time_str)
                percent = (elapsed_seconds / total_duration) * 100
                bar_length = 30
                filled_len = int(bar_length * elapsed_seconds // total_duration)
                bar = '█' * filled_len + '-' * (bar_length - filled_len)
                print(f'\r  - Progress: |{bar}| {percent:.1f}%', end='', flush=True)
        
        process.wait()
        print("\n  - Conversion complete.")
        if process.returncode != 0:
            print("\n[ERROR] FFmpeg failed during audio conversion.")
            # We can't print stderr here as it was merged, but the non-zero code is the indicator
            return

        print("[Step 2/3] Injecting chapter markers...")
        chapter_command = [
            'ffmpeg', '-y', '-i', temp_audio_filename, '-i', metadata_filename,
            '-map_metadata', '1', '-codec', 'copy', final_output_path
        ]
        subprocess.run(chapter_command, check=True, capture_output=True, text=True)
        print("  - Chapter injection successful.")

        print("[Step 3/3] Applying final tags and cover art...")
        audio = MP4(final_output_path)
        audio.delete()
        audio.tags['©alb'] = source_metadata['album']
        audio.tags['©ART'] = source_metadata['author']
        audio.tags['aART'] = source_metadata['author']
        audio.tags['©nam'] = source_metadata['album']
        
        if source_metadata['cover_data']:
            audio.tags['covr'] = [MP4Cover(source_metadata['cover_data'], imageformat=MP4Cover.FORMAT_JPEG)]
        
        audio.save()
        print("  - Tagging complete.")

    except subprocess.CalledProcessError as e:
        print("\n[ERROR] A subprocess failed!")
        print(f"  Command: {' '.join(e.cmd)}")
        print(f"  Stderr: {e.stderr.strip()}")
        return
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")
        return
    finally:
        for f in [concat_list_filename, metadata_filename, temp_audio_filename]:
            if os.path.exists(f):
                os.remove(f)

    print(f"\n{'='*20} SUCCESS {'='*20}")
    print(f"Successfully created chapterized audiobook:")
    print(final_output_path)
    print(f"{'='*49}")

if __name__ == "__main__":
    check_dependencies()
    combine_chapters_to_m4b()