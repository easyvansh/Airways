import json
import re
from html import escape
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, render_template_string, request

from flight_automation import DEFAULT_CONFIG_DIR, run_batch
from trip_configurator import ConfigGenerator


APP_ROOT = Path(__file__).parent
TRIP_CONFIG = APP_ROOT / "trip.json"
JSON_REPORT = APP_ROOT / "flight_results.json"
RUN_LOG = APP_ROOT / "flight_run_log.txt"
MAX_DATE_RANGE_DAYS = 31
SUPPORTED_CURRENCIES = {
    "CAD", "USD", "EUR", "GBP", "INR", "AUD", "JPY", "CHF", "NZD", "SGD"
}

app = Flask(__name__)


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Airways Flight Analytics</title>
  <link rel="icon" href="data:image/svg+xml,%3Csvg width='64' height='64' viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='256' height='256' rx='56' fill='%2308101F'/%3E%3Cpath d='M52 148C84 116 118 91 204 64C175 112 139 153 86 192L96 144L52 148Z' fill='%2378A6FF'/%3E%3Cpath d='M92 143L34 105L76 96L132 123L92 143Z' fill='%238E78FF'/%3E%3Cpath d='M109 162L122 220L151 187L143 136L109 162Z' fill='%2330D6C7'/%3E%3Ccircle cx='198' cy='64' r='8' fill='%235DF0A4'/%3E%3C/svg%3E">
  <style>
    :root {
      --bg: #060915;
      --panel: rgba(13, 20, 35, 0.72);
      --panel-strong: rgba(17, 27, 45, 0.88);
      --terminal: rgba(5, 10, 22, 0.86);
      --ink: #f7f9ff;
      --muted: #a7b1c5;
      --soft: #77849d;
      --line: rgba(216, 227, 255, 0.12);
      --line-strong: rgba(183, 203, 255, 0.24);
      --accent: #78a6ff;
      --accent-2: #8e78ff;
      --accent-3: #30d6c7;
      --bad: #ff9b91;
      --warn: #ffd27a;
      --good: #5df0a4;
      --good-soft: rgba(93, 240, 164, 0.18);
      --glow: rgba(93, 126, 255, 0.26);
      --shadow: 0 26px 90px rgba(0, 0, 0, 0.42);
      --ease: 180ms ease;
    }
    * { box-sizing: border-box; }
    html { color-scheme: dark; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 8% 12%, rgba(88, 128, 255, 0.18), transparent 32rem),
        radial-gradient(circle at 94% 10%, rgba(48, 214, 199, 0.11), transparent 28rem),
        radial-gradient(circle at 86% 86%, rgba(151, 112, 255, 0.14), transparent 34rem),
        linear-gradient(145deg, #050815 0%, #0b1020 48%, #070a14 100%);
      color: var(--ink);
      font-family: "Plus Jakarta Sans", Inter, "Segoe UI", Arial, sans-serif;
      font-size: 15px;
      line-height: 1.5;
      overflow-x: hidden;
      position: relative;
    }
    body::before,
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: -1;
    }
    body::before {
      background-image:
        linear-gradient(rgba(255, 255, 255, 0.034) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.026) 1px, transparent 1px);
      background-size: 48px 48px;
      mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.58), transparent 82%);
    }
    body::after {
      opacity: 0.17;
      background-image:
        radial-gradient(circle, rgba(255, 255, 255, 0.62) 0 1px, transparent 1px);
      background-size: 4px 4px;
      mix-blend-mode: screen;
    }
    header {
      max-width: 1280px;
      margin: 0 auto;
      padding: 30px 24px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }
    main {
      max-width: 1280px;
      margin: 0 auto;
      padding: 12px 24px 46px;
    }
    h1 {
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.35rem);
      line-height: 0.95;
      letter-spacing: -0.058em;
      background: linear-gradient(135deg, #f7f9ff 0%, #a9c0ff 50%, #c8b2ff 100%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
      text-shadow: 0 18px 48px rgba(104, 131, 255, 0.16);
    }
    h2 {
      margin: 30px 0 14px;
      font-size: 18px;
      letter-spacing: -0.02em;
    }
    h3 {
      margin: 0 0 8px;
      font-size: 16px;
      letter-spacing: -0.015em;
    }
    .muted { color: var(--muted); }
    .hero-copy {
      margin-top: 10px;
      max-width: 650px;
      color: var(--muted);
      font-size: 0.95rem;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 12px;
      border-radius: 999px;
      border: 1px solid rgba(120, 166, 255, 0.24);
      background: rgba(120, 166, 255, 0.085);
      color: #dbe6ff;
      font-size: 0.77rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      white-space: nowrap;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 16px 40px rgba(0, 0, 0, 0.2);
    }
    .brand-lockup {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .logo-mark {
      width: clamp(48px, 8vw, 68px);
      height: clamp(48px, 8vw, 68px);
      flex: 0 0 auto;
      filter: drop-shadow(0 18px 34px rgba(80, 128, 255, 0.2));
    }
    .status-badge::before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--good);
      box-shadow: 0 0 16px rgba(93, 240, 164, 0.75);
    }
    form {
      display: grid;
      grid-template-columns: repeat(8, minmax(108px, 1fr));
      gap: 12px;
      align-items: end;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.025)),
        var(--panel);
      backdrop-filter: blur(18px) saturate(140%);
      -webkit-backdrop-filter: blur(18px) saturate(140%);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 16px;
      box-shadow: var(--shadow), inset 0 1px 0 rgba(255, 255, 255, 0.08), inset 0 -44px 80px rgba(0, 0, 0, 0.14);
      position: relative;
      overflow: hidden;
    }
    form::before {
      content: "";
      position: absolute;
      inset: 0;
      height: 1px;
      background: linear-gradient(90deg, rgba(120, 166, 255, 0.32), transparent 38%, rgba(48, 214, 199, 0.16));
      opacity: 0.9;
    }
    label {
      display: grid;
      gap: 7px;
      color: #dce5f7;
      font-size: 0.76rem;
      font-weight: 800;
      letter-spacing: 0.075em;
      text-transform: uppercase;
    }
    input, select, button {
      width: 100%;
      min-height: 44px;
      border-radius: 13px;
      border: 1px solid rgba(162, 184, 255, 0.14);
      padding: 9px 11px;
      font: inherit;
      transition: border-color var(--ease), box-shadow var(--ease), transform var(--ease), background var(--ease), opacity var(--ease);
    }
    input, select {
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.01)),
        var(--terminal);
      color: var(--ink);
      box-shadow: inset 0 1px 16px rgba(0, 0, 0, 0.22);
    }
    input:focus-visible, select:focus-visible, button:focus-visible, summary:focus-visible {
      outline: none;
      border-color: rgba(120, 166, 255, 0.72);
      box-shadow: 0 0 0 4px rgba(120, 166, 255, 0.13), 0 0 28px rgba(120, 166, 255, 0.16);
    }
    button {
      border-color: rgba(255, 255, 255, 0.13);
      background: linear-gradient(135deg, #4f7cff 0%, #7c5cff 58%, #32d6c9 100%);
      color: white;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 14px 38px rgba(79, 124, 255, 0.22), 0 0 18px var(--glow);
    }
    button:hover {
      transform: translateY(-2px);
      border-color: rgba(255, 255, 255, 0.24);
      box-shadow: 0 20px 48px rgba(79, 124, 255, 0.29), 0 0 28px rgba(48, 214, 199, 0.16);
    }
    button:active { transform: translateY(0); opacity: 0.9; }
    .messages {
      margin: 14px 0;
      display: grid;
      gap: 8px;
    }
    .message {
      border-radius: 14px;
      padding: 11px 13px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
    }
    .error { border-color: rgba(255, 155, 145, 0.34); color: #ffd0cb; background: rgba(255, 155, 145, 0.08); }
    .warning { border-color: rgba(255, 210, 122, 0.32); color: #ffe0a1; background: rgba(255, 210, 122, 0.08); }
    .summary {
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }
    .metric {
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.065), rgba(255, 255, 255, 0.022)),
        var(--panel);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06), 0 18px 45px rgba(0, 0, 0, 0.18);
    }
    .metric strong {
      display: block;
      margin-top: 4px;
      font-size: 20px;
      letter-spacing: -0.03em;
    }
    .results {
      display: grid;
      gap: 12px;
    }
    .flight {
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.072), rgba(255, 255, 255, 0.026)),
        var(--panel-strong);
      backdrop-filter: blur(18px) saturate(130%);
      -webkit-backdrop-filter: blur(18px) saturate(130%);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 16px 18px;
      position: relative;
      overflow: hidden;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.06);
      transition: transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1), border-color var(--ease), box-shadow var(--ease), background var(--ease);
    }
    .flight::before {
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 3px;
      background: linear-gradient(180deg, var(--accent), var(--accent-2), var(--accent-3));
      opacity: 0.85;
    }
    .flight::after {
      content: "";
      position: absolute;
      inset: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.48), transparent);
      opacity: 0.16;
      transform: translateX(-35%);
      transition: transform 520ms ease, opacity var(--ease);
    }
    .flight:hover {
      transform: translateY(-3px);
      border-color: rgba(141, 170, 255, 0.36);
      box-shadow: 0 28px 74px rgba(0, 0, 0, 0.35), 0 0 34px rgba(87, 123, 255, 0.11), inset 0 1px 0 rgba(255, 255, 255, 0.08);
    }
    .flight:hover::after {
      opacity: 0.34;
      transform: translateX(34%);
    }
    .flight-head {
      display: grid;
      grid-template-columns: minmax(210px, 1.25fr) minmax(170px, 0.9fr) minmax(150px, 0.75fr) minmax(84px, 0.35fr);
      gap: 16px;
      align-items: start;
      position: relative;
      z-index: 1;
    }
    .price {
      font-size: clamp(1.45rem, 2.4vw, 1.9rem);
      font-weight: 850;
      color: var(--good);
      letter-spacing: -0.04em;
      text-shadow: 0 0 16px rgba(93, 240, 164, 0.28);
      white-space: nowrap;
    }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(140px, 1fr));
      gap: 10px;
      margin-top: 14px;
      position: relative;
      z-index: 1;
    }
    .detail {
      border-top: 1px solid rgba(255, 255, 255, 0.07);
      padding-top: 10px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    .detail strong {
      display: block;
      margin-bottom: 3px;
      color: #eaf1ff;
      font-size: 0.74rem;
      letter-spacing: 0.07em;
      text-transform: uppercase;
    }
    details {
      margin-top: 12px;
      color: var(--muted);
      position: relative;
      z-index: 1;
    }
    summary {
      cursor: pointer;
      color: #bdd0ff;
      font-weight: 800;
      transition: color var(--ease);
    }
    summary:hover { color: #e1e9ff; }
    .file-list {
      margin: 12px 0 0;
      padding-left: 18px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    .rank-chip {
      display: inline-grid;
      place-items: center;
      min-width: 38px;
      height: 38px;
      padding: 0 10px;
      border-radius: 999px;
      background:
        radial-gradient(circle at 30% 25%, rgba(255, 255, 255, 0.42), transparent 20%),
        linear-gradient(135deg, rgba(120, 166, 255, 0.95), rgba(124, 92, 255, 0.9));
      color: #fff;
      font-weight: 850;
      box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.16), 0 0 18px rgba(105, 133, 255, 0.45);
    }
    .route-line {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }
    .route-line h3 { overflow-wrap: anywhere; }
    .stops-pill {
      display: inline-flex;
      width: fit-content;
      margin-top: 7px;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(255, 210, 122, 0.1);
      border: 1px solid rgba(255, 210, 122, 0.22);
      color: #ffe0a1;
      font-size: 0.75rem;
      font-weight: 800;
      letter-spacing: 0.07em;
      text-transform: uppercase;
    }
    .duration-block {
      text-align: center;
      padding-inline: 12px;
      border-inline: 1px solid rgba(255, 255, 255, 0.055);
    }
    .duration-block strong {
      font-size: 1rem;
      letter-spacing: 0.01em;
    }
    .empty-state {
      text-align: center;
      padding: 56px 24px;
      color: var(--muted);
      border: 1px dashed rgba(181, 201, 255, 0.2);
      border-radius: 22px;
      background:
        radial-gradient(circle at 50% 0%, rgba(120, 166, 255, 0.1), transparent 18rem),
        rgba(255, 255, 255, 0.025);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }
    .empty-state::before {
      content: "*";
      display: grid;
      place-items: center;
      width: 3rem;
      height: 3rem;
      margin: 0 auto 1rem;
      border-radius: 50%;
      background: rgba(120, 166, 255, 0.1);
      border: 1px solid rgba(120, 166, 255, 0.22);
      color: #dbe6ff;
      box-shadow: 0 0 28px rgba(120, 166, 255, 0.15);
    }
    @media (max-width: 900px) {
      body { font-size: 14px; }
      header {
        flex-direction: column;
        align-items: flex-start;
        padding: 22px 16px 12px;
      }
      main { padding: 10px 16px 34px; }
      form, .summary, .flight-head, .detail-grid {
        grid-template-columns: 1fr;
      }
      form { border-radius: 20px; }
      .flight { padding: 15px; border-radius: 20px; }
      .duration-block {
        text-align: left;
        padding: 12px 0 0;
        border-inline: 0;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
      }
      .price { white-space: normal; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand-lockup">
      <svg class="logo-mark" viewBox="0 0 256 256" fill="none" aria-label="Airways logo" role="img" xmlns="http://www.w3.org/2000/svg">
        <rect width="256" height="256" rx="56" fill="#08101F"/>
        <rect x="1" y="1" width="254" height="254" rx="55" stroke="url(#aw-border)" stroke-opacity="0.65" stroke-width="2"/>
        <path d="M52 148C84 116 118 91 204 64C175 112 139 153 86 192L96 144L52 148Z" fill="url(#aw-wing)"/>
        <path d="M92 143L34 105L76 96L132 123L92 143Z" fill="url(#aw-trail)" opacity="0.9"/>
        <path d="M109 162L122 220L151 187L143 136L109 162Z" fill="url(#aw-tail)" opacity="0.92"/>
        <path d="M79 70C122 49 165 45 204 64" stroke="#DDE8FF" stroke-opacity="0.75" stroke-width="8" stroke-linecap="round"/>
        <circle cx="198" cy="64" r="8" fill="#5DF0A4"/>
        <defs>
          <linearGradient id="aw-border" x1="22" y1="12" x2="236" y2="246" gradientUnits="userSpaceOnUse">
            <stop stop-color="#78A6FF"/><stop offset="0.55" stop-color="#8E78FF"/><stop offset="1" stop-color="#30D6C7"/>
          </linearGradient>
          <linearGradient id="aw-wing" x1="52" y1="64" x2="204" y2="192" gradientUnits="userSpaceOnUse">
            <stop stop-color="#F7FAFF"/><stop offset="0.45" stop-color="#93B7FF"/><stop offset="1" stop-color="#30D6C7"/>
          </linearGradient>
          <linearGradient id="aw-trail" x1="34" y1="96" x2="132" y2="143" gradientUnits="userSpaceOnUse">
            <stop stop-color="#596BFF"/><stop offset="1" stop-color="#A28BFF"/>
          </linearGradient>
          <linearGradient id="aw-tail" x1="109" y1="136" x2="151" y2="220" gradientUnits="userSpaceOnUse">
            <stop stop-color="#78A6FF"/><stop offset="1" stop-color="#5DF0A4"/>
          </linearGradient>
        </defs>
      </svg>
      <div>
        <h1>Airways</h1>
        <div class="hero-copy">Premium flight analytics for flexible Google Flights search runs, persisted reports, and route-by-date comparison.</div>
      </div>
    </div>
    <div class="status-badge">Analytics View</div>
  </header>
  <main>
    <form method="post">
      <label>Origin
        <input name="origin" value="{{ form.origin }}" maxlength="3" required>
      </label>
      <label>Destination
        <input name="destination" value="{{ form.destination }}" maxlength="3" required>
      </label>
      <label>Start Date
        <input type="date" name="start_date" value="{{ form.start_date }}" required>
      </label>
      <label>End Date
        <input type="date" name="end_date" value="{{ form.end_date }}" required>
      </label>
      <label>Currency
        <select name="currency">
          {% for currency in currencies %}
            <option value="{{ currency }}" {% if form.currency == currency %}selected{% endif %}>{{ currency }}</option>
          {% endfor %}
        </select>
      </label>
      <label>Top Per Date
        <input type="number" name="max_results" value="{{ form.max_results }}" min="1" max="30" required>
      </label>
      <label>Max Stops
        <input type="number" name="max_stops" value="{{ form.max_stops }}" min="0" max="5">
      </label>
      <button type="submit">Run Search</button>
    </form>

    <div class="messages">
      {% for error in errors %}
        <div class="message error">{{ error }}</div>
      {% endfor %}
      {% if report and report.metadata.warnings %}
        {% for warning in report.metadata.warnings %}
          <div class="message warning">{{ warning }}</div>
        {% endfor %}
      {% endif %}
    </div>

    {% if report %}
      <section class="summary">
        <div class="metric"><span class="muted">Route</span><strong>{{ report.metadata.origin }} -> {{ report.metadata.destination }}</strong></div>
        <div class="metric"><span class="muted">Currency</span><strong>{{ report.metadata.target_currency }}</strong></div>
        <div class="metric"><span class="muted">Configs</span><strong>{{ report.metadata.generated_config_count }}</strong></div>
        <div class="metric"><span class="muted">Results</span><strong>{{ report.metadata.result_count }}</strong></div>
        <div class="metric"><span class="muted">Failed Dates</span><strong>{{ report.metadata.failed_dates|length }}</strong></div>
      </section>
      <ul class="file-list">
        <li>{{ report.metadata.text_output_file }}</li>
        <li>{{ report.metadata.json_output_file }}</li>
        <li>{{ run_log }}</li>
      </ul>

      <h2>Best Overall</h2>
      <div class="results">
        {% for flight in report.best_overall[:10] %}
          {{ flight_card(flight)|safe }}
        {% else %}
          <div class="message warning">No priced flights were available for ranking.</div>
        {% endfor %}
      </div>

      {% for depart_date, flights in report.results_by_date.items() %}
        <h2>{{ depart_date }}</h2>
        <div class="results">
          {% for flight in flights %}
            {{ flight_card(flight)|safe }}
          {% endfor %}
        </div>
      {% endfor %}
    {% else %}
      <section class="empty-state">
        <p>Run a search to generate ranked flight cards, persisted reports, and route-by-date analytics.</p>
      </section>
    {% endif %}
  </main>
</body>
</html>
"""


def flight_card(flight: Dict) -> str:
    warnings = ""
    if flight.get("warnings"):
        warnings = f"<div class='message warning'>{escape(', '.join(flight['warnings']))}</div>"
    airports = escape(", ".join(flight.get("connecting_airports") or []) or "N/A")
    airlines = escape(", ".join(flight.get("airlines") or []) or "N/A")
    stops = flight["stops"] if flight["stops"] is not None else "N/A"
    stop_label = "N/A" if stops == "N/A" else f"{stops} stop" if stops == 1 else f"{stops} stops"
    return f"""
    <article class="flight">
      <div class="flight-head">
        <div>
          <div class="route-line">
            <span class="rank-chip">{escape(str(flight['rank']))}</span>
            <h3>{escape(flight['depart_date'])} | {escape(flight['origin'])} -> {escape(flight['destination'])}</h3>
          </div>
          <div class="muted">{airlines}</div>
        </div>
        <div>
          <div class="price">{escape(flight['converted_price_label'])}</div>
          <div class="muted">Raw: {escape(flight['raw_price_label'])}</div>
        </div>
        <div class="duration-block">
          <strong>{escape(flight['duration_label'])}</strong>
          <div class="stops-pill">{escape(str(stop_label))}</div>
        </div>
        <div class="muted">Scraped rank<br>{escape(str(flight['rank']))}</div>
      </div>
      <div class="detail-grid">
        <div class="detail"><strong>Connecting airports</strong><br>{airports}</div>
        <div class="detail"><strong>Source config</strong><br>{escape(flight['config_file'])}</div>
        <div class="detail"><strong>Target currency</strong><br>{escape(flight['target_currency'])}</div>
        <div class="detail"><strong>Raw currency</strong><br>{escape(flight['raw_currency'] or 'N/A')}</div>
      </div>
      {warnings}
      <details>
        <summary>Full details</summary>
        <div>{escape(flight['full_details'])}</div>
      </details>
    </article>
    """


app.jinja_env.globals["flight_card"] = flight_card


def default_form() -> Dict[str, str]:
    return {
        "origin": "YEG",
        "destination": "DEL",
        "start_date": "2026-07-25",
        "end_date": "2026-07-28",
        "currency": "CAD",
        "max_results": "10",
        "max_stops": "",
    }


def validate_form(form: Dict[str, str]) -> List[str]:
    errors = []
    airport_pattern = re.compile(r"^[A-Z]{3}$")
    if not airport_pattern.match(form["origin"]):
        errors.append("Origin must be a 3-letter airport code.")
    if not airport_pattern.match(form["destination"]):
        errors.append("Destination must be a 3-letter airport code.")
    if form["origin"] == form["destination"]:
        errors.append("Origin and destination must be different.")
    if form["currency"] not in SUPPORTED_CURRENCIES:
        errors.append("Unsupported currency selected.")

    try:
        start = datetime.strptime(form["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(form["end_date"], "%Y-%m-%d").date()
    except ValueError:
        errors.append("Dates must be valid YYYY-MM-DD values.")
        return errors

    if end < start:
        errors.append("End date cannot be before start date.")
    if start < date.today():
        errors.append("Start date cannot be in the past.")
    if (end - start).days + 1 > MAX_DATE_RANGE_DAYS:
        errors.append(f"Date range cannot exceed {MAX_DATE_RANGE_DAYS} days.")

    try:
        max_results = int(form["max_results"])
        if max_results < 1 or max_results > 30:
            errors.append("Top per date must be between 1 and 30.")
    except ValueError:
        errors.append("Top per date must be a number.")

    if form["max_stops"]:
        try:
            max_stops = int(form["max_stops"])
            if max_stops < 0 or max_stops > 5:
                errors.append("Max stops must be between 0 and 5.")
        except ValueError:
            errors.append("Max stops must be a number.")

    return errors


def write_trip_config(form: Dict[str, str]) -> None:
    config = {
        "origins": [form["origin"]],
        "destinations": [form["destination"]],
        "departure_dates": [
            {
                "start": form["start_date"],
                "end": form["end_date"],
            }
        ],
        "search_modifier": f"cheapest {form['currency']}",
    }
    with TRIP_CONFIG.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=4)


def output_text_path(form: Dict[str, str]) -> Path:
    if form["origin"] == "YEG" and form["destination"] == "DEL":
        return APP_ROOT / "yeg_del_one_way_results.txt"
    return APP_ROOT / f"{form['origin'].lower()}_{form['destination'].lower()}_one_way_results.txt"


def write_run_log(report: Dict) -> None:
    metadata = report.get("metadata", {})
    with RUN_LOG.open("w", encoding="utf-8") as handle:
        handle.write("Airways run log\n")
        handle.write("=" * 40 + "\n")
        for key, value in metadata.items():
            handle.write(f"{key}: {value}\n")


def run_search(form: Dict[str, str]) -> Dict:
    write_trip_config(form)
    ConfigGenerator(str(TRIP_CONFIG)).generate_configs()
    max_stops: Optional[int] = int(form["max_stops"]) if form["max_stops"] else None
    report = run_batch(
        DEFAULT_CONFIG_DIR,
        output_text_path(form),
        pause_seconds=1.0,
        target_currency=form["currency"],
        json_output_file=JSON_REPORT,
        max_results_per_date=int(form["max_results"]),
        max_stops=max_stops,
    )
    write_run_log(report)
    return report


def load_existing_report() -> Optional[Dict]:
    if not JSON_REPORT.exists():
        return None
    try:
        with JSON_REPORT.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


@app.route("/", methods=["GET", "POST"])
def index():
    form = default_form()
    errors: List[str] = []
    report = load_existing_report()

    if request.method == "POST":
        form.update({
            "origin": request.form.get("origin", "").strip().upper(),
            "destination": request.form.get("destination", "").strip().upper(),
            "start_date": request.form.get("start_date", "").strip(),
            "end_date": request.form.get("end_date", "").strip(),
            "currency": request.form.get("currency", "CAD").strip().upper(),
            "max_results": request.form.get("max_results", "10").strip(),
            "max_stops": request.form.get("max_stops", "").strip(),
        })
        errors = validate_form(form)
        if not errors:
            try:
                report = run_search(form)
            except Exception as exc:
                errors.append(f"Search failed: {exc}")

    return render_template_string(
        PAGE_TEMPLATE,
        form=form,
        errors=errors,
        report=report,
        currencies=sorted(SUPPORTED_CURRENCIES),
        run_log=str(RUN_LOG),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
