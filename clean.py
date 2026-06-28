import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Set
import platform
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich import print as rprint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize Rich console
console = Console()

class CleanupError(Exception):
    """Custom exception for cleanup operations"""
    pass

class Cleaner:
    def __init__(self):
        self.system = platform.system()
        self.stats = {
            'files_processed': 0,
            'files_moved': 0,
            'folders_moved': 0,
            'errors': 0,
            'protected': 0
        }
        # Files to protect in current directory
        self.protected_patterns = {
            '*.config',
            '*.cfg',
            '*.conf',
            '*.ini',
            '*.json',
            '*.yaml',
            '*.yml',
            '*.py'
        }

    def get_trash_path(self) -> Path:
        """Get the system-specific trash directory path."""
        if self.system == "Darwin":  # macOS
            return Path.home() / ".Trash"
        elif self.system == "Windows":
            return Path(os.path.expandvars(r"%SystemDrive%\$Recycle.Bin"))
        else:  # Linux
            return Path.home() / ".local/share/Trash/files"

    def is_protected(self, file_path: Path) -> bool:
        """Check if a file should be protected from deletion."""
        if file_path.parent == Path.cwd():  # Only protect files in current directory
            return any(file_path.match(pattern) for pattern in self.protected_patterns)
        return file_path.suffix == '.py'  # Always protect .py files regardless of location

    def should_process_file(self, file_path: Path) -> bool:
        """Determine if a file should be processed based on its extension."""
        if self.is_protected(file_path):
            return False
        return file_path.suffix.lower() in {'.txt', '.log', '.csv', '.md'}

    def move_to_trash(self, path: Path) -> bool:
        """Move a file or directory to the trash."""
        try:
            if self.is_protected(path):
                self.stats['protected'] += 1
                console.print(f"[yellow]Protected file/folder:[/yellow] {path}")
                return False

            if self.system == "Darwin":
                import subprocess
                subprocess.run(['osascript', '-e', f'tell app "Finder" to move POSIX file "{path}" to trash'], 
                             check=True, capture_output=True)
            elif self.system == "Windows":
                import winshell
                winshell.delete_file(str(path), no_confirm=True, allow_undo=True)
            else:  # Linux
                trash_path = self.get_trash_path()
                trash_path.mkdir(parents=True, exist_ok=True)
                unique_name = f"{path.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.move(str(path), str(trash_path / unique_name))
            return True
        except Exception as e:
            logger.error(f"Error moving {path} to trash: {str(e)}")
            self.stats['errors'] += 1
            return False

    def process_directory(self, directory: Path):
        """Process a directory for cleanup."""
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=console
            ) as progress:
                # Collect all items first to show accurate progress
                items = list(directory.rglob("*"))
                task = progress.add_task("Processing files...", total=len(items))

                for item in items:
                    self.stats['files_processed'] += 1
                    progress.advance(task)

                    if item.is_file():
                        if self.should_process_file(item):
                            if self.move_to_trash(item):
                                self.stats['files_moved'] += 1
                                console.print(f"[green]Moved file to trash:[/green] {item}")
                    elif item.is_dir() and not any(self.is_protected(p) for p in item.glob("*")):
                        if self.move_to_trash(item):
                            self.stats['folders_moved'] += 1
                            console.print(f"[blue]Moved folder to trash:[/blue] {item}")

        except Exception as e:
            logger.error(f"Error processing directory: {str(e)}")
            raise CleanupError(f"Failed to process directory: {str(e)}")

    def print_summary(self):
        """Print a summary of the cleanup operation."""
        summary = Panel(f"""
[bold]Cleanup Summary[/bold]
Files Processed: {self.stats['files_processed']}
Files Moved to Trash: {self.stats['files_moved']}
Folders Moved to Trash: {self.stats['folders_moved']}
Protected Files/Folders: {self.stats['protected']}
Errors Encountered: {self.stats['errors']}
        """.strip(), title="Results", border_style="green")
        console.print(summary)

def main():
    console.print("[bold cyan]Starting cleanup operation...[/bold cyan]")
    
    try:
        cleaner = Cleaner()
        current_dir = Path.cwd()
        
        # Start cleanup
        cleaner.process_directory(current_dir)
        cleaner.print_summary()
        
    except CleanupError as e:
        console.print(f"[red bold]Cleanup Error:[/red bold] {str(e)}")
        logger.error(str(e))
        return 1
    except Exception as e:
        console.print(f"[red bold]Unexpected Error:[/red bold] {str(e)}")
        logger.error(f"Unexpected error: {str(e)}")
        return 1
    
    console.print("[bold green]Cleanup completed successfully![/bold green]")
    return 0

if __name__ == "__main__":
    exit(main())