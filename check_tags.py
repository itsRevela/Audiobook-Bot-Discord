# check_tags.py (Diagnostic Version)
import sys
import os
from mutagen.mp4 import MP4
import xml.etree.ElementTree as ET
from pprint import pprint

def inspect_chapters(filepath):
    """
    Opens an M4B file, finds the Audible chapter XML,
    prints it, and attempts to parse it for debugging.
    """
    if not os.path.exists(filepath):
        print(f"--- ERROR: File not found at '{filepath}' ---")
        return

    try:
        print(f"--- Inspecting Chapters for: {os.path.basename(filepath)} ---\n")
        audio = MP4(filepath)

        # Check for the specific Audible tag
        if "----:com.audible:chapters" in audio.tags:
            print("✅ Found '----:com.audible:chapters' tag. Extracting XML data...\n")
            
            # Get the raw XML data (it's a bytes string) and decode it
            xml_data_str = audio.tags["----:com.audible:chapters"][0].decode('utf-8')

            print("====================== RAW XML DATA - START ======================")
            print(xml_data_str)
            print("======================= RAW XML DATA - END =======================\n")

            print("--- Attempting to parse XML and extract chapters ---\n")
            try:
                # Parse the XML string
                root = ET.fromstring(xml_data_str)
                
                # The namespace is part of the tag name, like {http://...}Chapters
                # We need to handle it correctly.
                namespace = ''
                if '}' in root.tag:
                    namespace = root.tag.split('}')[0].strip('{')
                    print(f"Detected XML Namespace: {namespace}\n")

                # Use .// to find the tag anywhere in the tree
                search_path = f'.//{{{namespace}}}ChapterPoint'
                print(f"Searching for tags with path: '{search_path}'")
                
                chapter_points = root.findall(search_path)

                if not chapter_points:
                    print("\n❌ ERROR: Could not find any <ChapterPoint> tags using the detected namespace.")
                    print("Please examine the raw XML above to see what the correct chapter tag name is (e.g., maybe it's 'chapter' instead of 'ChapterPoint').")
                    return

                print(f"\n✅ Success! Found {len(chapter_points)} chapter entries. Listing them:\n")
                
                for i, chap_point in enumerate(chapter_points):
                    # Find the title and start time within each chapter point
                    title_element = chap_point.find(f'{{{namespace}}}Title')
                    start_element = chap_point.find(f'{{{namespace}}}StartTime')
                    
                    title = title_element.text if title_element is not None else "TITLE NOT FOUND"
                    start_time = start_element.text if start_element is not None else "START TIME NOT FOUND"
                    
                    print(f"  Chapter {i+1:02d}: '{title}' (Starts at: {start_time})")

            except ET.ParseError as e:
                print(f"\n❌ ERROR: Failed to parse the XML data. This may indicate the file is corrupt. Error: {e}")
            except Exception as e:
                print(f"\n❌ An unexpected error occurred during parsing: {e}")

        else:
            print("❌ Did not find the '----:com.audible:chapters' tag in this file.")
            print("\n--- Available Tags ---")
            pprint(audio.tags)
            print("----------------------")

    except Exception as e:
        print(f"An error occurred while opening or reading the file: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_to_check = sys.argv[1]
        inspect_chapters(file_to_check)
    else:
        print("Usage: python check_tags.py \"path/to/your/audiobook.m4b\"")
        print("Please provide the path to the file you want to inspect.")
        print("Remember to put the path in quotes if it contains spaces!")