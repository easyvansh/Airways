from datetime import datetime, timedelta
import json
import os
import shutil
from typing import List, Dict, Union, Optional, Tuple
from itertools import product
import sys
import logging
from rich.console import Console
from rich.progress import track
from rich.panel import Panel
from rich import print as rprint
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

console = Console()

class TripType(Enum):
    ROUND_TRIP = "round_trip"
    ONE_WAY = "one_way"

class ConfigError(Exception):
    pass

class DateError(Exception):
    pass

class DateRange:
    def __init__(self, start: str, end: str = None):
        try:
            self.start = datetime.strptime(start, '%Y-%m-%d')
            self.end = datetime.strptime(end, '%Y-%m-%d') if end else self.start
            
            if self.end < self.start:
                raise DateError(f"End date {end} cannot be before start date {start}")
                
        except ValueError as e:
            raise DateError(f"Invalid date format. Please use YYYY-MM-DD format: {str(e)}")

    def get_dates(self) -> List[datetime]:
        if self.start == self.end:
            return [self.start]
        dates = []
        current = self.start
        while current <= self.end:
            dates.append(current)
            current += timedelta(days=1)
        return dates

class ConfigGenerator:
    def __init__(self, config_path: str):
        self.config = self.load_config(config_path)
        self.base_dir = "all_trip_combinations"
        self.round_trip_dir = os.path.join(self.base_dir, "round_trip_combinations")
        self.single_trip_dir = os.path.join(self.base_dir, "single_trip_combinations")
        self.trip_type = TripType.ONE_WAY if 'return_dates' not in self.config else TripType.ROUND_TRIP
        
    def cleanup_existing_folders(self):
        console.print(f"\n[bold cyan]{'='*20} Cleaning Up Existing Folders {'='*20}[/bold cyan]")
        
        folders_to_clean = [
            (self.base_dir, "Base directory"),
            (self.round_trip_dir, "Round trip combinations directory"),
            (self.single_trip_dir, "Single trip combinations directory")
        ]
        
        for folder, description in folders_to_clean:
            if os.path.exists(folder):
                try:
                    shutil.rmtree(folder)
                    console.print(f"[green]OK[/green] Removed existing {description}: {folder}")
                except Exception as e:
                    console.print(f"[red]ERROR[/red] Error removing {description}: {str(e)}")
                    raise
        
        console.print("[green]Cleanup completed successfully[/green]\n")

    def display_config_format(self):
        example_config = {
            "origins": ["City1", "City2"],
            "destinations": ["CityA", "CityB"],
            "departure_dates": [
                "2025-01-01",
                {"start": "2025-01-05", "end": "2025-01-07"}
            ],
            "return_dates": [
                "2025-02-01",
                {"start": "2025-02-05", "end": "2025-02-07"}
            ],
            "search_modifier": "cheapest two person"
        }
        console.print(Panel.fit(
            f"Expected config format:\n{json.dumps(example_config, indent=2)}",
            title="Configuration Format",
            border_style="yellow"
        ))

    def validate_city_names(self, cities: List[str], field_name: str) -> None:
        if not cities or not isinstance(cities, list):
            raise ConfigError(f"{field_name} must be a non-empty list of cities")
        
        for city in cities:
            if not isinstance(city, str):
                raise ConfigError(f"Invalid city in {field_name}: {city}")
            if len(city.strip()) == 0:
                raise ConfigError(f"Empty city name found in {field_name}")

    def validate_dates(self, dates: List[Union[str, Dict]], field_name: str) -> None:
        if not dates or not isinstance(dates, list):
            raise ConfigError(f"{field_name} must be a non-empty list")
        
        for date in dates:
            if isinstance(date, str):
                try:
                    datetime.strptime(date, '%Y-%m-%d')
                except ValueError:
                    raise DateError(f"Invalid date format in {field_name}: {date}. Use YYYY-MM-DD")
            elif isinstance(date, dict):
                if not all(key in date for key in ['start', 'end']):
                    raise ConfigError(f"Date range in {field_name} must have 'start' and 'end' fields")
                try:
                    start = datetime.strptime(date['start'], '%Y-%m-%d')
                    end = datetime.strptime(date['end'], '%Y-%m-%d')
                    if end < start:
                        raise DateError(f"End date {date['end']} cannot be before start date {date['start']}")
                except ValueError as e:
                    raise DateError(f"Invalid date format in {field_name}: {str(e)}")
            else:
                raise ConfigError(f"Invalid date format in {field_name}: {date}")

    def load_config(self, path: str) -> Dict:
        logger.info(f"Loading configuration from {path}")
        
        if not os.path.exists(path):
            raise ConfigError(f"Configuration file not found: {path}")
            
        try:
            with open(path, 'r') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {str(e)}")
            self.display_config_format()
            raise ConfigError(f"Invalid JSON format in config file: {str(e)}")
        
        required = ['origins', 'destinations', 'departure_dates']
        missing = [key for key in required if key not in config]
        if missing:
            logger.error(f"Missing required fields: {missing}")
            self.display_config_format()
            raise ConfigError(f"Missing required fields: {', '.join(missing)}")
            
        self.validate_city_names(config['origins'], 'origins')
        self.validate_city_names(config['destinations'], 'destinations')
        
        self.validate_dates(config['departure_dates'], 'departure_dates')
        if 'return_dates' in config:
            self.validate_dates(config['return_dates'], 'return_dates')

        if 'search_modifier' in config and not isinstance(config['search_modifier'], str):
            raise ConfigError("search_modifier must be a string")
        
        logger.info("Configuration validated successfully")
        return config

    def parse_date_config(self, date_config: Union[str, Dict[str, str]]) -> List[datetime]:
        try:
            if isinstance(date_config, str):
                return [datetime.strptime(date_config, '%Y-%m-%d')]
            elif isinstance(date_config, dict):
                if 'start' in date_config and 'end' in date_config:
                    return DateRange(date_config['start'], date_config['end']).get_dates()
                raise ConfigError("Date range must contain 'start' and 'end' fields")
            raise ConfigError(f"Invalid date format: {date_config}")
        except ValueError as e:
            raise DateError(f"Invalid date format: {str(e)}")

    def generate_single_trip_config(self, origin: str, dest: str, date: datetime, 
                                  file_counter: int, is_return: bool = False) -> Tuple[str, Dict]:
        if is_return:
            filename = f"{file_counter}b.json"
        else:
            filename = f"{file_counter}a.json" if self.trip_type == TripType.ROUND_TRIP else f"{file_counter}.json"
            
        config = {
            'origin': origin,
            'destination': dest,
            'depart_date': date.strftime('%Y-%m-%d')
        }

        if 'search_modifier' in self.config:
            config['search_modifier'] = self.config['search_modifier']
        
        return filename, config

    def generate_configs(self):
        self.cleanup_existing_folders()
        logger.info(f"Starting configuration generation - Mode: {self.trip_type.value}")
        
        os.makedirs(self.single_trip_dir, exist_ok=True)
        if self.trip_type == TripType.ROUND_TRIP:
            os.makedirs(self.round_trip_dir, exist_ok=True)
        
        origins = self.config['origins']
        destinations = self.config['destinations']
        
        departure_dates = []
        for date_config in self.config['departure_dates']:
            departure_dates.extend(self.parse_date_config(date_config))
        
        return_dates = []
        if self.trip_type == TripType.ROUND_TRIP:
            for date_config in self.config['return_dates']:
                return_dates.extend(self.parse_date_config(date_config))
        
        total_one_way = len(origins) * len(destinations) * len(departure_dates)
        total_combinations = total_one_way * (len(return_dates) if return_dates else 1)
        
        valid_combinations = 0
        skipped_combinations = 0
        
        logger.info(f"Processing {total_combinations} potential combinations")
        console.print(f"\n[bold green]Starting generation of {self.trip_type.value} combinations[/bold green]")
        console.print(f"Found {len(origins)} origins, {len(destinations)} destinations")
        console.print(f"Departure dates: {len(departure_dates)}")
        if return_dates:
            console.print(f"Return dates: {len(return_dates)}\n")

        file_counter = 1
        
        with console.status("[bold green]Generating configurations...") as status:
            if self.trip_type == TripType.ONE_WAY:
                combinations = product(origins, destinations, departure_dates)
                for origin, dest, dep_date in track(
                    list(combinations), 
                    description="Processing one-way combinations..."
                ):
                    if origin == dest:
                        logger.debug(f"Skipping same origin/destination: {origin}")
                        skipped_combinations += 1
                        continue

                    filename, config = self.generate_single_trip_config(
                        origin, dest, dep_date, file_counter
                    )
                    filepath = os.path.join(self.single_trip_dir, filename)
                    
                    try:
                        with open(filepath, 'w') as f:
                            json.dump(config, f, indent=4)
                        valid_combinations += 1
                        file_counter += 1
                        
                        console.print(
                            f"[cyan]Generated[/cyan] {origin} -> {dest}: "
                            f"Date: {dep_date.strftime('%Y-%m-%d')}"
                        )
                    except IOError as e:
                        logger.error(f"Error writing configuration file {filepath}: {str(e)}")
                        raise ConfigError(f"Failed to write configuration file: {str(e)}")
            
            else:
                combinations = product(origins, destinations, departure_dates, return_dates)
                for origin, dest, dep_date, ret_date in track(
                    list(combinations), 
                    description="Processing round-trip combinations..."
                ):
                    if origin == dest:
                        logger.debug(f"Skipping same origin/destination: {origin}")
                        skipped_combinations += 1
                        continue
                        
                    if dep_date >= ret_date:
                        logger.debug(
                            f"Skipping invalid dates: Departure {dep_date.strftime('%Y-%m-%d')} "
                            f"not before return {ret_date.strftime('%Y-%m-%d')}"
                        )
                        skipped_combinations += 1
                        continue

                    filename_a, config_a = self.generate_single_trip_config(
                        origin, dest, dep_date, file_counter
                    )
                    filepath_a = os.path.join(self.single_trip_dir, filename_a)
                    
                    filename_b, config_b = self.generate_single_trip_config(
                        dest, origin, ret_date, file_counter, is_return=True
                    )
                    filepath_b = os.path.join(self.single_trip_dir, filename_b)
                    
                    round_trip_config = {
                        'origin': origin,
                        'destination': dest,
                        'depart_date': dep_date.strftime('%Y-%m-%d'),
                        'return_date': ret_date.strftime('%Y-%m-%d')
                    }

                    if 'search_modifier' in self.config:
                        round_trip_config['search_modifier'] = self.config['search_modifier']
                    
                    try:
                        with open(filepath_a, 'w') as f:
                            json.dump(config_a, f, indent=4)
                        with open(filepath_b, 'w') as f:
                            json.dump(config_b, f, indent=4)
                        with open(os.path.join(self.round_trip_dir, f"{file_counter}.json"), 'w') as f:
                            json.dump(round_trip_config, f, indent=4)
                            
                        valid_combinations += 1
                        file_counter += 1
                        
                        console.print(
                            f"[cyan]Generated[/cyan] Round Trip {origin} <-> {dest}: "
                            f"Outbound: {dep_date.strftime('%Y-%m-%d')}, "
                            f"Return: {ret_date.strftime('%Y-%m-%d')}"
                        )
                    except IOError as e:
                        logger.error(f"Error writing configuration files: {str(e)}")
                        raise ConfigError(f"Failed to write configuration files: {str(e)}")

        console.print("\n[bold green]Generation Complete![/bold green]")
        console.print(f"Total potential combinations: {total_combinations}")
        console.print(f"Valid combinations generated: {valid_combinations}")
        console.print(f"Skipped invalid combinations: {skipped_combinations}")
        console.print(f"Configuration files saved in: {self.base_dir}")
        if self.trip_type == TripType.ROUND_TRIP:
            console.print(f"Single leg configurations: {self.single_trip_dir}")
            console.print(f"Round trip configurations: {self.round_trip_dir}\n")
        else:
            console.print(f"One-way configurations: {self.single_trip_dir}\n")

