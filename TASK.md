# Spatial Bike-Share GraphQL Sandbox

## Objective

Build a training project that ingests a useful subset of the public NYC Citi Bike dataset into PostgreSQL with PostGIS and exposes two spatial/time-series features through a Node.js GraphQL API.

The finished repository must contain:

1. a reproducible Meltano ingestion project;
2. a PostGIS schema with spatial, time-series, and relational tables;
3. a Node.js GraphQL backend implementing the two features below;
4. integration tests that execute GraphQL requests against a real PostGIS database;
5. documentation explaining setup, ingestion, development, and testing.

Optimize for a small, understandable backend system that demonstrates sound spatial querying, relational modeling, and test design. The first release covers one month of historical trips and the reference data needed by the API.

## Data sources

Use the official [Citi Bike System Data](https://citibikenyc.com/system-data).

For the initial implementation, ingest one complete recent month of trip-history data. The pipeline should allow a different month to be selected through configuration without code changes.

The trip data includes:

- ride ID and rideable type;
- start and end timestamps;
- start and end station IDs and names;
- start and end coordinates;
- member or casual rider type.

Use the Citi Bike GBFS `station_information` feed as the canonical source for the current station catalog. It supplies stable station IDs, names, coordinates, and capacity metadata. Capture it once per ingestion run as reference data; continuous station-status collection is reserved for a later version.

Historical trips may refer to a station that is absent from the current GBFS snapshot because stations can be renamed, moved, or retired. Reconcile such references by creating a station record from the most recent valid endpoint metadata in the selected trip archive. Record each station's provenance so consumers can distinguish `GBFS` records from `TRIP_DERIVED` fallback records.

Also ingest an NYC neighborhood-boundary dataset from an official NYC Open Data source. Record the selected dataset URL and version in the README. A simplified fixture containing a few polygons may be used by tests, but production ingestion must support the real boundary dataset.

The first version uses the GBFS station catalog as reference data and the historical trip archive as its time-series data source. Continuous ingestion of GBFS station availability belongs to a future extension.

## Suggested technology choices

- Node.js 22 or newer
- TypeScript
- GraphQL server framework of your choice
- PostgreSQL 16 or newer with PostGIS 3
- Meltano for orchestration and ingestion
- SQL migrations managed by a migration tool of your choice
- Vitest or Node's built-in test runner
- Testcontainers for integration tests
- Docker Compose for local PostgreSQL/PostGIS

Equivalent choices are acceptable, but document deviations and their reasons.

## Repository layout

Use a structure similar to:

```text
.
├── backend/
│   ├── src/
│   ├── migrations/
│   └── test/
├── meltano/
│   ├── meltano.yml
│   ├── plugins/
│   └── transform/
├── docker-compose.yml
├── .env.example
└── README.md
```

The exact layout may differ if the responsibilities remain clear.

## Meltano ingestion

Create a Meltano project that can perform the complete load with one documented command.

The pipeline must:

1. accept a year and month as configuration;
2. download or extract the corresponding Citi Bike archive;
3. load trip rows into a staging table;
4. load a snapshot of the GBFS `station_information` feed into a staging table;
5. ingest neighborhood boundaries into a staging table;
6. normalize and upsert the GBFS station catalog;
7. reconcile trip endpoints and create provenance-marked fallback stations for historical IDs absent from GBFS;
8. load trips with foreign keys to the normalized stations;
9. create or update PostGIS geometries in SRID 4326;
10. produce the same domain records when a completed ingestion is rerun;
11. quarantine malformed rows with a reason and source-row reference;
12. report source, accepted, fallback, quarantined, inserted, and updated row counts at the end of a run.

Using Meltano utilities or dbt-postgres for download and transformation steps is acceptable. Keep raw source fields in staging tables and perform type conversion and geometry creation in explicit transformation steps.

Configuration and credentials must come from environment variables. Commit an `.env.example` containing safe placeholders.

## Database model

At minimum, implement these tables.

### `neighborhoods`

```text
id                  primary key
external_id         unique source identifier
name
borough
boundary            geometry(MultiPolygon, 4326)
```

### `stations`

```text
id                  primary key
external_id         unique Citi Bike station ID
name
location            geometry(Point, 4326)
capacity            nullable integer
source              enum: GBFS or TRIP_DERIVED
neighborhood_id     nullable foreign key -> neighborhoods.id
```

Assign `neighborhood_id` with a PostGIS point-in-polygon join during transformation. Represent stations beyond the imported boundaries with a null neighborhood.

### `trips`

```text
id                  primary key
external_id         unique ride ID
started_at          timestamptz
ended_at            timestamptz
start_station_id    foreign key -> stations.id
end_station_id      foreign key -> stations.id
rideable_type
rider_type
```

Add constraints for valid trip duration and rider type. Decide and document how trips with missing stations are handled.

### Required indexes

- GiST indexes on `stations.location` and `neighborhoods.boundary`;
- B-tree indexes on `trips.started_at` and `trips.ended_at`;
- indexes supporting both station foreign keys combined with time filtering;
- uniqueness indexes used by idempotent ingestion.

Use `geometry`, rather than `geography`, as the stored type. Cast to `geography` when a query needs distances in meters. This keeps containment operations straightforward while making distance units explicit.

## GraphQL feature 1: Area mobility summary

Return mobility statistics for an arbitrary user-supplied polygon and time interval.

Example operation:

```graphql
query AreaMobility($input: AreaMobilityInput!) {
  areaMobility(input: $input) {
    stationCount
    departures
    arrivals
    internalTrips
    outboundTrips
    inboundTrips
    averageTripDurationSeconds
    busiestStations {
      station { id name neighborhood { name borough } }
      departures
      arrivals
    }
    topOutboundDestinations {
      neighborhood { id name borough }
      tripCount
    }
  }
}
```

Input fields:

- a GeoJSON `Polygon` or `MultiPolygon`;
- `from` and `to` timestamps;
- optional rider type;
- optional limit for ranked results, with a safe maximum.

Required behavior:

- validate GeoJSON type, coordinate ranges, polygon validity, and maximum complexity;
- find stations inside the supplied area using PostGIS;
- classify trips as internal, inbound, or outbound by joining both trip station references;
- group outbound destinations by the destination station's neighborhood;
- return zero-valued metrics for a valid area with no matching trips;
- use half-open time intervals: `started_at >= from AND started_at < to`.

Implement this feature primarily as database aggregation, returning only the aggregated result set to Node.js.

## GraphQL feature 2: Nearby station imbalance

Rank stations near a point by the difference between arrivals and departures during a time interval. This approximates where bike redistribution may have been needed.

Example operation:

```graphql
query NearbyImbalance($input: NearbyImbalanceInput!) {
  nearbyStationImbalance(input: $input) {
    station {
      id
      name
      neighborhood { id name borough }
    }
    distanceMeters
    departures
    arrivals
    netFlow
    imbalanceScore
  }
}
```

Input fields:

- longitude and latitude;
- radius in meters;
- `from` and `to` timestamps;
- optional minimum trip count;
- sort direction: most depleted or most accumulated;
- result limit, with a safe maximum.

Required behavior:

- use `ST_DWithin` to select candidate stations and `ST_Distance` for the returned distance;
- join trips separately through `start_station_id` and `end_station_id` without producing a departure-by-arrival row multiplication;
- calculate `netFlow = arrivals - departures`;
- define and document a normalized `imbalanceScore` that remains meaningful across low- and high-volume stations;
- include neighborhood information through the station relationship;
- return stations with activity on only one side of the calculation;
- use deterministic ordering when scores tie.

A suitable initial score is:

```text
imbalanceScore = (arrivals - departures) / sqrt(arrivals + departures)
```

Handle the zero-trip case explicitly.

## GraphQL and API requirements

- Publish a schema with descriptions for non-obvious fields and units.
- Use a custom scalar or a clearly documented input object for GeoJSON.
- Return opaque GraphQL IDs rather than exposing assumptions about database keys.
- Validate dates, ranges, radii, limits, and geometry before executing SQL.
- Bind every user-provided geometry and filter value through parameterized SQL or a query builder.
- Map expected validation failures to useful GraphQL errors without exposing SQL or credentials.
- Resolve stations and neighborhoods with bounded queries, joins, or request-scoped batching.
- Provide a health endpoint that checks database connectivity.

Reasonable input limits should be configurable. Suggested defaults are a 31-day maximum time range, a 20-kilometer maximum radius, and a maximum of 100 returned stations.

## Integration tests

Integration tests must start an isolated PostgreSQL/PostGIS instance, apply the real migrations, insert a small deterministic dataset, start or invoke the real GraphQL application, and execute GraphQL operations through its HTTP interface.

Exercise the production database adapter and native PostGIS functions in these tests.

Create fixtures with:

- at least two adjacent neighborhood polygons;
- stations inside each polygon;
- a station close to a polygon boundary;
- a station outside all neighborhoods;
- internal, inbound, outbound, and cross-neighborhood trips;
- trips exactly before, at, and after time boundaries;
- a station with departures but no arrivals;
- a station with arrivals but no departures;
- trips outside the search radius.

At minimum, test:

### Area mobility

1. correct internal, inbound, and outbound classification;
2. correct point-in-polygon behavior near a boundary;
3. destination grouping through station and neighborhood joins;
4. rider-type filtering;
5. half-open time-window behavior;
6. a valid polygon with no activity;
7. rejection of invalid, unsupported, or excessively complex geometry;
8. rejection of an excessive time range.

### Nearby imbalance

1. radius filtering in meters;
2. correct arrival and departure counts without join multiplication;
3. inclusion of one-sided station activity;
4. score and net-flow calculation;
5. sorting for depleted and accumulated modes;
6. minimum-trip filtering and limiting;
7. deterministic ordering for ties;
8. rejection of invalid coordinates, radius, or timestamps.

Also include:

- a health-check test;
- a test that GraphQL variables resembling SQL injection remain data and cause no schema damage;
- a test proving migrations can initialize an empty database;
- cleanup that leaves no containers or persistent test data behind.

The tests should assert both GraphQL response values and the absence or expected shape of GraphQL errors.

## Documentation requirements

The README must explain:

- prerequisites;
- environment variables;
- how to start PostGIS;
- how to run migrations;
- how to ingest a selected month;
- how to start the backend;
- how to run unit and integration tests;
- example GraphQL operations;
- data-source attribution and any applicable usage terms;
- important modeling decisions and known limitations.

Include a small architecture diagram, which may be Mermaid:

```text
Citi Bike archive ─┐
                   ├─> Meltano ─> staging ─> transforms ─> PostGIS
Neighborhood data ─┘                                  │
                                                     ▼
                                             Node.js GraphQL API
                                                     │
                                                     ▼
                                             integration tests
```

## Out of scope

- frontend or map rendering;
- authentication and user accounts;
- real-time GBFS ingestion;
- prediction or machine-learning models;
- ingestion of the complete Citi Bike history;
- production deployment or cloud infrastructure.

## Definition of done

The project is complete when a new developer can clone the repository and, using only documented commands:

1. start PostGIS;
2. ingest a configured month of Citi Bike trips and the neighborhood boundaries;
3. start the GraphQL API;
4. successfully execute both feature queries against the ingested data;
5. run the complete automated test suite against an isolated PostGIS instance;
6. rerun ingestion and observe no duplicate domain records.

All linting, type checking, migrations, and tests must pass in CI.
