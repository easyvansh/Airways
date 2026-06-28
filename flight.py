from dataclasses import dataclass
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
import json
import re
import platform
import os
import subprocess
import sys
import logging
import urllib.parse
from typing import List, Optional, Dict, Tuple
from enum import Enum
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class ConfigError(Exception):
    pass

class DriverError(Exception):
    pass

class Config:
    BROWSER_ARGS = [
        '--headless=new',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--window-size=1920,1080',
    ]
    WAIT_TIMEOUT = 10
    RESULTS_FILE = "flights.txt"
    MAX_RESULTS = 30

    @staticmethod
    def get_platform_config() -> Dict[str, str]:
        try:
            system = platform.system()
            machine = platform.machine().lower()
            
            logger.info(f"Detected system: {system} on {machine} architecture")
            
            configs = {
                'system': system,
                'machine': machine,
                'chromedriver_path': None,
                'platform_args': []
            }
            
            if system == "Darwin":
                if machine in ['arm64', 'aarch64']:
                    configs['platform_args'] = [
                        '--use-angle=metal',
                        '--use-cmd-decoder=passthrough'
                    ]
                    configs['chromedriver_path'] = '/opt/homebrew/bin/chromedriver'
                else:
                    configs['platform_args'] = ['--disable-gpu']
                    configs['chromedriver_path'] = '/usr/local/bin/chromedriver'
            
            elif system == "Linux":
                configs['platform_args'] = ['--disable-gpu']
                try:
                    configs['chromedriver_path'] = subprocess.getoutput('which chromedriver')
                except subprocess.SubprocessError as e:
                    logger.warning(f"Failed to locate chromedriver using 'which': {e}")
                    configs['chromedriver_path'] = '/usr/bin/chromedriver'
            
            elif system == "Windows":
                configs['platform_args'] = ['--disable-gpu']
                configs['chromedriver_path'] = None
            
            else:
                raise ConfigError(f"Unsupported operating system: {system}")
            
            return configs
            
        except Exception as e:
            logger.error(f"Error getting platform configuration: {e}")
            raise ConfigError(f"Failed to determine platform configuration: {str(e)}")

class FlightSelectors(str, Enum):
    ITEM = "li.pIav2d"
    FULL_DETAILS = '.JMc5Xc'

@dataclass
class FlightDetails:
    full_details: str = "N/A"
    
    def is_valid(self) -> bool:
        return self.full_details != "N/A"
    
    def clean_details(self) -> str:
        if not self.is_valid():
            return ""
        details = self.full_details
        details = re.sub(r'Carbon emissions estimate:.*kilograms\.', '', details)
        details = details.replace("Select flight", "").strip()
        return details

@dataclass
class SearchConfig:
    origin: str
    destination: str
    depart_date: str
    return_date: Optional[str] = None
    search_modifier: Optional[str] = None
    
    @property
    def is_round_trip(self) -> bool:
        return self.return_date is not None

    def get_modified_search_term(self, base_term: str) -> str:
        if self.search_modifier:
            return f"{self.search_modifier.replace(' ', '+')}+{base_term}"
        return base_term
    
    @classmethod
    def from_file(cls, config_path: str) -> 'SearchConfig':
        try:
            with open(config_path, 'r') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    print("Invalid JSON format. Usage:")
                    print("One-way config: {'origin': 'City', 'destination': 'City', 'depart_date': 'YYYY-MM-DD', 'search_modifier': 'optional modifier'}")
                    print("Round-trip config: {'origin': 'City', 'destination': 'City', 'depart_date': 'YYYY-MM-DD', 'return_date': 'YYYY-MM-DD', 'search_modifier': 'optional modifier'}")
                    raise ConfigError(f"Invalid JSON format in config file: {e}")
                
                required_fields = ['origin', 'destination', 'depart_date']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    raise ConfigError(f"Missing required fields in config: {', '.join(missing_fields)}")
                
                for field in required_fields:
                    if not isinstance(data[field], str):
                        raise ConfigError(f"{field} must be a string")
                
                if 'return_date' in data and not isinstance(data['return_date'], str):
                    raise ConfigError("return_date must be a string")
                
                if 'search_modifier' in data and not isinstance(data['search_modifier'], str):
                    raise ConfigError("search_modifier must be a string")
                
                return cls(**data)
                
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {config_path}")
        except Exception as e:
            raise ConfigError(f"Error reading config file: {str(e)}")

