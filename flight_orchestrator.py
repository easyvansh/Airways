import json
import os
import sys
import glob
import subprocess
import datetime
import shutil
from typing import List, Optional
import logging
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich import print as rprint
import signal
import time

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException()

class FlightOrchestrator:
    def __init__(self):
        self.current_dir = os.getcwd()
        self.timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        
    def display_welcome(self):
        welcome_msg = """
        Flight Search Orchestration Tool
        ------------------------------
        This script will:
        1. Find all JSON config files in the current directory
        2. Process each config file through trip_configurator.py
        3. Run flight_automation.py on the generated configurations
        4. Create timestamped results folders
        5. Combine and save all results and logs
        """
        console.print(Panel(welcome_msg, title="Welcome", border_style="blue"))

    def find_json_files(self, requested_files: Optional[List[str]] = None) -> List[str]:
        try:
            json_files = requested_files or glob.glob("*.json")
            json_files = [file for file in json_files if file.endswith(".json")]
            json_files.sort()
            
            if not json_files:
                console.print("[yellow]No JSON files found in current directory.[/yellow]")
                return []
                
            console.print(f"[green]Found {len(json_files)} JSON file(s):[/green]")
            for file in json_files:
                console.print(f"  - {file}")
            return json_files
            
        except Exception as e:
            logger.error(f"Error while searching for JSON files: {e}")
            raise

    def validate_json_file(self, file_path: str) -> bool:
        try:
            with open(file_path, 'r') as f:
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON format in {file_path}: {str(e)}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Error reading {file_path}: {str(e)}[/red]")
            return False

    def create_results_directory(self, config_name: str) -> str:
        try:
            results_dir = f"results_{config_name}_{self.timestamp}"
            os.makedirs(results_dir, exist_ok=True)
            console.print(f"[green]Created results directory:[/green] {results_dir}")
            return results_dir
        except Exception as e:
            logger.error(f"Error creating results directory: {e}")
            raise

    def run_command(self, command: List[str], log_file: Path) -> bool:
        try:
            console.print(f"[cyan]Executing:[/cyan] {' '.join(command)}")
            
            with open(log_file, 'a') as log:
                log.write(f"\n{'='*50}\nCommand: {' '.join(command)}\n{'='*50}\n")
                
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        log.write(output)
                        console.print(output.strip())
                        
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"Error running command {' '.join(command)}: {e}")
            return False

    def combine_results(self, results_dir: str, config_file: str) -> None:
        try:
            output_file = os.path.join(results_dir, "all_flight_permutations.txt")
            
            with open(output_file, 'w') as out:
                out.write(f"Configuration File: {config_file}\n{'='*50}\n")
                with open(config_file, 'r') as f:
                    out.write(f"{f.read()}\n\n{'='*50}\n\n")
                
                if os.path.exists("trips.txt"):
                    out.write("Regular Trips Results:\n")
                    out.write(f"{'='*50}\n")
                    with open("trips.txt", 'r') as f:
                        out.write(f"{f.read()}\n\n")
                
                if os.path.exists("one-way-round-trips.txt"):
                    out.write("Split Round-Trip Results:\n")
                    out.write(f"{'='*50}\n")
                    with open("one-way-round-trips.txt", 'r') as f:
                        out.write(f"{f.read()}\n")

                if os.path.exists("yeg_del_one_way_results.txt"):
                    out.write("Grouped One-way Results:\n")
                    out.write(f"{'='*50}\n")
                    with open("yeg_del_one_way_results.txt", 'r', encoding='utf-8') as f:
                        out.write(f"{f.read()}\n")
                        
            console.print(f"[green]Combined results saved to:[/green] {output_file}")
            
        except Exception as e:
            logger.error(f"Error combining results: {e}")
            raise

    def process_config_file(self, config_file: str) -> None:
        try:
            console.print(f"\n[bold cyan]{'='*20} Processing {config_file} {'='*20}[/bold cyan]")
            
            if not self.validate_json_file(config_file):
                return
                
            results_dir = self.create_results_directory(Path(config_file).stem)
            log_file = Path(results_dir) / "log.txt"
            
            if not self.run_command([sys.executable, 'trip_configurator.py', config_file], log_file):
                raise Exception("Trip configurator failed")
                
            if not self.run_command([sys.executable, 'flight_automation.py'], log_file):
                raise Exception("Flight automation failed")
                
            self.combine_results(results_dir, config_file)
            
            console.print(f"[bold green]Successfully processed {config_file}[/bold green]")
            
        except Exception as e:
            logger.error(f"Error processing {config_file}: {e}")
            console.print(f"[bold red]Error processing {config_file}: {str(e)}[/bold red]")

    def prompt_cleanup(self) -> bool:
        if not os.path.exists('clean.py'):
            return False
            
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)
        
        try:
            response = input("\nWould you like to run clean.py? [y/N]: ").lower()
            signal.alarm(0)
            return response == 'y'
        except TimeoutException:
            console.print("\n[yellow]No response received within 10 seconds. Defaulting to No.[/yellow]")
            return False
        except KeyboardInterrupt:
            signal.alarm(0)
            console.print("\n[yellow]Input interrupted. Defaulting to No.[/yellow]")
            return False
        finally:
            signal.alarm(0)

    def run(self, requested_files: Optional[List[str]] = None):
        try:
            self.display_welcome()
            
            json_files = self.find_json_files(requested_files)
            if not json_files:
                return
                
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                task = progress.add_task("[cyan]Processing config files...", total=len(json_files))
                
                for config_file in json_files:
                    self.process_config_file(config_file)
                    progress.advance(task)
                    
            console.print("\n[bold green]All processing completed successfully![/bold green]")
            
            if self.prompt_cleanup():
                self.run_command([sys.executable, 'clean.py'], Path('cleanup_log.txt'))
            
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            console.print(f"[bold red]Fatal error: {str(e)}[/bold red]")
            sys.exit(1)

def main():
    try:
        orchestrator = FlightOrchestrator()
        orchestrator.run(sys.argv[1:] or None)
    except KeyboardInterrupt:
        console.print("\n[yellow]Process interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error: {str(e)}[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
