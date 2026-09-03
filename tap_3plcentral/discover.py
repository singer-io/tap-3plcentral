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
    """Probe top-level stream read access with a minimal request; return False only on 403.

    401 is re-raised (invalid credentials, not a per-stream permission issue).
    """
    # Use stream-specific resource path for a minimal GET.
    # pgsiz=1 minimizes the response payload.
    resource_path = _get_probe_resource_path(stream_name, facility_id=facility_id)
    query_string = 'pgsiz=1'
    try:
        client.get(
            resource_path=resource_path,
            querystring=query_string,
            endpoint=stream_name,
        )
        return True
    except TPLAPIError as ex:
        if ex.error_code == 403:
            LOGGER.warning(
                "Unauthorized Stream: %s, excluding from catalog. HTTP-Error-Message:'%s'",
                stream_name,
                ex.tpl_error_msg,
            )
            return False
        raise


def _prune_inaccessible_children(schemas: dict, field_metadata: dict) -> None:
    """Remove child streams from the catalog whose parent stream was excluded.

    Mutates schemas and field_metadata in place.
    """
    to_remove = []
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
            to_remove.append(stream_name)
    return to_remove


def _apply_access_checks(client, schemas: dict, field_metadata: dict, facility_id=None) -> None:
    """Probe each top-level stream for read access and remove inaccessible streams
    (and their children) from schemas and field_metadata in place.

    Child streams are skipped during probing — their removal is handled separately
    by _prune_inaccessible_children().
    Fails fast with TPLAPIError on the first 401 (invalid credentials), and raises
    TPLAPIError if no top-level streams remain accessible after 403 exclusions.
    """
    inaccessible_streams = []
    for stream_name, stream_config in STREAMS.items():
        if stream_name not in schemas or stream_config.get('parent'):
            continue
        try:
            accessible = check_stream_access(client, stream_name, facility_id=facility_id)
        except TPLAPIError as ex:
            if ex.error_code == 401:
                raise TPLAPIError(
                    "Invalid credentials. Authentication failed while probing "
                    f"stream '{stream_name}'.",
                    error_code=401,
                    tpl_error_msg=ex.tpl_error_msg,
                ) from ex
            raise
        if not accessible:
            inaccessible_streams.append(stream_name)

    for stream_name in inaccessible_streams:
        schemas.pop(stream_name, None)
        field_metadata.pop(stream_name, None)

    inaccessible_children = _prune_inaccessible_children(schemas, field_metadata)
    inaccessible_streams.extend(inaccessible_children)

    accessible_streams = [s for s in STREAMS if s in schemas]

    if not accessible_streams:
        raise TPLAPIError(
            "No streams are accessible. Ensure the credentials have 'read' access "
            "to at least one supported stream.",
            error_code=403,
        )
    if inaccessible_streams:
        LOGGER.warning(
            "Unauthorized streams excluded from catalog: %s",
            ", ".join(sorted(set(inaccessible_streams))),
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
