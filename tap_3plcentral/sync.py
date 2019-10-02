from datetime import datetime
import math
import singer
from singer import metrics, metadata, Transformer, utils
from tap_3plcentral.transform import transform_json, convert

LOGGER = singer.get_logger()


def write_schema(catalog, stream_name):
    stream = catalog.get_stream(stream_name)
    schema = stream.schema.to_dict()
    try:
        singer.write_schema(stream_name, schema, stream.key_properties)
    except OSError as err:
        LOGGER.info('OS Error writing schema for: {}'.format(stream_name))
        raise err


def write_record(stream_name, record, time_extracted):
    try:
        singer.write_record(stream_name, record, time_extracted=time_extracted)
    except OSError as err:
        LOGGER.info('OS Error writing record for: {}'.format(stream_name))
        LOGGER.info('record: {}'.format(record))
        raise err


def get_bookmark(state, stream, default):
    if (state is None) or ('bookmarks' not in state):
        return default
    return (
        state
        .get('bookmarks', {})
        .get(stream, default)
    )


def write_bookmark(state, stream, value):
    if 'bookmarks' not in state:
        state['bookmarks'] = {}
    state['bookmarks'][stream] = value
    LOGGER.info('Write state for stream: {}, value: {}'.format(stream, value))
    singer.write_state(state)


def process_records(catalog, #pylint: disable=too-many-branches
                    stream_name,
                    records,
                    time_extracted,
                    bookmark_field=None,
                    bookmark_type=None,
                    max_bookmark_value=None,
                    last_datetime=None,
                    last_integer=None,
                    parent=None,
                    parent_id=None):
    stream = catalog.get_stream(stream_name)
    schema = stream.schema.to_dict()
    stream_metadata = metadata.to_map(stream.metadata)

    with metrics.record_counter(stream_name) as counter:
        for record in records:
            # If child object, add parent_id to record
            if parent_id and parent:
                record[parent + '_id'] = parent_id

            # Transform record for Singer.io
            with Transformer() as transformer:
                transformed_record = transformer.transform(record,
                                               schema,
                                               stream_metadata)

                # Reset max_bookmark_value to new value if higher
                if bookmark_field and (bookmark_field in transformed_record):
                    if (max_bookmark_value is None) or \
                        (transformed_record[bookmark_field] > max_bookmark_value):
                        max_bookmark_value = transformed_record[bookmark_field]

                if bookmark_field:
                    if bookmark_field in transformed_record:
                        if bookmark_type == 'integer':
                            # Keep only records whose bookmark is after the last_integer
                            if transformed_record[bookmark_field] >= last_integer:
                                write_record(stream_name, transformed_record, time_extracted=time_extracted)
                                counter.increment()
                        elif bookmark_type == 'datetime':
                            last_dttm = transformer._transform_datetime(last_datetime)
                            bookmark_dttm = transformer._transform_datetime(transformed_record[bookmark_field])
                            # Keep only records whose bookmark is after the last_datetime
                            if bookmark_dttm >= last_dttm:
                                write_record(stream_name, transformed_record, time_extracted=time_extracted)
                                counter.increment()
                else:
                    write_record(stream_name, transformed_record, time_extracted=time_extracted)
                    counter.increment()

        return max_bookmark_value, counter.value