class FlightSearch:
    def __init__(self):
        self.platform_config = Config.get_platform_config()
        logger.info(f"Platform configuration loaded: {self.platform_config['system']} {self.platform_config['machine']}")
        self.driver = self._create_driver()
        self.wait = WebDriverWait(self.driver, Config.WAIT_TIMEOUT)
    
    def _find_chromedriver(self) -> Optional[str]:
        default_path = self.platform_config['chromedriver_path']
        
        if default_path and os.path.exists(default_path):
            logger.info(f"Found ChromeDriver at default path: {default_path}")
            return default_path
        
        try:
            command = 'where chromedriver' if self.platform_config['system'] == "Windows" else 'which chromedriver'
            path = subprocess.getoutput(command).splitlines()[0].strip()
            if path and os.path.exists(path):
                logger.info(f"Found ChromeDriver in PATH: {path}")
                return path
        except Exception as e:
            logger.warning(f"Failed to locate chromedriver in PATH: {e}")
        
        logger.info("ChromeDriver not found in PATH; Selenium Manager will try to resolve it.")
        return None
    
    def _create_driver(self) -> webdriver.Chrome:
        logger.info("Initializing Chrome WebDriver...")
        try:
            options = Options()
            
            for arg in Config.BROWSER_ARGS:
                options.add_argument(arg)
                
            for arg in self.platform_config['platform_args']:
                options.add_argument(arg)
            
            prefs = {
                'profile.default_content_setting_values.notifications': 2,
                'profile.managed_default_content_settings.images': 2,
            }
            options.add_experimental_option('prefs', prefs)
            
            driver_path = self._find_chromedriver()
            if driver_path:
                service = Service(driver_path)
                return webdriver.Chrome(service=service, options=options)

            return webdriver.Chrome(options=options)
            
        except Exception as e:
            logger.error(f"Failed to create Chrome WebDriver: {e}")
            raise DriverError(f"Failed to initialize Chrome WebDriver: {str(e)}")
    
    def _find_element_text(self, el: WebElement, selector: str, get_attr: Optional[str] = None) -> str:
        try:
            element = el.find_element(By.CSS_SELECTOR, selector)
            return (element.get_attribute(get_attr) if get_attr else element.text).strip() or "N/A"
        except NoSuchElementException:
            logger.warning(f"Element not found with selector: {selector}")
            return "N/A"
        except Exception as e:
            logger.warning(f"Error finding element text: {e}")
            return "N/A"
    
    def _extract_flight_details(self, flight_el: WebElement) -> FlightDetails:
        try:
            return FlightDetails(
                full_details=self._find_element_text(flight_el, FlightSelectors.FULL_DETAILS, "aria-label")
            )
        except Exception as e:
            logger.warning(f"Error extracting flight details: {e}")
            return FlightDetails()
    
    def _write_results(self, results: List[FlightDetails], start_number: int) -> None:
        try:
            with open(Config.RESULTS_FILE, "w", encoding="utf-8") as f:
                if not results:
                    logger.warning("No flights found to write to results file")
                    f.write("Found no flights.")
                    return
                
                valid_flights = [result.clean_details() for result in results if result.is_valid()]
                if not valid_flights:
                    logger.warning("No valid flights found to write to results file")
                    f.write("Found no flights.")
                    return
                
                logger.info(f"Writing {len(valid_flights)} flights to results file")
                for i, details in enumerate(valid_flights, start_number):
                    if details:
                        f.write(f"{i}: {details}\n")
                        
        except Exception as e:
            logger.error(f"Error writing results to file: {e}")
            raise IOError(f"Failed to write results to file: {str(e)}")
    
    def search(self, config: SearchConfig, start_number: int, currency: str = "CAD") -> List[FlightDetails]:
        if config.is_round_trip:
            print("Detected round trip flight search")
            query = (
                f"Flights to {config.destination} from {config.origin} on "
                f"{config.depart_date} through {config.return_date} round trip"
            )
        else:
            print("Detected one-way flight search")
            query = (
                f"Flights to {config.destination} from {config.origin} on "
                f"{config.depart_date} oneway"
            )

        params = urllib.parse.urlencode({
            "q": query,
            "hl": "en",
            "gl": "CA",
            "curr": currency,
        })
        url = f"https://www.google.com/travel/flights/search?{params}"
        
        logger.info(f"Starting search for {'round-trip' if config.is_round_trip else 'one-way'} flights from {config.origin} to {config.destination}")
        
        try:
            logger.info("Opening Google Flights...")
            self.driver.get(url)
            
            logger.info("Waiting for flight results...")
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, FlightSelectors.ITEM)))
            flights = self.wait.until(EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, FlightSelectors.ITEM)))[:Config.MAX_RESULTS]
            
            logger.info(f"Processing {len(flights)} flights...")
            results = [self._extract_flight_details(flight) for flight in flights]
            
            logger.info("Saving search results...")
            self._write_results(results, start_number)
            return results
            
        except TimeoutException:
            logger.error("Timeout waiting for flight results")
            return []
        except WebDriverException as e:
            logger.error(f"WebDriver error during search: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during search: {e}")
            return []
    
    def close(self):
        if self.driver:
            logger.info("Closing Chrome WebDriver...")
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error closing Chrome WebDriver: {e}")

def validate_args() -> Tuple[bool, str, int]:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python3 flights.py config.json [start_number]")
        return False, "", 0
    
    config_path = sys.argv[1]
    if not config_path.endswith('.json'):
        print("Error: Config file must be a JSON file")
        return False, "", 0
    
    start_number = 1
    if len(sys.argv) == 3:
        try:
            start_number = int(sys.argv[2])
        except ValueError:
            print("Error: start_number must be an integer")
            return False, "", 0
    else:
        print("No start number provided, defaulting to 1")
    
    return True, config_path, start_number

def main():
    logger.info("Starting flight search application...")
    
    is_valid, config_path, start_number = validate_args()
    if not is_valid:
        return
    
    try:
        config = SearchConfig.from_file(config_path)
        logger.info("Configuration loaded successfully")
        
        searcher = FlightSearch()
        try:
            results = searcher.search(config, start_number)
            if results:
                logger.info("Search completed successfully!")
            else:
                logger.warning("No results found during search")
        finally:
            searcher.close()
            
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        print(f"Configuration error: {e}")
    except DriverError as e:
        logger.error(f"Driver error: {e}")
        print(f"Driver error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
