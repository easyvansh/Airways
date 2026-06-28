import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from flight import FlightDetails, FlightSearch, SearchConfig


DEFAULT_CONFIG_DIR = Path("all_trip_combinations") / "single_trip_combinations"
DEFAULT_OUTPUT_FILE = Path("yeg_del_one_way_results.txt")
DEFAULT_JSON_OUTPUT_FILE = Path("flight_results.json")
DEFAULT_TARGET_CURRENCY = "CAD"


@dataclass
class ParsedFlight:
    config_file: str
    origin: str
    destination: str
    depart_date: str
    rank: int
    raw_price: Optional[float]
    raw_currency: Optional[str]
    converted_price: Optional[float]
    target_currency: str
    airlines: List[str]
    duration_minutes: Optional[int]
    stops: Optional[int]
    connecting_airports: List[str]
    full_details: str
    warnings: List[str]

    @property
    def cad_price(self) -> Optional[float]:
        return self.converted_price if self.target_currency == "CAD" else None


def load_configs(config_dir: Path) -> List[Path]:
    if not config_dir.exists():
        raise FileNotFoundError(
            f"Generated config directory not found: {config_dir}. "
            "Run trip_configurator.py first."
        )

    def sort_key(path: Path):
        match = re.match(r"(\d+)", path.stem)
        return int(match.group(1)) if match else path.name

    return sorted(config_dir.glob("*.json"), key=sort_key)


def fetch_rates(currencies: Iterable[str], target_currency: str) -> Dict[str, float]:
    rates = {target_currency: 1.0}
    for currency in sorted({c for c in currencies if c and c != target_currency}):
        url = (
            "https://api.frankfurter.app/latest?"
            + urllib.parse.urlencode({"from": currency, "to": target_currency})
        )
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rate = payload.get("rates", {}).get(target_currency)
            if isinstance(rate, (int, float)):
                rates[currency] = float(rate)
        except Exception as exc:
            print(f"Warning: could not fetch {currency}->{target_currency} rate: {exc}")
    return rates


def parse_price(details: str, default_currency: str = DEFAULT_TARGET_CURRENCY) -> Tuple[Optional[float], Optional[str]]:
    symbol_match = re.search(r"\b(?:from\s+)?(CA\$|US\$|\$)\s*([\d,]+(?:\.\d+)?)\b", details, re.IGNORECASE)
    if symbol_match:
        symbol = symbol_match.group(1).upper()
        currency = "CAD" if symbol == "CA$" else "USD" if symbol == "US$" else default_currency
        try:
            return float(symbol_match.group(2).replace(",", "")), currency
        except ValueError:
            return None, None

    match = re.search(r"\bFrom\s+([\d,]+(?:\.\d+)?)\s+([A-Za-z]{3}|Canadian dollars|US dollars)\b", details)
    if not match:
        return None, None

    try:
        amount = float(match.group(1).replace(",", ""))
    except ValueError:
        return None, None

    currency_text = match.group(2).strip()
    currency_map = {
        "Canadian dollars": "CAD",
        "US dollars": "USD",
    }
    return amount, currency_map.get(currency_text, currency_text.upper())


def parse_airlines(details: str) -> List[str]:
    patterns = [
        r"\d+\s+stops?\s+flight\s+with\s+(.+?)\.",
        r"Nonstop flight with (.+?)\.",
    ]
    for pattern in patterns:
        match = re.search(pattern, details)
        if match:
            airlines = re.split(r",|\band\b", match.group(1))
            return [airline.strip() for airline in airlines if airline.strip()]
    return []


def parse_duration(details: str) -> Optional[int]:
    match = re.search(r"Total duration\s+(\d+)\s+hr(?:\s+(\d+)\s+min)?\.", details)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