def display_usage():
    usage = """
    Trip Configuration Generator
    ---------------------------
    
    Usage: python config_generator.py <config_file>
    
    The config file must be a JSON file with the following structure:
    {
        "origins": ["City1", "City2", ...],
        "destinations": ["CityA", "CityB", ...],
        "departure_dates": [
            "2025-01-01",
            {"start": "2025-01-05", "end": "2025-01-07"},
            ...
        ],
        "return_dates": [
            "2025-02-01",
            {"start": "2025-02-05", "end": "2025-02-07"},
            ...
        ],
        "search_modifier": "optional search modifier string"
    }
    
    Notes:
    - Dates can be specified as single dates (YYYY-MM-DD) or date ranges
    - Date ranges must have 'start' and 'end' dates
    - Origins and destinations must be non-empty lists of city names
    - Same origin and destination combinations are automatically filtered out
    - Search modifier is optional and will be added to all generated configs if present
    - If return_dates is included:
        - Return dates must be after departure dates
        - Files will be generated as 1a.json/1b.json pairs in single_trip_combinations
        - Complete round trips will be saved in round_trip_combinations
    - If return_dates is omitted:
        - Only one-way trips will be generated
        - Files will be numbered sequentially (1.json, 2.json, etc.)
        - Only single_trip_combinations folder will be created
    """
    console.print(Panel(usage, title="Usage Instructions", border_style="blue"))

def main():
    if len(sys.argv) != 2:
        display_usage()
        sys.exit(1)
    
    try:
        generator = ConfigGenerator(sys.argv[1])
        generator.generate_configs()
    except (ConfigError, DateError) as e:
        console.print(f"\n[bold red]Error:[/bold red] {str(e)}")
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {str(e)}")
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
