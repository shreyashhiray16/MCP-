# Pune Transit MCP: Learning Log

## Phase 0: Foundations (11 October 2026)
1. **What I built/studied**:
   - The MCP specification, client-host-server architecture, JSON-RPC 2.0 lifecycle.
   - Flow of a tool call: Client `initialize` request -> Server response with capabilities -> Client `initialized` notification -> `tools/list` -> Model calls `tools/call` -> Tool handler response.
2. **What I learned about MCP**:
   - MCP defines three fundamental server primitives:
     - **Tools**: actions called dynamically by LLMs based on natural language queries.
     - **Resources**: contextual data loaded by user/host (read-only documents or templates).
     - **Prompts**: pre-engineered user prompts with arguments for guiding workflows.
   - Stdio transport uses stdout strictly for JSON-RPC messages; all diagnostic logging must go to stderr.
3. **What surprised me or broke**:
   - If anything prints to stdout, the JSON-RPC parser breaks immediately and Claude drops the connection.
4. **What I would do differently**:
   - Always set `logging.basicConfig(stream=sys.stderr)` before importing or running any MCP component.
5. **Open questions**:
   - How best to negotiate streaming vs batch responses in high-latency geocoding calls?

---

## Phase 1: Hello MCP (12 October 2026)
1. **What I built**:
   - Scaffolded the Python MCP project with `mcp` 2.x, Pydantic, and SQLite.
   - Built `resolve_place` with curated Pune landmarks.
   - Verified tool registration and schema exposure.
2. **What I learned about MCP**:
   - FastMCP in MCP 2.x is `MCPServer`, providing decorator-based tool and resource registration with automatic Pydantic argument type-checking and docstring-to-description mapping.
3. **What surprised me or broke**:
   - Migration from v1 `FastMCP` to v2 `MCPServer`.
4. **What I would do differently**:
   - Explicitly verify SDK version features and types early.
5. **Open questions**:
   - Does Claude Desktop prefer short or detailed tool descriptions? Detailed with explicit negative constraints works best.

---

## Phase 2: Bus Data (12 October 2026)
1. **What I built**:
   - `scripts/ingest_gtfs.py` loading PMPML GTFS into SQLite tables: `stops`, `routes`, `trips`, `stop_times`, `calendar`, `calendar_dates`.
   - Stored times as integer seconds since midnight (handling trips past midnight >= 86400s).
   - Built spatial indexes on `(stop_lat, stop_lon)` and time indexes on `(stop_id, departure_secs)`.
   - Services for `find_nearby_stops`, `next_departures` (IST calendar calculation), and `find_routes_between`.
2. **What I learned about MCP**:
   - Real-world transit datasets require robust validation and clear calendar handling. Returning `NO_SERVICE` with recovery hints prevents model hallucinations.
3. **What surprised me or broke**:
   - GTFS trips can run past midnight (e.g. 25:15:00). Storing them in seconds since midnight handles this cleanly.
4. **What I would do differently**:
   - Batch database inserts using transactions, which sped up ingestion by over 50x.
5. **Open questions**:
   - How to gracefully handle live bus tracking when feeds are unstable? (Timetable fallback).

---

## Phase 3: Places, Metro, Saved Places (12 October 2026)
1. **What I built**:
   - Curated `data/metro.json` with Purple Line (PCMC-Swargate) and Aqua Line (Vanaz-Ramwadi), stations, and official Maha-Metro fare slabs.
   - Pydantic schema validation for Metro data at startup.
   - `metro_info` tool for station info, line schedules, and fares.
   - `saved_places` SQLite table and tools `save_place` and `list_saved_places`.
2. **What I learned about MCP**:
   - Only `save_place` is a non-read-only tool; setting `annotations=ToolAnnotations(read_only=False)` accurately indicates mutability to clients.
