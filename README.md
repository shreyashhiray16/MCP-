# Pune Transit and Commute MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP SDK](https://img.shields.io/badge/MCP-2.3.0-green.svg)](https://modelcontextprotocol.io)
[![Tests](https://img.shields.io/badge/tests-35%20passed-brightgreen.svg)](#testing)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

An official **Model Context Protocol (MCP)** server built in **Python** that empowers Claude (and any MCP-compliant AI client) to answer real-world transit and commute questions across Pune and Pimpri-Chinchwad accurately:

> *"Which bus stops are near Pimpri station?"*  
> *"When is the next bus from the Shivajinagar stop towards Hinjewadi?"*  
> *"What are the first and last metro trains from Swargate?"*  
> *"Best way from home to college, leaving at 8:30 am?"*  
> *"Remember Hinjewadi Phase 1 as my office."*  
> *"Which route stops at both Pimpri and Deccan?"*

---

## Architecture

```
   Claude Desktop (stdio)            Claude Remote Connector (HTTPS)
          │                                        │
    Stdio Transport                   Streamable HTTP (/mcp) + Bearer Auth
          │                                        │
          └──────────────────┬─────────────────────┘
                             │
                      MCPServer (Python)
         Tools │ Resources │ Prompts │ Pydantic Validation │ Typed Errors
                             │
                      services/ (Pure Python)
       places.py │ stops.py │ departures.py │ planner.py
                             │
        ┌────────────────────┼────────────────────┬─────────────────┐
     SQLite              metro.json             Nominatim          GTFS-RT
  (pune_transit.db)   (Pydantic-checked)     (httpx + LRU)       (optional)
```

- **Handlers stay thin**: MCP handlers validate inputs, call the service layer, and return structured payloads with `source` and `data_as_of` metadata.
- **Protocol isolation**: Stdio logging is redirected strictly to `sys.stderr` so JSON-RPC communication on `stdout` is never corrupted.
- **Deterministic responses**: No hallucinated routes or fake timetables. If service is unavailable, Claude receives structured `NO_SERVICE` or `PLACE_NOT_FOUND` errors with actionable user hints.

---

## MCP Primitives

### 1. Tools (8 Tools)

| Tool | Description | Key Inputs |
| :--- | :--- | :--- |
| `resolve_place` | Resolves a Pune place name or landmark into coordinates. Handles ambiguity with candidate suggestions. | `query: str` |
| `find_nearby_stops` | Discovers bus stops and metro stations within walking distance of coordinates using bounding box prefilter + Haversine distance. | `lat, lng, radius_m, mode, limit` |
| `next_departures` | Upcoming scheduled departures at a stop/station in Indian Standard Time (IST), taking into account GTFS calendar schedules, active services, and after-midnight trips. | `stop_id, route, after, limit` |
| `find_routes_between` | Finds direct bus routes connecting two stops in travel sequence order. | `from_stop_id, to_stop_id` |
| `metro_info` | Pune Metro (Maha-Metro Purple & Aqua Lines) station lists, operational hours (06:00 - 22:00 IST), and official fares with Civil Court interchange logic. | `line, station, second_station` |
| `plan_trip` | Ranked multi-modal door-to-door trip itineraries (direct bus, metro, 1-transfer connections, and walking legs) with road travel comparisons. | `origin, destination, depart_at, arrive_by, modes, max_walk_m` |
| `save_place` | Saves personal favourite places (e.g. `home`, `office`, `college`) in SQLite with tenant isolation. | `label, place` |
| `list_saved_places` | Lists previously saved favourite places for the user. | *None* |

### 2. Resources (4 Resources)

- `transit://pune/routes`: JSON list of all public bus routes operating in Pune.
- `transit://pune/stops/{stop_id}`: Resource template returning details for a specific stop and all serving routes.
- `transit://pune/metro`: Complete Pune Metro operational network, stations, first/last trains, and fare rules.
- `transit://user/places`: User-saved favourite commute locations.

### 3. Prompts (2 Prompts)

- `morning_commute`: Guides Claude to retrieve saved commute origins/destinations, call `plan_trip`, compare alternatives, and recommend the best route.
- `explore_area`: Guides Claude to investigate public transit access (bus stops, routes, metro) for any Pune neighborhood.

---

## Quick Start

### 1. Prerequisites
- Python 3.11 or newer
- Git

### 2. Install Dependencies
```bash
git clone https://github.com/example/pune-transit-mcp.git
cd pune-transit-mcp
pip install -r requirements.txt
```

### 3. Ingest Transit Data
Generate the seed PMPML GTFS dataset and populate the SQLite database:
```bash
python scripts/ingest_gtfs.py
```
*Output:*
```
[Ingest] Seed GTFS files generated at: ./data/gtfs
         Stops: 26, Routes: 10, Trips: 1060, StopTimes: 6572
[Ingest] Successfully loaded GTFS into: ./data/pune_transit.db
[Ingest] Validation Report Summary: { "status": "PASS" }
```

### 4. Run the Web Application & Server
Launch the live interactive web UI and MCP backend:
```bash
npm start
# or
python -m src.http_server
```
Then open **[http://localhost:8000](http://localhost:8000)** in your browser!

### 5. Run the Automated Test Suite
```bash
python -m pytest -v
# or
npm test
```
All **41 unit and integration tests** pass, validating database queries, Haversine math, departures, metro fares, trip planning, Web APIs, and MCP protocol compliance.

---

## Using with Claude Desktop

Add the server to your `claude_desktop_config.json` (`%APPDATA%\Claude\claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "pune-transit": {
      "command": "python",
      "args": [
        "-m",
        "src.server"
      ],
      "cwd": "C:/Users/LOQ/Downloads/mcp projecty"
    }
  }
}
```

Restart Claude Desktop, and ask:
- *"Which bus stops are near Pimpri station?"*
- *"When is the next bus from Shivajinagar to Hinjewadi?"*
- *"What is the metro fare from Vanaz to Ramwadi?"*
- *"Remember Hinjewadi Phase 1 as my office and plan my commute from Pimpri at 9 am."*

---

## Inspecting with MCP Inspector

Test tools interactively in the web UI:
```bash
npx @modelcontextprotocol/inspector python -m src.server
```

---

## Running the Remote Server (Streamable HTTP)

To launch the remote server with Bearer authentication and rate limiting:
```bash
python -m src.http_server
```
- Endpoint: `http://localhost:8000/mcp`
- Authentication header: `Authorization: Bearer demo-token-123`
- Tenant isolation: Tokens map automatically to user accounts (`local`, `user1`).

### Running via Docker
```bash
docker build -t pune-transit-mcp .
docker run -p 8000:8000 -e PORT=8000 pune-transit-mcp
```

---

## Error Handling Specifications

All errors return structured responses conforming to Section 5.3:

```json
{
  "error": true,
  "code": "AMBIGUOUS_PLACE",
  "message": "Multiple places matched 'Hinjewadi'.",
  "hint": "Ask the user to clarify which specific location or phase they meant.",
  "candidates": [
    {"name": "Hinjewadi Phase 1", "lat": 18.5912, "lon": 73.7389},
    {"name": "Hinjewadi Phase 2", "lat": 18.5982, "lon": 73.7185},
    {"name": "Hinjewadi Phase 3", "lat": 18.5775, "lon": 73.6892}
  ]
}
```

Error codes supported:
- `INVALID_INPUT`: Validation failure.
- `PLACE_NOT_FOUND`: Location could not be resolved.
- `AMBIGUOUS_PLACE`: Multiple locations match query; includes `candidates`.
- `NO_SERVICE`: No transit service at requested time.
- `NO_DATA`: Dataset missing or unreadable.
- `UNAUTHORIZED`: Invalid or missing Bearer token.
- `RATE_LIMITED`: Request cap exceeded.

---

## License

MIT License. See [LICENSE](./LICENSE) for details.
