#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║                    FILE ORGANIZER v4                          ║
║        By @flakesofsmth and @jussoftware on instagram         ║
╚═══════════════════════════════════════════════════════════════╝

Usage:
    python organiser_v4.py                      # Interactive mode
    python organiser_v4.py --path "C:/MyFolder" # Organize specific folder
    python organiser_v4.py --dry-run            # Preview without moving
    python organiser_v4.py --undo               # Reverse last run
    python organiser_v4.py --watch              # Auto-organize on new files
    python organiser_v4.py --no-ai              # Skip AI, use rules only
    python organiser_v4.py --granularity high   # Deep nested AI sorting
"""

import os
import sys
import shutil
import datetime
import json
import time
import hashlib
import argparse
import urllib.request
import urllib.error
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.columns import Columns
    from rich import box
    from rich.live import Live
    from rich.align import Align
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ─── Console ────────────────────────────────────────────────────
console = Console() if RICH_AVAILABLE else None

def cprint(msg, style=None):
    """Cross-compatible print that uses rich if available."""
    if console and style:
        console.print(msg, style=style)
    elif console:
        console.print(msg)
    else:
        print(msg)

# ─── Constants ──────────────────────────────────────────────────
APP_NAME = "Organizer"
VERSION = "4.0.0"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
MANIFEST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'manifest.json')
DEFAULT_MODEL = "arcee-ai/trinity-large-preview:free"
WATCH_INTERVAL = 5  # seconds

EXTENSIONS = {
    'Media': {
        'Images': ['.jpg', '.jpeg', '.png', '.heic', '.gif', '.bmp', '.tiff', '.webp', '.svg', '.ico', '.raw', '.cr2'],
        'Video': ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp'],
        'Audio': ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a', '.wma', '.opus']
    },
    'Documents': {
        'PDF': ['.pdf'],
        'Spreadsheets': ['.xlsx', '.xls', '.csv', '.ods', '.tsv'],
        'Presentations': ['.pptx', '.ppt', '.key', '.odp'],
        'Text': ['.docx', '.doc', '.txt', '.rtf', '.odt', '.md', '.tex', '.log'],
        'eBooks': ['.epub', '.mobi', '.azw3']
    },
    'Installers': {
        'Executables': ['.exe', '.msi', '.bat', '.cmd', '.appx', '.msix'],
        'Disk_Images': ['.dmg', '.iso', '.bin', '.img', '.vhd', '.vmdk']
    },
    'Archives': {
        'Compressed': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.pkg', '.deb', '.rpm']
    },
    'Code': {
        'Scripts': ['.py', '.js', '.ts', '.sh', '.pl', '.php', '.rb', '.lua', '.ps1'],
        'Source': ['.html', '.css', '.scss', '.c', '.cpp', '.h', '.java', '.kt', '.swift',
                   '.go', '.rs', '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg'],
        'Notebooks': ['.ipynb']
    },
    'Design': {
        'Graphics': ['.psd', '.ai', '.sketch', '.fig', '.xd', '.indd'],
        'Models_3D': ['.blend', '.obj', '.fbx', '.stl', '.step']
    },
    'Fonts': {
        'Font_Files': ['.ttf', '.otf', '.woff', '.woff2', '.eot']
    },
    'Data': {
        'Databases': ['.db', '.sqlite', '.sql', '.mdb', '.accdb'],
        'Datasets': ['.parquet', '.avro', '.hdf5', '.npy', '.npz']
    }
}

DESTINATIONS_FLAT = [f"{cat}/{sub}" for cat, subs in EXTENSIONS.items() for sub in subs]

SYSTEM_FOLDERS_BASE = {'folders', 'misc'}
for _cat in EXTENSIONS:
    SYSTEM_FOLDERS_BASE.add(_cat.lower())

def is_system_folder(name):
    """Check if a folder name is a system/managed folder."""
    lower = name.lower()
    if lower in SYSTEM_FOLDERS_BASE:
        return True
    return False

# ─── Banner ─────────────────────────────────────────────────────
BANNER = """[bold cyan]
╔═══════════════════════════════════════════════════════════════╗
║                    FILE ORGANIZER v4                          ║
║        By @flakesofsmth and @jussoftware on instagram         ║
╚═══════════════════════════════════════════════════════════════╝
[/bold cyan]"""

BANNER_PLAIN = """
╔═══════════════════════════════════════════════════════════════╗
║                    FILE ORGANIZER v4                          ║
║        By @flakesofsmth and @jussoftware on instagram         ║
╚═══════════════════════════════════════════════════════════════╝
"""

# ═══════════════════════════════════════════════════════════════
#  CONFIG MANAGEMENT
# ═══════════════════════════════════════════════════════════════

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return None

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def setup_config(skip_ai=False):
    if skip_ai:
        return None
    config = load_config()
    if config and config.get('api_key'):
        cprint(f"✅ AI config loaded (model: [bold]{config.get('model', DEFAULT_MODEL)}[/bold])", "green")
        return config

    if console:
        console.print(Panel("[bold yellow]AI Configuration[/bold yellow]\nTo use AI features, enter your OpenRouter API Key.\nGet one at: [link=https://openrouter.ai/keys]https://openrouter.ai/keys[/link]", border_style="yellow"))
        api_key = Prompt.ask("🔑 API Key (leave empty to skip AI)", default="")
    else:
        print("--- AI Configuration ---")
        api_key = input("API Key (leave empty to skip AI): ").strip()

    if not api_key:
        cprint("⏭️  Skipping AI — using rule-based sorting only.", "dim")
        return None

    if console:
        model = Prompt.ask("🤖 Model", default=DEFAULT_MODEL)
    else:
        model = input(f"Model (default: {DEFAULT_MODEL}): ").strip() or DEFAULT_MODEL

    new_config = {"api_key": api_key, "model": model}
    save_config(new_config)
    cprint(f"✅ Config saved to [bold]{CONFIG_FILE}[/bold]", "green")
    return new_config

# ═══════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_file_hash(filepath, chunk_size=8192):
    """Calculate MD5 hash for duplicate detection."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return None

