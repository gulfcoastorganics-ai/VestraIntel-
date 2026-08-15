# v1.4 source / protocol validation — 2026-08-14

This release validates the fingerprint families against current primary documentation.

## CKAN

Primary documentation: CKAN API Guide.

Validated behavior:

- Action API version 3 is the current Action API;
- read-only GET actions include `package_search`;
- CKAN documents recently changed package activity as an API capability.

Implementation consequence: FIA uses the versioned `/api/3/action/...` path and a low-impact `status_show` GET as a technology fingerprint.

## Socrata / SODA

Primary documentation: Socrata Developer documentation.

Validated behavior:

- Socrata describes a global catalog/discovery capability;
- every Socrata dataset exposes a SODA API;
- current SODA3 data-query endpoints use `/api/v3/views/{identifier}/query.json`;
- current SODA3 query requests require either user authentication or a valid application token.

Implementation consequence: v1.4 fingerprints Socrata passively and records the credential requirement instead of issuing an unauthenticated SODA3 query merely to detect the platform.

## ArcGIS Hub / Portal

Primary documentation: Esri ArcGIS REST API and ArcGIS Hub Search API.

Validated behavior:

- Portal content can be searched with the REST `/sharing/rest/search` operation;
- ArcGIS Hub exposes a catalog Search API conforming to OGC API Records concepts;
- public Hub content can be explored/downloaded without an account when the item is public.

Implementation consequence: FIA uses public read-only search/landing probes only.

## DCAT 3

Primary documentation: W3C Data Catalog Vocabulary (DCAT) Version 3, Recommendation 22 August 2024.

Validated behavior:

- DCAT is designed to make catalogs, datasets, distributions and data services interoperable and aggregatable;
- DCAT metadata can be serialized in RDF formats including RDF/XML, Turtle and JSON-LD;
- DCAT explicitly supports decentralized/federated dataset discovery.

Implementation consequence: FIA recognizes advertised RDF/DCAT metadata as a connector-worthy catalog surface without assuming one fixed URL convention.

## SPARQL

Primary documentation: W3C SPARQL Protocol.

Validated behavior:

- SPARQL defines an HTTP query operation and a separate update operation;
- query operations can be sent with HTTP GET or POST;
- structured result formats include SPARQL JSON results.

Implementation consequence: FIA implements only a bounded read-only SELECT fingerprint and explicitly records `update_operations_allowed=false`.

## Atom

Primary documentation: RFC 4287.

Validated behavior:

- Atom defines feed documents and `link` elements;
- a feed commonly identifies itself with a `rel=self` link and `application/atom+xml` content.

Implementation consequence: FIA treats advertised Atom/RSS-style feeds as change-monitor surfaces, not as proof of a general dataset API.

## Generic bulk downloads

There is no single universal bulk-download portal standard. v1.4 therefore uses a transparent heuristic only when a public page advertises multiple machine-readable file URLs. The generated proposal remains analyst-review-only.

## Non-goals

The release does not:

- search credentials;
- circumvent authentication;
- crawl private portals;
- submit SPARQL updates;
- make unrestricted-use assumptions based solely on public accessibility;
- activate discovered connectors automatically.