# Sync a specific parent or child endpoint.
def sync_endpoint(client, #pylint: disable=too-many-branches
                  catalog,
                  state,
                  start_date,
                  stream_name,
                  path,
                  endpoint_config,
                  data_key,
                  static_params,
                  bookmark_query_field=None,
                  bookmark_field=None,
                  bookmark_type=None,
                  id_fields=None,
                  parent=None,
                  parent_id=None):

    # Get the latest bookmark for the stream and set the last_integer/datetime
    last_datetime = None
    last_integer = None
    max_bookmark_value = None
    if bookmark_type == 'integer':
        last_integer = get_bookmark(state, stream_name, 0)
        max_bookmark_value = last_integer
    else:
        last_datetime = get_bookmark(state, stream_name, start_date)
        max_bookmark_value = last_datetime

    write_schema(catalog, stream_name)

    # pagination: loop thru all pages of data
    # Each page has an pgnum (page number) and a 
    #   pgsiz (page size from the endpoint = batch size, number of records)
    # Loop through pages, increase the "pgnum" by 1 for each "pgsiz" batch of records.
    # Continue until the "offset" exceeds the total_records.

    page = 1
    total_pages = 1  # initial value, set with first API call
    total_records = 0 # total number of result records (across all batches)
    while page <= total_pages:
        params = {
            'pgnum': page,
            **static_params # adds in endpoint specific, sort, filter params
        }

        if 'pgsiz' in params:
            page_size = params['pgsiz']
        else:
            page_size = 100

        # Resource Query Language (RQL) is used to filter data. Reference: http://api.3plcentral.com/rels/rql
        if bookmark_query_field:
            if 'rql' in params:
                if bookmark_type == 'datetime':
                    params['rql'] = '{};{}=ge={}'.format(params['rql'], bookmark_query_field, last_datetime)
                elif bookmark_type == 'integer':
                    params['rql'] = '{};{}=ge={}'.format(params['rql'], bookmark_query_field, last_integer)
            else:
                if bookmark_type == 'datetime':
                    params['rql'] = '{}=ge={}'.format(bookmark_query_field, last_datetime)
                elif bookmark_type == 'integer':
                    params['rql'] = '{}=ge={}'.format(bookmark_query_field, last_integer)

        LOGGER.info('{} - Sync start'.format(
            stream_name,
            'since: {}, '.format(last_datetime) if bookmark_query_field else ''))

        # Squash params to query-string params
        querystring = '&'.join(['%s=%s' % (key, value) for (key, value) in params.items()])

        # Get data, API request
        data = client.get(
            path,
            querystring=querystring,
            endpoint=stream_name)
        # time_extracted: datetime when the data was extracted from the API
        time_extracted = utils.now()
        if not data or data is None or data == []:
            break # No data results

        # Transform raw data with transform_json from transform.py
        if data_key is None:
            transformed_data = transform_json(data, stream_name, 'ResourceList')[convert(
                'ResourceList')]
        elif data_key in data:
            transformed_data = transform_json(data, stream_name, data_key)[convert(data_key)]
        # LOGGER.info('transformed_data = {}'.format(transformed_data))
        # If transformed_data is a single-record dict, add it to a list
        if isinstance(transformed_data, dict):
            # rec_ids = {}
            tdata = []
            tdata.append(transformed_data)
            transformed_data = tdata
        if not transformed_data or transformed_data is None:
            break # No data results

        # Process records and get the max_bookmark_value and record_count for the set of records
        max_bookmark_value, record_count = process_records(
            catalog=catalog,
            stream_name=stream_name,
            records=transformed_data,
            time_extracted=time_extracted,
            bookmark_field=bookmark_field,
            bookmark_type=bookmark_type,
            max_bookmark_value=max_bookmark_value,
            last_datetime=last_datetime,
            last_integer=last_integer,
            parent=parent,
            parent_id=parent_id)

        # set page and total_pages for pagination
        if 'TotalResults' in data:
            total_records = data['TotalResults']
            if total_records < page_size:
                total_pages = 1
            else:
                total_pages = math.ceil(total_records / page_size)
        else:
            total_pages = 1
            total_records = record_count

        # Loop thru parent batch records for each children objects (if should stream)
        children = endpoint_config.get('children')
        if children:
            for child_stream_name, child_endpoint_config in children.items():
                should_stream, last_stream_child = should_sync_stream(get_selected_streams(catalog),
                                                            None,
                                                            child_stream_name)
                if should_stream:
                    # For each parent record
                    for record in transformed_data:
                        i = 0
                        # Set parent_id
                        for id_field in id_fields:
                            if i == 0:
                                parent_id_field = id_field
                            if id_field == 'id':
                                parent_id_field = id_field
                            i = i + 1
                        parent_id = record.get(parent_id_field)

                        # sync_endpoint for child
                        LOGGER.info('Syncing: {}, parent_stream: {}, parent_id: {}'.format(
                            child_stream_name,
                            stream_name,
                            parent_id))
                        child_path = child_endpoint_config.get('path').format(str(parent_id))
                        child_total_records = sync_endpoint(
                            client=client,
                            catalog=catalog,
                            state=state,
                            start_date=start_date,
                            stream_name=child_stream_name,
                            path=child_path,
                            endpoint_config=child_endpoint_config,
                            data_key=child_endpoint_config.get('data_key', 'ResourceList'),
                            static_params=child_endpoint_config.get('params', {}),
                            bookmark_query_field=child_endpoint_config.get('bookmark_query_field'),
                            bookmark_field=child_endpoint_config.get('bookmark_field'),
                            bookmark_type=child_endpoint_config.get('bookmark_type'),
                            id_fields=child_endpoint_config.get('id_fields'),
                            parent=child_endpoint_config.get('parent'),
                            parent_id=parent_id)
                        LOGGER.info('Synced: {}, parent_id: {}, total_records: {}'.format(
                            child_stream_name, 
                            parent_id,
                            child_total_records))

        # Update the state with the max_bookmark_value for the stream
        if bookmark_field:
            write_bookmark(state,
                           stream_name,
                           max_bookmark_value)

        LOGGER.info('{} - Synced - page: {}, total pages: {}'.format(
            stream_name,
            page,
            total_pages))
        page = page + 1

    # Return total_records across all batches
    return total_records