3. **What surprised me or broke**:
   - Geocoding coordinates for "PCMC" vs "Pimpri Railway Station" differ by ~1.8 km. Adding exact metro station matching to the geocoding pipeline solved transit search accuracy.
4. **What I would do differently**:
   - Integrate transit station names directly into local alias dictionaries.
5. **Open questions**:
   - Multi-tenant saved places: pass authenticated `user_id` from remote headers.

---

## Phase 4: Trip Planning (12 October 2026)
1. **What I built**:
   - `plan_trip` multi-modal planner:
     - Direct bus routes with walking legs.
     - Direct metro routes with station connections.
     - 1-transfer connections via central hubs (Shivajinagar, Deccan, Civil Court) with 5-minute minimum buffer.
     - Walking time calculation (detour factor 1.3 / 4.5 km/h) and road comparison (1.4 detour factor / 25 km/h).
     - Ranking by total duration, transfers, and walking distance.
2. **What I learned about MCP**:
   - Multi-leg trips can be complex. Summarizing itineraries with leg-by-leg details enables Claude to explain travel trade-offs to users clearly.
3. **What surprised me or broke**:
   - Walking distances in dense Indian cities require detour multipliers (1.3x) rather than straight-line approximations.
4. **What I would do differently**:
   - Benchmark SQL joins using `EXPLAIN QUERY PLAN` to ensure index coverage.
5. **Open questions**:
   - Real-time GTFS-RT delays: can be added in Phase 8.

---

## Phase 5: Resources and Prompts (12 October 2026)
1. **What I built**:
   - Registered 4 MCP Resources:
     - `transit://pune/routes`
     - `transit://pune/stops/{stop_id}`
     - `transit://pune/metro`
     - `transit://user/places`
   - Registered 2 MCP Prompts:
     - `morning_commute`: guides model to plan between saved places.
     - `explore_area`: guides model to summarize transit in a Pune neighborhood.
2. **What I learned about MCP**:
   - The distinction between MCP primitives:
     - Tools are invoked by the model autonomously when planning actions.
     - Resources are documents attached by the user/host as background context.
     - Prompts are user-facing reusable templates that structure agent behavior.
3. **What surprised me or broke**:
   - MCPServer dynamically binds URI template parameters (e.g. `{stop_id}`) to python arguments cleanly.
4. **What I would do differently**:
   - Ensure resource payloads return valid JSON strings with `application/json` mime type.
5. **Open questions**:
   - How Claude Desktop displays resource attachments in the UI.

---

## Phase 6: Quality, Security and Hardening (12 October 2026)
1. **What I built**:
   - Standardized error model: `code`, `message`, `hint`, and `details`.
   - 35 automated tests covering unit, integration, and model behavior benchmark scenarios.
   - Hardened parameter validation and SQL parameterization.
2. **What I learned about MCP**:
   - Negative instructions in tool descriptions prevent hallucinations when transit data is missing.
3. **What surprised me or broke**:
   - Async testing in pytest requires `pytest-asyncio`.
4. **What I would do differently**:
   - Include acceptance test scenarios directly in continuous testing.
5. **Open questions**:
   - Rate limiting thresholds for public remote servers.

---

## Phase 7: Remote Server (12 October 2026)
1. **What I built**:
   - `src/http_server.py`: Streamable HTTP server on `/mcp`.
   - Bearer-token authentication using `secrets.compare_digest`.
   - Tenant isolation: token maps to `userId` for `saved_places`.
   - Rate limiting (sliding window per token) and CORS middleware.
   - Dockerfile for production containerization.
2. **What I learned about MCP**:
   - Streamable HTTP allows remote MCP servers over HTTPS with standard web infrastructure and reverse proxies.
3. **What surprised me or broke**:
   - Remote servers must return 401 cleanly with no leaky internal details.
4. **What I would do differently**:
   - Use environment variables for rotating secret tokens.
5. **Open questions**:
   - Standardizing OAuth 2.0 with the evolving MCP Auth specification.
