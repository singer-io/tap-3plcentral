import singer
from singer.catalog import Catalog, CatalogEntry, Schema
from tap_3plcentral.schema import get_schemas, STREAMS
from tap_3plcentral.client import TPLAPIError

LOGGER = singer.get_logger()

DISCOVERY_PROBE_PATHS = {
    'stock_summaries': 'inventory/stocksummaries',
    'locations': 'inventory/facilities/{facility_id}/locations',
}


def _get_probe_resource_path(stream_name, facility_id=None):
    resource_path_template = DISCOVERY_PROBE_PATHS.get(stream_name, stream_name)
    if '{facility_id}' in resource_path_template:
        if facility_id:
            return resource_path_template.format(facility_id=facility_id)
        LOGGER.warning(
            "No facility_id provided for stream '%s' access probe. Falling back to stream name path.",
            stream_name,
        )
        return stream_name
    return resource_path_template


def check_stream_access(client, stream_name, facility_id=None) -> bool:
    """Probe a top-level stream endpoint (pgsiz=1) to verify credentials have read access.

    Returns True if accessible, False on 401/403/404 (TPLAPIError with those codes).
    Any other exception is re-raised.
    Should only be called for top-level streams (those without a 'parent' key).
    """
    # Use stream-specific resource path for a minimal GET.
    # pgsiz=1 minimizes the response payload.
    resource_path = _get_probe_resource_path(stream_name, facility_id=facility_id)
    querystring = 'pgsiz=1'
    LOGGER.info("Checking access for stream '%s'", stream_name)
    try:
        client.get(
            resource_path=resource_path,
            querystring=querystring,
            endpoint=stream_name,
        )
        return True
    except TPLAPIError as ex:
        if ex.error_code in (401, 403, 404):
            LOGGER.warning(
                "Excluding unauthorized stream '%s' from catalog. HTTP-Error-Message: '%s'",
                stream_name,
                str(ex)
            )
            return False
        raise


def _prune_inaccessible_children(schemas: dict, field_metadata: dict) -> None:
    """Remove child streams from the catalog whose parent stream was excluded.

    Mutates schemas and field_metadata in place.
    """
    for stream_name, stream_config in list(STREAMS.items()):
        parent = stream_config.get('parent')
        if stream_name in schemas and parent and parent not in schemas:
            LOGGER.warning(
                "Stream '%s' excluded from catalog because its parent stream '%s' is not accessible.",
                stream_name,
                parent,
            )
            schemas.pop(stream_name, None)
            field_metadata.pop(stream_name, None)


def _apply_access_checks(client, schemas: dict, field_metadata: dict, facility_id=None) -> None:
    """Probe each top-level stream for read access and remove inaccessible streams
    (and their children) from schemas and field_metadata in place.

    Child streams are skipped during probing — their removal is handled separately
    by _prune_inaccessible_children().
    Raises TPLAPIError if no top-level streams remain accessible.
    """
    inaccessible_streams = [
        stream_name
        for stream_name, stream_config in STREAMS.items()
        if stream_name in schemas
        and not stream_config.get('parent')
        and not check_stream_access(client, stream_name, facility_id=facility_id)
    ]

    for stream_name in inaccessible_streams:
        schemas.pop(stream_name, None)
        field_metadata.pop(stream_name, None)

    _prune_inaccessible_children(schemas, field_metadata)

    if inaccessible_streams:
        accessible_top_level = sum(
            1 for name in schemas
            if not STREAMS.get(name, {}).get('parent')
        )
        if accessible_top_level == 0:
            raise TPLAPIError(
                "HTTP-error-code: 403, Error: The account credentials supplied do not have 'read' access to any "
                "of the streams supported by the tap. Data collection cannot be initiated due to lack of permissions.",
                error_code=403,
            )
        LOGGER.warning(
            "The account credentials supplied do not have 'read' access to the following stream(s): %s. "
            "These streams have been excluded from the catalog.",
            ", ".join(inaccessible_streams),
        )


def discover(client, config=None) -> Catalog:
    """Run discovery and exclude streams the credentials cannot read.

    Access to each top-level stream is verified via check_stream_access().
    Inaccessible streams are removed from the returned catalog.
    Child streams are excluded when their parent stream is inaccessible.
    """
    schemas, field_metadata = get_schemas()
    facility_id = config.get('facility_id') if config else None
    _apply_access_checks(client, schemas, field_metadata, facility_id=facility_id)

    catalog = Catalog([])

    for stream_name, schema_dict in schemas.items():
        schema = Schema.from_dict(schema_dict)
        mdata = field_metadata[stream_name]

        catalog.streams.append(CatalogEntry(
            stream=stream_name,
            tap_stream_id=stream_name,
            key_properties=STREAMS[stream_name]['key_properties'],
            schema=schema,
            metadata=mdata
        ))

    return catalog