# Review catalog and make a list of selected streams
def get_selected_streams(catalog):
    selected_streams = set()
    for stream in catalog.streams:
        mdata = metadata.to_map(stream.metadata)
        root_metadata = mdata.get(())
        if root_metadata and root_metadata.get('selected') is True:
            selected_streams.add(stream.tap_stream_id)
    return list(selected_streams)


# Currently syncing sets the stream currently being delivered in the state.
# If the integration is interrupted, this state property is used to identify
#  the starting point to continue from.
# Reference: https://github.com/singer-io/singer-python/blob/master/singer/bookmarks.py#L41-L46
def update_currently_syncing(state, stream_name):
    if (stream_name is None) and ('currently_syncing' in state):
        del state['currently_syncing']
    else:
        singer.set_currently_syncing(state, stream_name)
    singer.write_state(state)


# Review last_stream (last currently syncing stream), if any,
#  and continue where it left off in the selected streams.
# Or begin from the beginning, if no last_stream, and sync
#  all selected steams.
# Returns should_sync_stream (true/false) and last_stream.
def should_sync_stream(selected_streams, last_stream, stream_name):
    if last_stream == stream_name or last_stream is None:
        if last_stream is not None:
            last_stream = None
        if stream_name in selected_streams:
            return True, last_stream
    return False, last_stream


