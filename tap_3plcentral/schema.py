import os
import json
from singer import metadata

# Reference: https://github.com/singer-io/getting-started/blob/master/docs/DISCOVERY_MODE.md#Metadata
STREAMS = {
    'customers': {
        'key_properties': ['customer_id'],
        'replication_method': 'FULL_TABLE'
    },
    'sku_items': {
        'key_properties': ['item_id'],
        'replication_method': 'INCREMENTAL',
        'replication_keys': ['last_modified_date']
    },
    'stock_details': {
        'key_properties': ['receive_item_id'],
        'replication_method': 'FULL_TABLE'
    },
    'stock_summaries': {
        'key_properties': ['facility_id', 'item_id'],
        'replication_method': 'FULL_TABLE'
    },
    'locations': {
        'key_properties': ['facility_id', 'location_id'],
        'replication_method': 'FULL_TABLE'
    },
    'inventory': {
        'key_properties': ['receive_item_id'],
        'replication_method': 'FULL_TABLE'
    },
    'orders': {
        'key_properties': ['order_id'],
        'replication_method': 'INCREMENTAL',
        'replication_keys': ['last_modified_date']
    }
}


def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)

def get_schemas():
    schemas = {}
    field_metadata = {}

    for stream_name, stream_metadata in STREAMS.items():
        schema_path = get_abs_path('schemas/{}.json'.format(stream_name))
        with open(schema_path) as file:
            schema = json.load(file)
        schemas[stream_name] = schema
        mdata = metadata.new()

        # Documentation: https://github.com/singer-io/getting-started/blob/master/docs/DISCOVERY_MODE.md#singer-python-helper-functions
        # Reference: https://github.com/singer-io/singer-python/blob/master/singer/metadata.py#L25-L44
        mdata = metadata.get_standard_metadata(
            schema=schema,
            key_properties=stream_metadata.get('key_properties', None),
            valid_replication_keys=stream_metadata.get('replication_keys', None),
            replication_method=stream_metadata.get('replication_method', None)
        )
        field_metadata[stream_name] = mdata

    return schemas, field_metadata
