# Pune Transit Data Sources Catalog

*Last updated: 12 October 2026*

This document tracks all external and internal transit data sources used by the Pune Transit MCP Server, including licenses, freshness, caveats, and spot-checks.

---

## 1. PMPML Bus Data (Static GTFS)
- **Source**: PMPML Open Transit Community dataset / Crola FOSS United
- **URL**: `https://fossunited.org/grants/directory/crola`
- **Format**: Standard GTFS (CSV files: `agency.txt`, `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, `calendar.txt`, `calendar_dates.txt`)
- **License**: Open Data / Community Open License
- **Coverage**: Pune Municipal Corporation (PMC) and Pimpri-Chinchwad Municipal Corporation (PCMC)
- **Ingestion**: Parsed via `scripts/ingest_gtfs.py` into SQLite `data/pune_transit.db`.
- **Spot-Check Results**:
  - Route 348 (Pimpri to Hinjewadi Phase 3): Confirmed stops and frequency match ground timetable.
  - Route 100 (Shivajinagar to Hinjewadi Phase 3 via Aundh/Wakad): Confirmed peak morning departures.
  - Route 42 (Katraj to Pimpri via Swargate/Shivajinagar): Confirmed stops order.

---

## 2. Pune Metro (Maha-Metro)
- **Source**: Maharashtra Metro Rail Corporation Ltd (Pune Metro Rail Project)
- **URL**: `https://www.punemetrorail.org`
- **Format**: Hand-curated JSON verified against official operational schedules (`data/metro.json`)
- **Verified Date**: 11 October 2026
- **Network Coverage**:
  - **Purple Line (Line 1)**: PCMC to Swargate (14 stations: PCMC, Sant Tukaram Nagar, Bhosari, Kasarwadi, Phugewadi, Dapodi, Bopodi, Khadki, Range Hill, Shivajinagar, Civil Court, Budhwar Peth, Mandai, Swargate).
  - **Aqua Line (Line 2)**: Vanaz to Ramwadi (16 stations: Vanaz, Anand Nagar, Ideal Colony, Nal Stop, Garware College, Deccan Gymkhana, Sambhaji Udyan, PMC, Civil Court, Mangalwar Peth, Pune Railway Station, Ruby Hall Clinic, Bund Garden, Kalyani Nagar, Ramwadi).
  - **Interchange**: Civil Court multi-modal hub.
  - **Operating Timings**: 06:00 AM to 10:00 PM IST daily.
  - **Fares**: Tiered ₹10, ₹15, ₹20, ₹25, ₹30, ₹35 slabs.

---

## 3. Geocoding and Place Resolution
- **Primary Source**: Local curated Pune dataset (`data/pune_places.json`) covering 20+ prominent landmarks, IT parks, colleges, and transportation hubs.
- **Secondary Source**: OpenStreetMap Nominatim with viewbox bounding box: `viewbox=73.65,18.75,74.05,18.40`
- **Rate Limit & Policy**: Compliant with OSM Nominatim Usage Policy (max 1 req/sec, descriptive User-Agent, in-memory LRU caching).
- **Attribution**: "Data © OpenStreetMap contributors".

---

## 4. Live Vehicle Tracking (GTFS-RT) [Phase 8 - Stretch]
- **Source**: Experimental PMPML GTFS-RT feed (`https://pmpml-rt.blrtransit.com/`)
- **Status**: Optional / Experimental. The server defaults to static timetables when live feeds are unavailable.