def sync(client, config, catalog, state, start_date):
    if 'start_date' in config:
        start_date = config['start_date']
    if 'customer_id' in config:
        customer_id = config['customer_id']
    if 'facility_id' in config:
        facility_id = config['facility_id']

    selected_streams = get_selected_streams(catalog)
    LOGGER.info('selected_streams: {}'.format(selected_streams))

    if not selected_streams:
        return

    # last_stream = Previous currently synced stream, if the load was interrupted
    last_stream = singer.get_currently_syncing(state)
    LOGGER.info('last/currently syncing stream: {}'.format(last_stream))

    # endpoints: API URL endpoints to be called
    # properties:
    #   <root node>: Plural stream name for the endpoint
    #   path: API endpoint relative path, when added to the base URL, creates the full path
    #   params: Query, sort, and other endpoint specific parameters
    #   data_key: JSON element containing the records for the endpoint
    #   bookmark_query_field: Typically a date-time field used for filtering the query
    #   bookmark_field: Replication key field, typically a date-time, used for filtering the results
    #        and setting the state
    #   bookmark_type: Data type for bookmark, integer or datetime
    #   store_ids: Used for parents to create an id_bag collection of ids for children endpoints
    #   id_fields: Primary key (and other IDs) from the Parent stored when store_ids is true.
    #   children: A collection of child endpoints (where the endpoint path includes the parent id)
    #   parent: On each of the children, the singular stream name for parent element

    endpoints = {
        'inventory': {
            'path': 'inventory',
            'params': {
                'pgsiz': 200,
                'sort': 'receivedDate'
            },
            'data_key': 'ResourceList',
            'id_fields': ['receive_item_id']
        },

        'locations': {
            'path': 'inventory/facilities/{}/locations',
            'params': {
                'pgsiz': 200
            },
            'data_key': 'ResourceList',
            'id_fields': ['facility_id', 'location_id']
        },

        'stock_summaries': {
            'path': 'inventory/stocksummaries',
            'params': {
                'pgsiz': 200,
                'facilityid': facility_id
            },
            'data_key': 'Summaries',
            'id_fields': ['facility_id', 'item_id']
        } ,

        'customers': {
            'path': 'customers',
            'params': {
                'pgsiz': 100,
                'sort': 'ReadOnly.CreationDate'
            },
            'data_key': 'ResourceList',
            'id_fields': ['customer_id'],
            'children': {
               'sku_items': {
                    'path': 'customers/{}/items',
                    'params': {
                        'pgsiz': 100,
                        'sort': 'ReadOnly.lastModifiedDate'
                    },
                    'data_key': 'ResourceList',
                    'bookmark_field': 'last_modified_date',
                    'bookmark_type': 'datetime',
                    'bookmark_query_field': 'ReadOnly.lastModifiedDate',
                    'id_fields': ['item_id'],
                    'parent': 'customer'
                },
                'stock_details': {
                    'path': 'inventory/stockdetails',
                    'params': {
                        'pgsiz': 100,
                        'customerid': customer_id,
                        'facilityid': facility_id,
                        'sort': 'receivedDate'
                    },
                    'data_key': 'ResourceList',
                    'id_fields': ['receive_item_id'],
                    'parent': 'customer'
                }
            }
        },

        'orders': {
            'path': 'orders',
            'params': {
                'pgsiz': 200,
                'detail': 'All',
                'itemdetail': 'All',
                'sort': 'ReadOnly.lastModifiedDate'
            },
            'data_key': 'ResourceList',
            'bookmark_field': 'last_modified_date',
            'bookmark_type': 'datetime',
            'bookmark_query_field': 'ReadOnly.lastModifiedDate',
            'id_fields': ['order_id']
        }
    }

# For each endpoint (above), determine if the stream should be streamed
    #   (based on the catalog and last_stream), then sync those streams.
    for stream_name, endpoint_config in endpoints.items():
        should_stream, last_stream = should_sync_stream(selected_streams,
                                                        last_stream,
                                                        stream_name)
        if should_stream:
            LOGGER.info('START Syncing: {}'.format(stream_name))
            update_currently_syncing(state, stream_name)
            if stream_name == 'locations':
                path = endpoint_config.get('path').format(facility_id)
            else:
                path = endpoint_config.get('path')
            total_records = sync_endpoint(
                client=client,
                catalog=catalog,
                state=state,
                start_date=start_date,
                stream_name=stream_name,
                path=path,
                endpoint_config=endpoint_config,
                data_key=endpoint_config.get('data_key', 'ResourceList'),
                static_params=endpoint_config.get('params', {}),
                bookmark_query_field=endpoint_config.get('bookmark_query_field'),
                bookmark_field=endpoint_config.get('bookmark_field'),
                bookmark_type=endpoint_config.get('bookmark_type'),
                id_fields=endpoint_config.get('id_fields'))

            update_currently_syncing(state, None)
            LOGGER.info('Synced: {}, total_records: {}'.format(
                            stream_name, 
                            total_records))
            LOGGER.info('FINISHED Syncing: {}'.format(stream_name))