def parse_stops(details: str) -> Optional[int]:
    if re.search(r"\bNonstop flight\b", details, flags=re.IGNORECASE):
        return 0
    match = re.search(r"\b(\d+)\s+stops?\s+flight\b", details, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_connecting_airports(details: str) -> List[str]:
    airports = []
    for pattern in [
        r"\bLayover(?: \(\d+ of \d+\))?\s+is\s+a\s+.*?\s+layover\s+at\s+(.+?)(?:\.|,|\s+for\b)",
        r"\bChange planes(?: in| at)?\s+(.+?)(?:\.|,|\s+for\b)",
    ]:
        for match in re.finditer(pattern, details, flags=re.IGNORECASE):
            airport = re.sub(r"\s+", " ", match.group(1)).strip()
            if airport and airport not in airports:
                airports.append(airport)
    return airports


def repair_text(text: str) -> str:
    if "\u00c3" not in text:
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return text


def duration_label(minutes: Optional[int]) -> str:
    if minutes is None:
        return "N/A"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def price_label(amount: Optional[float], currency: Optional[str]) -> str:
    if amount is None or not currency:
        return "N/A"
    return f"{amount:,.2f} {currency}"


def converted_label(amount: Optional[float], currency: str) -> str:
    return f"{amount:,.2f} {currency}" if amount is not None else "N/A"


def parse_result(
    config: SearchConfig,
    config_file: Path,
    rank: int,
    details: FlightDetails,
    rates: Dict[str, float],
    target_currency: str,
) -> ParsedFlight:
    clean_details = repair_text(details.clean_details())
    raw_price, raw_currency = parse_price(clean_details, target_currency)
    converted_price = None
    warnings = []

    if raw_price is None:
        warnings.append("Price unavailable")
    elif raw_currency in rates:
        converted_price = round(raw_price * rates[raw_currency], 2)
    else:
        warnings.append(f"No {raw_currency}->{target_currency} exchange rate available")

    return ParsedFlight(
        config_file=config_file.name,
        origin=config.origin,
        destination=config.destination,
        depart_date=config.depart_date,
        rank=rank,
        raw_price=raw_price,
        raw_currency=raw_currency,
        converted_price=converted_price,
        target_currency=target_currency,
        airlines=parse_airlines(clean_details),
        duration_minutes=parse_duration(clean_details),
        stops=parse_stops(clean_details),
        connecting_airports=parse_connecting_airports(clean_details),
        full_details=clean_details,
        warnings=warnings,
    )


def sort_results(results: List[ParsedFlight]) -> List[ParsedFlight]:
    return sorted(
        results,
        key=lambda item: (
            item.converted_price is None,
            item.converted_price if item.converted_price is not None else float("inf"),
            item.stops is None,
            item.stops if item.stops is not None else 99,
            item.duration_minutes is None,
            item.duration_minutes if item.duration_minutes is not None else 99999,
        ),
    )


def dedupe_results(results: List[ParsedFlight]) -> List[ParsedFlight]:
    seen = set()
    unique = []
    for result in results:
        key = (result.depart_date, result.full_details)
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def result_to_dict(result: ParsedFlight) -> Dict:
    data = asdict(result)
    data["cad_price"] = result.cad_price
    data["duration_label"] = duration_label(result.duration_minutes)
    data["raw_price_label"] = price_label(result.raw_price, result.raw_currency)
    data["converted_price_label"] = converted_label(result.converted_price, result.target_currency)
    return data


def build_report(results: List[ParsedFlight], metadata: Dict) -> Dict:
    sorted_results = sort_results(results)
    grouped: Dict[str, List[Dict]] = {}
    for result in sorted_results:
        grouped.setdefault(result.depart_date, []).append(result_to_dict(result))
    return {
        "metadata": metadata,
        "best_overall": [
            result_to_dict(result)
            for result in sorted_results
            if result.converted_price is not None
        ],
        "results_by_date": grouped,
        "results": [result_to_dict(result) for result in sorted_results],
    }


def write_results(results: List[ParsedFlight], output_file: Path, metadata: Optional[Dict] = None) -> None:
    grouped: Dict[str, List[ParsedFlight]] = {}
    for result in sort_results(results):
        grouped.setdefault(result.depart_date, []).append(result)

    target_currency = metadata.get("target_currency", DEFAULT_TARGET_CURRENCY) if metadata else DEFAULT_TARGET_CURRENCY
    route = ""
    if metadata and metadata.get("origin") and metadata.get("destination"):
        route = f" {metadata['origin']} to {metadata['destination']}"

    with output_file.open("w", encoding="utf-8") as handle:
        handle.write(f"One-way{route} flight results\n")
        handle.write("=" * 60 + "\n")
        handle.write(f"Sorted by {target_currency}-equivalent price, then stops, then duration.\n")
        if metadata:
            handle.write(f"Run timestamp: {metadata.get('run_timestamp', 'N/A')}\n")
            if metadata.get("warnings"):
                handle.write("Warnings:\n")
                for warning in metadata["warnings"]:
                    handle.write(f"- {warning}\n")
        handle.write("\n")

        if not grouped:
            handle.write("No flights found.\n")
            return

        for depart_date in sorted(grouped):
            handle.write(f"Departure date: {depart_date}\n")
            handle.write("-" * 60 + "\n")
            for index, result in enumerate(grouped[depart_date], start=1):
                handle.write(f"{index}. {result.origin} -> {result.destination}\n")
                handle.write(f"   Raw price: {price_label(result.raw_price, result.raw_currency)}\n")
                handle.write(f"   {result.target_currency} equivalent: {converted_label(result.converted_price, result.target_currency)}\n")
                handle.write(f"   Airlines: {', '.join(result.airlines) if result.airlines else 'N/A'}\n")
                handle.write(f"   Duration: {duration_label(result.duration_minutes)}\n")
                handle.write(f"   Stops: {result.stops if result.stops is not None else 'N/A'}\n")
                handle.write(
                    "   Connecting airports: "
                    f"{', '.join(result.connecting_airports) if result.connecting_airports else 'N/A'}\n"
                )
                handle.write(f"   Source config: {result.config_file}, scraped rank: {result.rank}\n")
                if result.warnings:
                    handle.write(f"   Warnings: {', '.join(result.warnings)}\n")
                handle.write(f"   Full details: {result.full_details}\n\n")


def write_json_report(report: Dict, output_file: Path) -> None:
    with output_file.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)


