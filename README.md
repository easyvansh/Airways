<p align="center">
  <img src="ss/airways-logo.svg" alt="Airways logo" width="96" height="96">
</p>

# Airways

Airways is a local flight search and analytics dashboard for comparing Google Flights results across flexible one-way departure dates. It generates one search config per date, runs browser-based flight searches, parses fare and route details, ranks options by converted price, stops, and duration, and saves everything as readable text plus structured JSON.

The app is built for practical flight research: enter a route, scan multiple departure dates, compare the best fares, and keep the output files for review.

## Preview

### Dashboard

![Dashboard Preview](ss/dashboard.png)

### Results

![Results Preview](ss/results.png)

> Add screenshots to the `ss/` folder using `dashboard.png` and `results.png`, or update these links if you prefer different filenames.

## Features

- One-way flight searches across a selected departure date range.
- Airport-code based route input, for example `YEG` to `DEL`.
- Canada-focused defaults with configurable target currency.
- Selenium-powered Google Flights search automation.
- Parsed flight details for price, currency, airline, duration, stops, connecting airports, and full raw details.
- Best-deal ranking by converted price, then stops, then duration.
- Currency conversion for non-target-currency fares when exchange-rate data is available.
- Persistent outputs for generated configs, raw scrape text, final text reports, JSON reports, and run logs.
- Flask dashboard for running searches locally.
- Validation and safeguards for invalid airport codes, bad date ranges, missing prices, failed dates, and unavailable conversions.

## Tech Stack

- Python
- Flask
- Selenium
- Chrome / Selenium Manager or ChromeDriver
- Rich
- HTML
- CSS
- JavaScript

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/easyvansh/Airways.git
cd Airways
```

If your local folder has a different name, run the commands from that project directory.

### 2. Create a Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the App

```bash
python app.py
```

Open the dashboard at:

```text
http://127.0.0.1:5000
```

If port `5000` is already in use, stop the existing process or change the port in `app.py`.

## Usage

1. Open the local dashboard in your browser.
2. Enter the origin airport, destination airport, date range, currency, max results per date, and max stops.
3. Click `Run Search`.
4. Review the Best Overall section and the date-grouped results.
5. Use the generated text and JSON output files for saved analysis.

Default values are currently set for:

- Origin: `YEG`
- Destination: `DEL`
- Currency: `CAD`
- Date range: `2026-07-25` to `2026-07-28`

## Command Line Workflow

Edit `trip.json`:

```json
{
    "origins": ["YEG"],
    "destinations": ["DEL"],
    "departure_dates": [
        {
            "start": "2026-07-25",
            "end": "2026-07-28"
        }
    ],
    "search_modifier": "cheapest CAD"
}
```

Generate one search config per date:

```bash
python trip_configurator.py trip.json
```

Run the batch search:

```bash
python flight_automation.py --currency CAD --max-results-per-date 10
```

Or run the full orchestrator:

```bash
python flight_orchestrator.py trip.json
```

## Outputs

- `all_trip_combinations/single_trip_combinations/`: generated one-way search configs.
- `flights.txt`: latest raw scraped flight details from `flight.py`.
- `yeg_del_one_way_results.txt`: readable grouped report for the default YEG to DEL search.
- `flight_results.json`: structured report used by the dashboard.
- `flight_run_log.txt`: metadata, warnings, result counts, failed dates, and exchange-rate information.

## How It Works

1. `trip_configurator.py` expands `trip.json` into one JSON config per departure date.
2. `flight.py` opens Google Flights with Selenium using a route/date search URL.
3. `flight_automation.py` runs each generated config, parses flight details, converts prices when possible, sorts results, and writes reports.
4. `app.py` provides the Airways dashboard and calls the same pipeline.

## Project Structure

```text
Airways/
|-- ss/
|   |-- airways-logo.svg
|   |-- dashboard.png
|   `-- results.png
|-- all_trip_combinations/
|   `-- single_trip_combinations/
|-- app.py
|-- clean.py
|-- flight.py
|-- flight_automation.py
|-- flight_orchestrator.py
|-- flight_sorter.py
|-- LICENSE
|-- README.md
|-- requirements.txt
|-- trip.json
|-- flights.txt
|-- flight_results.json
|-- flight_run_log.txt
`-- yeg_del_one_way_results.txt
```

## File Guide

- `app.py`: Flask dashboard for entering search inputs, running searches, and displaying ranked results.
- `trip_configurator.py`: Generates per-date flight search configs from `trip.json`.
- `flight.py`: Selenium search engine that opens Google Flights and extracts flight card details.
- `flight_automation.py`: Batch runner, parser, sorter, currency converter, and report writer.
- `flight_orchestrator.py`: Runs config generation and automation together.
- `flight_sorter.py`: Older interactive sorter kept for compatibility.
- `clean.py`: Cleanup utility.
- `ss/`: Logo and README screenshot folder.
- `requirements.txt`: Python dependencies required to run the project.

## Notes

- Use airport codes when possible for better route accuracy.
- Keep date ranges reasonable; the web app currently limits searches to 31 days.
- Some Google Flights cards may show unavailable prices. These are preserved but sorted after priced results.
- Currency conversion only happens when a usable exchange rate is available.
- Google Flights markup can change, so scraping selectors may need maintenance over time.
- Prices and routes are live search snapshots, not booking guarantees.

## License

This project is licensed under the terms in [LICENSE](LICENSE).

## Disclaimer

Airways is for personal flight research and comparison. It uses browser automation against Google Flights, so use it responsibly and avoid excessive automated requests.
