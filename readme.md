---

# Discord Audiobook Bot & Library Tools

A feature-rich Discord bot for browsing and listening to audiobooks in `.m4b` format, with interactive controls, series support, and cover art.  
Includes a set of Python tools for preparing and managing your audiobook library.

---

## Features

- Interactive slash commands for browsing and playing audiobooks
- Supports series and standalone books
- Chapter navigation, scrubbing, pause/resume, and quit controls
- Displays cover art and synopsis (if available)
- Live playback status and time tracking
- Designed for `.m4b` audiobook files (split into individual chapters)
- **Library Tools:** Split, combine, and inspect audiobooks for best compatibility

---

## Table of Contents

- [Setup Instructions](#setup-instructions)
- [Audiobook Library Tools](#audiobook-library-tools)
  - [split_m4b_mp3.py](#split_m4b_mp3py)
  - [mp3_to_m4b.py](#mp3_to_m4bpy)
  - [inspect_m4b.py](#inspect_m4bpy)
- [Audiobook Folder Structure](#audiobook-folder-structure)
- [Running the Bot](#running-the-bot)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [Credits](#credits)

---

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/discord-audiobook-bot.git
cd discord-audiobook-bot
```

---

### 2. Create a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt / cmd.exe):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**macOS/Linux (bash/zsh):**
```bash
python3 -m venv venv
source venv/bin/activate
```

---

### 3. Install Requirements

```bash
pip install -r requirements.txt
```

*This will install:*
- [Nextcord (voice support, dev version)](https://github.com/Renaud11232/nextcord)
- [mutagen](https://mutagen.readthedocs.io/en/latest/)
- [python-dotenv](https://pypi.org/project/python-dotenv/)
- [natsort](https://github.com/SethMMorton/natsort) (for library tools)

**Note:**  
You must also have [FFmpeg](https://ffmpeg.org/download.html) installed and available in your system’s PATH for audio playback and metadata extraction.

---

### 4. Set Up Your Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **"New Application"** and give your bot a name.
3. Go to **"Bot"** in the sidebar, then click **"Add Bot"**.
4. Under **Privileged Gateway Intents**, enable:
   - **SERVER MEMBERS INTENT** 
   - **MESSAGE CONTENT INTENT** 
   - **PRESENCE INTENT** 
5. Under **Token**, click **"Reset Token"** and copy your bot token.
6. Go to **"OAuth2" > "URL Generator"**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions:  
     - `Send Messages`
     - `Connect`
     - `Speak`
     - `Read Message History`
     - `Use Slash Commands`
     - *(Optional: `Attach Files` for cover art)*
   - Copy the generated URL and use it to invite your bot to your server.

---

### 5. Configure the `.env` File

1. Copy the example environment file:

   ```bash
   cp .envexample .env
   ```

2. Open `.env` and paste your Discord bot token:

   ```
   BOT_TOKEN=
   ```

   Example:
   ```
   BOT_TOKEN="your-bot-token-here"
   ```

---

## Audiobook Library Tools

These helper scripts make it easy to prepare your audiobook library for the bot.

---

### split_m4b_mp3.py

**Purpose:**  
Split a large `.m4b` or `.mp3` audiobook into individual chapter files, preserving metadata.

**When to use:**  
- You have a single audiobook file (with embedded chapters) and want to split it into separate chapter files for use with the bot.

**How to use:**

1. Run the script:
   ```bash
   python split_m4b_mp3.py
   ```
2. A file dialog will open.  
   **Select the root folder** containing your audiobooks (can be a folder with one or more `.m4b` or `.mp3` files).
3. The script will scan for valid audiobook files and display what it finds.
4. You’ll be prompted to select an **output folder** (or cancel to save chapters next to the source files).
5. The script will process each file, splitting it into chapters (using embedded chapter data), and save the results in:
   ```
   OutputFolder/Author/Album/001 - Chapter Name.m4b
   ```
6. Progress and errors will be shown in the terminal.

**Result:**  
Chapters are saved as individual `.m4b` files, organized by author and album, ready for the bot.

---

### mp3_to_m4b.py

**Purpose:**  
Combine a folder of `.mp3` chapter files into a single, chapterized `.m4b` audiobook, with cover art and metadata.

**When to use:**  
- You have a folder of MP3s (one per chapter) and want to create a single `.m4b` file with chapters and tags.

**How to use:**

1. Run the script:
   ```bash
   python mp3_to_m4b.py
   ```
2. A file dialog will open.  
   **Select the folder containing your MP3 chapters.**  
   (Files should be named in order, e.g., `01 - Chapter 1.mp3`, `02 - Chapter 2.mp3`, etc.)
3. Select an **output folder** for the resulting `.m4b` file.
4. The script will:
   - Combine all MP3s in order
   - Add chapter markers and metadata
   - Embed cover art (if present in the first MP3)
5. Progress will be shown in the terminal, including a progress bar for conversion.

**Result:**  
A single `.m4b` file with chapters and cover art, saved as:
```
OutputFolder/Author/Album/Album.m4b
```

---

### inspect_m4b.py

**Purpose:**  
Inspect and verify the metadata, chapters, and structure of your `.m4b` or `.mp3` files.

**When to use:**  
- You want to check that your files have the correct metadata, chapters, and cover art before using them with the bot.

**How to use:**

1. Run the script:
   ```bash
   python inspect_m4b.py
   ```
2. Follow the prompts to select files or folders to inspect.
3. The script will display metadata, chapter information, and cover art status in the terminal.

**Result:**  
You can verify that your audiobooks are properly tagged and structured for use with the bot.

---

## Audiobook Folder Structure

Your audiobooks should be organized in the following folder structure inside the `audiobooks/` directory (default, can be changed in `config.py`):

```
audiobooks/
  Author Name/
    Book Title/
      001 - Chapter 1.m4b
      002 - Chapter 2.m4b
    Series Name/
      Book 1 Title/
        001 - Chapter 1.m4b
        002 - Chapter 2.m4b
      Book 2 Title/
        001 - Chapter 1.m4b
        ...
```

- **Standalone books:** `audiobooks/Author Name/Book Title/*.m4b`
- **Series:** `audiobooks/Author Name/Series Name/Book Title/*.m4b`
- **Chapters:** Each `.m4b` file is treated as a chapter.  
- **Metadata:** For best results, ensure your `.m4b` files have proper metadata (title, track number, cover art, synopsis/description).

---

## Running the Bot

After you have set up your environment, installed requirements, configured your `.env` file, and prepared your audiobook library, you can start the Discord Audiobook Bot with:

```bash
python main.py
```

- The bot will log in, sync commands, and be ready to use in your Discord server.
- You should see status messages in your terminal indicating successful startup.

---

## Usage

- Use `/audiobook` to start the interactive player.
- Use `/stop` to disconnect the bot and stop playback.
- Use `/controls` to reopen the player controls panel if you closed it.

---

## Troubleshooting

- **FFmpeg not found:**  
  Make sure FFmpeg is installed and available in your system’s PATH.
- **No audiobooks found:**  
  Check your folder structure and file extensions (`.m4b`).
- **Bot not responding:**  
  Ensure your bot token is correct and the bot has the necessary permissions.
- **Library tool errors:**  
  Ensure you have all Python dependencies installed and that your files have the correct extensions and metadata.

---

## License

MIT License

---

## Credits

- Built with [Nextcord](https://github.com/Renaud11232/nextcord)
- Audio metadata via [mutagen](https://mutagen.readthedocs.io/en/latest/)
- Natural sorting via [natsort](https://github.com/SethMMorton/natsort)
- Audio processing via [FFmpeg](https://ffmpeg.org/)
- Created by revela

---