def get_creation_date(filepath):
    try:
        stat = os.stat(filepath)
        timestamp = stat.st_mtime
        return datetime.datetime.fromtimestamp(timestamp)
    except (OSError, ValueError):
        return datetime.datetime.now()


def format_size(size_bytes):
    """Human-readable file size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

def generate_unique_name(dest_folder, filename):
    name, ext = os.path.splitext(filename)
    dest = os.path.join(dest_folder, filename)
    if not os.path.exists(dest):
        return filename
    # Check if it's a true duplicate by hash
    counter = 1
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"{name}_{timestamp}{ext}"
    final = os.path.join(dest_folder, new_name)
    while os.path.exists(final):
        counter += 1
        new_name = f"{name}_{timestamp}_{counter}{ext}"
        final = os.path.join(dest_folder, new_name)
    return new_name

def auto_rename(filename):
    """Apply naming convention: YYYY-MM-DD_OriginalName."""
    name, ext = os.path.splitext(filename)
    date_prefix = datetime.datetime.now().strftime("%Y-%m-%d")
    # Don't double-prefix if already has a date pattern
    if len(name) >= 10 and name[:4].isdigit() and name[4] == '-' and name[7] == '-':
        return filename
    return f"{date_prefix}_{name}{ext}"

def get_extension_category(ext):
    """Fallback: determine category from file extension."""
    ext = ext.lower()
    for cat, subs in EXTENSIONS.items():
        for sub, valid_exts in subs.items():
            if ext in valid_exts:
                return cat, sub
    return None, None

# ═══════════════════════════════════════════════════════════════
#  AI CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def get_ai_classification(file_infos, config, granularity="normal"):
    """
    Sends batch of file info to OpenRouter for smart classification.
    file_infos: list of dicts with {name, size, date}
    """
    if not config or not file_infos:
        return {}

    if granularity == "high":
        gran_text = """**HIGH GRANULARITY MODE**: Create DEEPLY nested, extremely specific folders.
    Example: "Roblox/CityProject/Models", "School/Physics/Lab_Reports", "Work/Clients/Acme/Contracts"."""
    else:
        gran_text = """Create descriptive, project-aware folder names.
    Example: "Roblox/CityProject", "SchoolWork/Math", "Photography/Wedding"."""

    # Build rich file info for AI
    files_desc = []
    for fi in file_infos:
        files_desc.append(f"  - {fi['name']} ({fi['size']}, modified {fi['date']})")
    files_text = "\n".join(files_desc)

    prompt = f"""You are an expert file organization AI that specializes in PROJECT DETECTION.