def run_batch(
    config_dir: Path,
    output_file: Path,
    pause_seconds: float,
    target_currency: str = DEFAULT_TARGET_CURRENCY,
    json_output_file: Optional[Path] = DEFAULT_JSON_OUTPUT_FILE,
    max_results_per_date: Optional[int] = None,
    max_stops: Optional[int] = None,
) -> Dict:
    config_files = load_configs(config_dir)
    print(f"Found {len(config_files)} generated search config(s) in {config_dir}")

    searcher = FlightSearch()
    raw_results = []
    failed_dates = []
    warnings = []
    origin = None
    destination = None

    try:
        for config_file in config_files:
            config = SearchConfig.from_file(str(config_file))
            origin = origin or config.origin
            destination = destination or config.destination
            if config.return_date:
                warning = f"Skipping round-trip config: {config_file}"
                print(warning)
                warnings.append(warning)
                continue

            print(f"Searching {config.origin} -> {config.destination} on {config.depart_date}")
            details = searcher.search(config, start_number=1, currency=target_currency)
            if not details:
                failed_dates.append(config.depart_date)
                warnings.append(f"No usable results found for {config.depart_date}")
            for rank, detail in enumerate(details, start=1):
                if detail.is_valid():
                    raw_results.append((config, config_file, rank, detail))
            if pause_seconds:
                time.sleep(pause_seconds)
    finally:
        searcher.close()

    currencies = []
    for _, _, _, detail in raw_results:
        _, currency = parse_price(repair_text(detail.clean_details()), target_currency)
        if currency:
            currencies.append(currency)

    rates = fetch_rates(currencies, target_currency)
    parsed_results = [
        parse_result(config, config_file, rank, detail, rates, target_currency)
        for config, config_file, rank, detail in raw_results
    ]
    parsed_results = dedupe_results(parsed_results)

    if max_stops is not None:
        parsed_results = [
            result for result in parsed_results
            if result.stops is None or result.stops <= max_stops
        ]

    if max_results_per_date is not None:
        grouped: Dict[str, List[ParsedFlight]] = {}
        for result in sort_results(parsed_results):
            grouped.setdefault(result.depart_date, []).append(result)
        parsed_results = [
            result
            for results_for_date in grouped.values()
            for result in results_for_date[:max_results_per_date]
        ]

    metadata = {
        "origin": origin,
        "destination": destination,
        "target_currency": target_currency,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_url_pattern": (
            "https://www.google.com/travel/flights/search?"
            "q=Flights+to+DEST+from+ORIGIN+on+DATE+oneway&hl=en&gl=CA&curr=CURRENCY"
        ),
        "config_dir": str(config_dir),
        "text_output_file": str(output_file),
        "json_output_file": str(json_output_file) if json_output_file else None,
        "generated_config_count": len(config_files),
        "result_count": len(parsed_results),
        "failed_dates": failed_dates,
        "warnings": warnings,
        "rates": rates,
    }

    write_results(parsed_results, output_file, metadata)
    report = build_report(parsed_results, metadata)
    if json_output_file:
        write_json_report(report, json_output_file)
    print(f"Saved grouped results to {output_file}")
    if json_output_file:
        print(f"Saved structured results to {json_output_file}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run generated one-way flight searches and group results.")
    parser.add_argument("--config-dir", default=str(DEFAULT_CONFIG_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_FILE))
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT_FILE))
    parser.add_argument("--currency", default=DEFAULT_TARGET_CURRENCY)
    parser.add_argument("--max-results-per-date", type=int)
    parser.add_argument("--max-stops", type=int)
    parser.add_argument("--pause", type=float, default=2.0, help="Seconds to wait between searches.")
    args = parser.parse_args()

    run_batch(
        Path(args.config_dir),
        Path(args.output),
        args.pause,
        target_currency=args.currency.upper(),
        json_output_file=Path(args.json_output),
        max_results_per_date=args.max_results_per_date,
        max_stops=args.max_stops,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