Your #1 priority is to detect PROJECTS and THEMES from filenames:
- Look for common prefixes, keywords, and naming patterns.
- Files like "BloxCityBuildings.obj", "BloxCityRoad.obj", "CityTexture.png" all belong to the SAME project folder.
- Files like "resume_v2.docx", "cover_letter.pdf" belong together in "JobSearch" or "Career".
- Files like "homework_ch5.pdf", "notes_physics.txt" belong in "School/Physics".

Rules:
1. **Projects First**: Group by detected project/theme, NOT by file type.
   - WRONG: putting "BloxCityBuildings.obj" in "Design/Models_3D"
   - RIGHT: putting it in "Roblox/CityProject" or "GameDev/BloxCity"
2. **Smart Naming**: Name folders after the project, game, or activity.
3. {gran_text}
4. Only use generic categories ({', '.join(DESTINATIONS_FLAT)}) as a LAST RESORT for truly random files.
5. Use "Misc" only if a file is completely unrelated to anything else.

Files to classify:
{files_text}

Return ONLY a valid JSON object mapping each filename to its destination folder.
Example: {{"BloxCityBuildings.obj": "Roblox/CityProject", "resume_v2.docx": "Career/Applications"}}"""

    data = {
        "model": config['model'],
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/shubh72010/organizer",
    }

    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(data).encode('utf-8'),
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)
            content = result['choices'][0]['message']['content']
            # Try to extract JSON even if wrapped in markdown
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content.strip())
    except Exception as e:
        cprint(f"⚠️  AI Error: {e}", "bold red")
        return {}

# ═══════════════════════════════════════════════════════════════
#  MANIFEST / UNDO SYSTEM
# ═══════════════════════════════════════════════════════════════

def save_manifest(moves):
    """Save a record of all moves for undo."""
    manifest = {
        "timestamp": datetime.datetime.now().isoformat(),
        "version": VERSION,
        "moves": moves
    }
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest, f, indent=2)
    cprint(f"📋 Manifest saved ({len(moves)} moves) → [bold]{MANIFEST_FILE}[/bold]", "dim")

def undo_last_run():
    """Reverse all moves from the last manifest."""
    if not os.path.exists(MANIFEST_FILE):
        cprint("❌ No manifest found. Nothing to undo.", "bold red")
        return

    with open(MANIFEST_FILE, 'r') as f:
        manifest = json.load(f)

    moves = manifest.get("moves", [])
    ts = manifest.get("timestamp", "unknown")

    if not moves:
        cprint("❌ Manifest is empty.", "bold red")
        return

    cprint(f"\n🔄 Undoing {len(moves)} moves from run at {ts}...\n", "bold yellow")

    success = 0
    errors = 0

    if console:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Undoing...", total=len(moves))
            for move in reversed(moves):
                src = move.get("to")
                dst_dir = os.path.dirname(move.get("from"))
                dst = move.get("from")
                try:
                    if os.path.exists(src):
                        os.makedirs(dst_dir, exist_ok=True)
                        shutil.move(src, dst)
                        success += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1
                progress.advance(task)
    else:
        for move in reversed(moves):
            src = move.get("to")
            dst_dir = os.path.dirname(move.get("from"))
            dst = move.get("from")
            try:
                if os.path.exists(src):
                    os.makedirs(dst_dir, exist_ok=True)
                    shutil.move(src, dst)
                    success += 1
                else:
                    errors += 1
            except Exception:
                errors += 1

    cprint(f"\n✅ Undo complete: {success} restored, {errors} errors.", "bold green" if errors == 0 else "yellow")

    # Remove the manifest after undo
    try:
        os.remove(MANIFEST_FILE)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
#  SCANNING & CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def scan_directory(source_dir):
    """Collect all items with metadata."""
    files = []
    folders = []
    script_name = os.path.basename(__file__)

    for item_name in os.listdir(source_dir):
        item_path = os.path.join(source_dir, item_name)
        if item_name == script_name:
            continue

        if os.path.isdir(item_path):
            if not is_system_folder(item_name):
                folders.append({
                    "name": item_name,
                    "path": item_path,
                    "date": get_creation_date(item_path)
                })
        else:
            try:
                size = os.path.getsize(item_path)
            except OSError:
                size = 0

            _, ext = os.path.splitext(item_name)
            files.append({
                "name": item_name,
                "path": item_path,
                "ext": ext.lower(),
                "size": size,
                "size_human": format_size(size),
                "date": get_creation_date(item_path),
                "date_str": get_creation_date(item_path).strftime("%Y-%m-%d"),
                "hash": None  # Computed lazily
            })

    return files, folders

def classify_files(files, config, granularity, source_dir):
    """Determine destination for each file using AI + fallback."""
    ai_mapping = {}

    # AI Classification
    if config and files:
        cprint(f"\n🤖 Asking AI to classify {len(files)} files (granularity: {granularity})...", "bold cyan")
        file_infos = [{"name": f["name"], "size": f["size_human"], "date": f["date_str"]} for f in files]

        # Batch in chunks of 25
        for i in range(0, len(file_infos), 25):
            chunk = file_infos[i:i + 25]
            result = get_ai_classification(chunk, config, granularity)
            ai_mapping.update(result)
            if i + 25 < len(file_infos):
                time.sleep(0.5)

        cprint(f"✅ AI classified {len(ai_mapping)} files.", "green")

    # Determine destinations
    results = []
    for f in files:
        month_year = f["date"].strftime("%Y-%m")

        ai_cat = ai_mapping.get(f["name"])
        if ai_cat and ai_cat != "Misc":
            dest_folder = os.path.join(source_dir, ai_cat, month_year)
            method = "🤖 AI"
        else:
            cat, sub = get_extension_category(f["ext"])
            if cat:
                dest_folder = os.path.join(source_dir, cat, sub, month_year)
                method = "📁 Rules"
            else:
                dest_folder = None
                method = "⏭️ Skip"

        results.append({**f, "dest_folder": dest_folder, "method": method})

    return results

# ═══════════════════════════════════════════════════════════════
#  DUPLICATE DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_duplicates(files):
    """Find true duplicates using MD5 hash."""
    hash_map = {}
    duplicates = []

    if console:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), console=console, transient=True) as progress:
            task = progress.add_task("🔍 Hashing files for duplicate detection...", total=len(files))
            for f in files:
                file_hash = get_file_hash(f["path"])
                f["hash"] = file_hash
                if file_hash:
                    if file_hash in hash_map:
                        duplicates.append((f, hash_map[file_hash]))
                    else:
                        hash_map[file_hash] = f
                progress.advance(task)
    else:
        for f in files:
            file_hash = get_file_hash(f["path"])
            f["hash"] = file_hash
            if file_hash:
                if file_hash in hash_map:
                    duplicates.append((f, hash_map[file_hash]))
                else:
                    hash_map[file_hash] = f

    return duplicates

# ═══════════════════════════════════════════════════════════════
#  EXECUTE MOVES
# ═══════════════════════════════════════════════════════════════

def execute_moves(classified_files, folders, source_dir, dry_run=False, rename=True):
    """Move files and folders (or preview in dry-run mode)."""
    manifest_moves = []
    stats = {"moved": 0, "skipped": 0, "errors": 0, "by_category": {}, "total_size": 0}

    # ── Display preview table ──
    if console:
        table = Table(title="📦 Organization Plan", box=box.ROUNDED, border_style="cyan", show_lines=False)
        table.add_column("#", style="dim", width=4)
        table.add_column("File", style="bold white", max_width=35, overflow="ellipsis")
        table.add_column("Size", style="dim", justify="right", width=9)
        table.add_column("Method", width=10)
        table.add_column("Destination", style="green", max_width=50, overflow="ellipsis")

        for i, f in enumerate(classified_files, 1):
            if f["dest_folder"]:
                dest_display = os.path.relpath(f["dest_folder"], source_dir)
                table.add_row(str(i), f["name"], f["size_human"], f["method"], dest_display)
            else:
                table.add_row(str(i), f["name"], f["size_human"], f["method"], "[dim]— staying —[/dim]")

        if folders:
            table.add_row("", "─── Folders ───", "", "", "", style="dim")
            for fl in folders:
                dest = f"Folders/{fl['date'].strftime('%Y-%m')}"
                table.add_row("📂", fl["name"], "", "🗂️ Folder", dest)

        console.print(table)
        console.print()

    if dry_run:
        cprint("🏁 [bold yellow]DRY RUN[/bold yellow] — No files were moved. Review the plan above.", "yellow")
        return stats

    # ── Move files ──
    items_to_move = [(f, True) for f in classified_files if f["dest_folder"]]
    folder_items = [(fl, False) for fl in folders]
    all_items = items_to_move + folder_items

    if not all_items:
        cprint("✨ Nothing to organize — folder is already clean!", "bold green")
        return stats

    if console:
        with Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="green", finished_style="bold green"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            task = progress.add_task("🚀 Organizing files...", total=len(all_items))

            for item, is_file in all_items:
                try:
                    if is_file:
                        dest_folder = item["dest_folder"]
                        original_path = item["path"]
                        filename = item["name"]

                        # Auto-rename
                        if rename:
                            filename = auto_rename(filename)

                        os.makedirs(dest_folder, exist_ok=True)
                        final_name = generate_unique_name(dest_folder, filename)
                        final_path = os.path.join(dest_folder, final_name)

                        shutil.move(original_path, final_path)
                        manifest_moves.append({"from": original_path, "to": final_path})

                        # Stats
                        stats["moved"] += 1
                        stats["total_size"] += item.get("size", 0)
                        cat = item["method"]
                        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
                    else:
                        # Folder
                        fl = item
                        dest = os.path.join(source_dir, 'Folders', fl["date"].strftime("%Y-%m"))

                        abs_dest = os.path.abspath(dest)
                        abs_src = os.path.abspath(fl["path"])
                        if abs_dest.startswith(abs_src) or abs_dest == abs_src:
                            stats["skipped"] += 1
                            progress.advance(task)
                            continue

                        os.makedirs(dest, exist_ok=True)
                        final_name = generate_unique_name(dest, fl["name"])
                        final_path = os.path.join(dest, final_name)
                        shutil.move(fl["path"], final_path)
                        manifest_moves.append({"from": fl["path"], "to": final_path})
                        stats["moved"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    cprint(f"  ❌ Error: {item.get('name', '?')}: {e}", "red")

                progress.advance(task)
    else:
        for item, is_file in all_items:
            try:
                if is_file:
                    dest_folder = item["dest_folder"]
                    original_path = item["path"]
                    filename = auto_rename(item["name"]) if rename else item["name"]
                    os.makedirs(dest_folder, exist_ok=True)
                    final_name = generate_unique_name(dest_folder, filename)
                    final_path = os.path.join(dest_folder, final_name)
                    shutil.move(original_path, final_path)
                    manifest_moves.append({"from": original_path, "to": final_path})
                    stats["moved"] += 1
                    stats["total_size"] += item.get("size", 0)
                    print(f"  Moved: {item['name']} -> {dest_folder}")
                else:
                    fl = item
                    dest = os.path.join(source_dir, 'Folders', fl["date"].strftime("%Y-%m"))
                    abs_dest = os.path.abspath(dest)
                    abs_src = os.path.abspath(fl["path"])
                    if abs_dest.startswith(abs_src) or abs_dest == abs_src:
                        continue
                    os.makedirs(dest, exist_ok=True)
                    final_name = generate_unique_name(dest, fl["name"])
                    shutil.move(fl["path"], os.path.join(dest, final_name))
                    manifest_moves.append({"from": fl["path"], "to": os.path.join(dest, final_name)})
                    stats["moved"] += 1
            except Exception as e:
                stats["errors"] += 1

    # Save manifest
    if manifest_moves:
        save_manifest(manifest_moves)

    return stats

# ═══════════════════════════════════════════════════════════════
#  STATISTICS DASHBOARD
# ═══════════════════════════════════════════════════════════════

def show_stats(stats, duplicates, total_files, total_folders):
    """Display a beautiful statistics dashboard."""
    if not console:
        print(f"\n=== RESULTS ===")
        print(f"Moved: {stats['moved']} | Skipped: {stats['skipped']} | Errors: {stats['errors']}")
        print(f"Duplicates found: {len(duplicates)} | Total size moved: {format_size(stats['total_size'])}")
        return

    console.print()

    # Summary panel
    summary_items = [
        f"[bold green]✅ Moved:[/bold green] {stats['moved']}",
        f"[bold yellow]⏭️ Skipped:[/bold yellow] {stats['skipped']}",
        f"[bold red]❌ Errors:[/bold red] {stats['errors']}",

        f"[bold magenta]🔍 Duplicates:[/bold magenta] {len(duplicates)}",
        f"[bold cyan]📦 Total Size:[/bold cyan] {format_size(stats['total_size'])}",
    ]

    console.print(Panel(
        Align.center(Text.from_markup("\n".join(summary_items))),
        title="[bold]📊 Results Dashboard[/bold]",
        border_style="cyan",
        padding=(1, 4)
    ))

    # Category breakdown
    if stats["by_category"]:
        cat_table = Table(title="📁 By Classification Method", box=box.SIMPLE_HEAVY, border_style="dim")
        cat_table.add_column("Method", style="bold")
        cat_table.add_column("Count", justify="right", style="cyan")
        for method, count in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
            cat_table.add_row(method, str(count))
        console.print(cat_table)

    # Duplicates
    if duplicates:
        dup_table = Table(title="🔍 Duplicate Files Detected", box=box.SIMPLE, border_style="yellow")
        dup_table.add_column("File A", style="white", max_width=40)
        dup_table.add_column("File B", style="white", max_width=40)
        dup_table.add_column("Size", justify="right", style="dim")
        for dup, original in duplicates[:10]:  # Show max 10
            dup_table.add_row(dup["name"], original["name"], dup["size_human"])
        if len(duplicates) > 10:
            dup_table.add_row(f"... and {len(duplicates) - 10} more", "", "", style="dim")
        console.print(dup_table)

    console.print()

# ═══════════════════════════════════════════════════════════════
#  WATCH MODE
# ═══════════════════════════════════════════════════════════════

def watch_folder(source_dir, config, granularity):
    """Continuously watch and auto-organize new files."""
    cprint(f"\n👀 [bold]Watch Mode[/bold] — Monitoring: {source_dir}", "bold cyan")
    cprint(f"   Checking every {WATCH_INTERVAL}s. Press Ctrl+C to stop.\n", "dim")

    known_items = set(os.listdir(source_dir))

    try:
        while True:
            time.sleep(WATCH_INTERVAL)
            current_items = set(os.listdir(source_dir))
            new_items = current_items - known_items

            if new_items:
                cprint(f"\n📥 {len(new_items)} new item(s) detected!", "bold green")
                # Run organizer on the folder
                files, folders = scan_directory(source_dir)
                # Only process new items
                new_files = [f for f in files if f["name"] in new_items]
                new_folders = [f for f in folders if f["name"] in new_items]

                if new_files or new_folders:
                    classified = classify_files(new_files, config, granularity, source_dir)
                    execute_moves(classified, new_folders, source_dir, dry_run=False, rename=True)

                known_items = set(os.listdir(source_dir))
            else:
                if console:
                    console.print(f"   ⏳ {datetime.datetime.now().strftime('%H:%M:%S')} — no new files", style="dim", end="\r")
    except KeyboardInterrupt:
        cprint("\n\n🛑 Watch mode stopped.", "bold yellow")

# ═══════════════════════════════════════════════════════════════
#  MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def organize(source_dir, config, granularity="normal", dry_run=False, rename=True):
    """Main orchestration function."""
    cprint(f"\n📂 Target: [bold]{source_dir}[/bold]", "white")
    cprint(f"   Mode: {'🏜️ Dry Run' if dry_run else '🚀 Live'} | Granularity: {granularity} | Rename: {'✅' if rename else '❌'}\n", "dim")

    # 1. Scan
    files, folders = scan_directory(source_dir)
    cprint(f"   Found [bold]{len(files)}[/bold] files and [bold]{len(folders)}[/bold] folders.", "white")

    if not files and not folders:
        cprint("✨ Nothing to organize!", "bold green")
        return

    # 2. Detect duplicates
    duplicates = detect_duplicates(files)
    if duplicates:
        cprint(f"   ⚠️  Found [bold]{len(duplicates)}[/bold] duplicate file(s).", "yellow")

    # 3. Classify
    classified = classify_files(files, config, granularity, source_dir)

    # 4. Execute
    stats = execute_moves(classified, folders, source_dir, dry_run=dry_run, rename=rename)

    # 5. Dashboard
    show_stats(stats, duplicates, len(files), len(folders))

    cprint("🏁 [bold green]Done![/bold green]\n", "green")

# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="⚡ Ultra Pro Max File Organizer — AI-Powered, Smart Duplicates, Undo, Watch Mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python organiser_v4.py                          # Interactive
  python organiser_v4.py --path ~/Downloads        # Specific folder
  python organiser_v4.py --dry-run                 # Preview only
  python organiser_v4.py --undo                    # Reverse last run
  python organiser_v4.py --watch                   # Auto-organize
  python organiser_v4.py --no-ai --granularity low # Rules only
        """
    )
    parser.add_argument("--path",        type=str, default=None, help="Folder path to organize")
    parser.add_argument("--dry-run",     action="store_true", help="Preview moves without executing")
    parser.add_argument("--undo",        action="store_true", help="Reverse the last organization run")
    parser.add_argument("--watch",       action="store_true", help="Watch folder and auto-organize new files")
    parser.add_argument("--no-ai",       action="store_true", help="Skip AI classification, use rules only")
    parser.add_argument("--no-rename",   action="store_true", help="Skip auto-renaming files with date prefix")
    parser.add_argument("--granularity", type=str, default="normal", choices=["normal", "high"], help="AI sorting depth")

    args = parser.parse_args()

    # Banner
    if console:
        console.print(BANNER)
    else:
        print(BANNER_PLAIN)

    # ── Undo mode ──
    if args.undo:
        undo_last_run()
        return

    # ── Determine path ──
    default_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
    if args.path:
        target_dir = os.path.expanduser(args.path)
    else:
        if console:
            target_dir = Prompt.ask("📂 Folder to organize", default=default_dir)
        else:
            print(f"Enter folder path (default: {default_dir}):")
            target_dir = input("Path: ").strip() or default_dir
            target_dir = os.path.expanduser(target_dir)

    if not os.path.isdir(target_dir):
        cprint(f"❌ Path not found: {target_dir}", "bold red")
        return

    # ── Setup AI ──
    config = setup_config(skip_ai=args.no_ai)

    # ── Granularity prompt (interactive only) ──
    granularity = args.granularity
    if config and granularity == "normal" and not any([args.dry_run, args.watch]):
        if console:
            if Confirm.ask("🔬 Enable High Granularity? (deeper, more specific folders)", default=False):
                granularity = "high"
        else:
            hg = input("Enable High Granularity? (y/N): ").strip().lower()
            if hg == 'y':
                granularity = "high"

    # ── Watch mode ──
    if args.watch:
        watch_folder(target_dir, config, granularity)
        return

    # ── Main organize ──
    organize(target_dir, config, granularity=granularity, dry_run=args.dry_run, rename=not args.no_rename)


if __name__ == "__main__":
    main()
