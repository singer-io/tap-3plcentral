import re
import json
import time
import random
import tarfile
import math
from datetime import datetime, timedelta

import requests
import singer
from singer import metrics, metadata, Transformer
from tap_tplcentral.transform import transform_json, convert

LOGGER = singer.get_logger()


def validate_datetime(date_text):
    try:
        if date_text != datetime.strptime(date_text, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ"):
            raise ValueError
        return True
    except ValueError:
        return False

def write_schema(catalog, stream_name):
    stream = catalog.get_stream(stream_name)
    schema = stream.schema.to_dict()
    singer.write_schema(stream_name, schema, stream.key_properties)

def process_records(catalog,
                    stream_name,
                    records,
                    persist=True,
                    bookmark_field=None,
                    max_bookmark_field=None,
                    last_datetime=None,
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
            if bookmark_field:
                if max_bookmark_field is None or \
                    record[bookmark_field] > max_bookmark_field:
                    max_bookmark_field = record[bookmark_field]
            if persist:
                with Transformer() as transformer:
                    record = transformer.transform(record,
                                                   schema,
                                                   stream_metadata)
                if bookmark_field:
                    if isinstance(record[bookmark_field], int):
                        singer.write_record(stream_name, record)
                        counter.increment()
                    elif validate_datetime(record[bookmark_field]) and validate_datetime(last_datetime):
                        # Keep only records whose bookmark is after the last_datetime
                        if datetime.strptime(record[bookmark_field], "%Y-%m-%dT%H:%M:%SZ") >= \
                            datetime.strptime(last_datetime, "%Y-%m-%dT%H:%M:%SZ"):
                            singer.write_record(stream_name, record)
                            counter.increment()
                else:
                    singer.write_record(stream_name, record)
                    counter.increment()
        return max_bookmark_field

def get_bookmark(state, path, default):
    dic = state
    for key in (['bookmarks'] + path):
        if key in dic:
            dic = dic[key]
        else:
            return default
    return dic

def nested_set(dic, path, value):
    for key in path[:-1]:
        dic = dic.setdefault(key, {})
    dic[path[-1]] = value

def write_bookmark(state, path, value):
    nested_set(state, ['bookmarks'] + path, value)
    singer.write_state(state)

def sync_endpoint(client,
                  catalog,
                  state,
                  start_date,
                  stream_name,
                  persist,
                  path,
                  data_key,
                  static_params,
                  bookmark_path,
                  bookmark_query_field,
                  bookmark_field,
                  parent=None,
                  parent_id=None):
    bookmark_path = bookmark_path + [bookmark_field]
    last_datetime = get_bookmark(state, bookmark_path, start_date)
    ids = []
    max_bookmark_field = last_datetime

    def transform(record):
        _id = record.get('id')
        if _id:
            ids.append(_id)
        return record

    write_schema(catalog, stream_name)

    # pagination: loop thru all pages of data
    page = 1
    total_pages = 1  # initial value, set with first API call
    while page <= total_pages:
        params = {
            'pgnum': page,
            **static_params
        }

        if 'pgsiz' in params:
            page_size = params['pgsiz']
        else:
            page_size = 100

        # Resource Query Language (RQL) is used to filter data. Reference: http://api.3plcentral.com/rels/rql
        if bookmark_query_field:
            if 'rql' in params:
                params['rql'] = '{};{}=ge={}'.format(params['rql'], bookmark_query_field, last_datetime)
            else:
                params['rql'] = '{}=ge={}'.format(bookmark_query_field, last_datetime)

        LOGGER.info('{} - Sync start'.format(
            stream_name,
            'since: {}, '.format(last_datetime) if bookmark_query_field else ''))

        querystring = urllib.parse.urlencode(params)
        data = client.get(
            path,
            querystring=querystring,
            endpoint=stream_name)

        # transform raw data with transform_json from transform.py
        transform_data = transform_json(data, data_key)[convert(data_key)]

        max_bookmark_field = process_records(catalog=catalog,
                                             stream_name=stream_name,
                                             records=map(transform, transform_data),
                                             persist=persist,
                                             bookmark_field=bookmark_field,
                                             max_bookmark_field=max_bookmark_field,
                                             last_datetime=last_datetime,
                                             parent=parent,
                                             parent_id=parent_id)

        if bookmark_field:
            write_bookmark(state,
                           bookmark_path,
                           max_bookmark_field)

        # set page and total_pages for pagination
        total_results = data['TotalResults']
        total_pages = math.ceil(total_results / page_size)
        LOGGER.info('{} - Synced - page: {}, total pages: {}'.format(
            stream_name,
            page,
            total_pages))
        if page == 0 or page > 100:
            break
        page = page + 1

    return ids

def get_dependents(endpoint_config):
    dependents = endpoint_config.get('dependents', [])
    for stream_name, child_endpoint_config in endpoint_config.get('children', {}).items():
        dependents.append(stream_name)
        dependents += get_dependents(child_endpoint_config)
    return dependents

def sync_stream(client,
                catalog,
                state,
                start_date,
                streams_to_sync,
                id_bag,
                stream_name,
                endpoint_config,
                bookmark_path=None,
                id_path=None,
                parent=None,
                parent_id=None):
    if not bookmark_path:
        bookmark_path = [stream_name]
    if not id_path:
        id_path = []

    dependents = get_dependents(endpoint_config)
    should_stream, should_persist = should_sync_stream(streams_to_sync,
                                                       dependents,
                                                       stream_name)
    if should_stream:
        path = endpoint_config.get('path').format(*id_path)
        stream_ids = sync_endpoint(client=client,
                                   catalog=catalog,
                                   state=state,
                                   start_date=start_date,
                                   stream_name=stream_name,
                                   persist=should_persist,
                                   path=path,
                                   data_key=endpoint_config.get('data_path', stream_name),
                                   static_params=endpoint_config.get('params', {}),
                                   bookmark_path=bookmark_path,
                                   bookmark_query_field=endpoint_config.get('bookmark_query_field'),
                                   bookmark_field=endpoint_config.get('bookmark_field'),
                                   parent=endpoint_config.get('parent'),
                                   parent_id=parent_id)

        if endpoint_config.get('store_ids'):
            id_bag[stream_name] = stream_ids
        
        children = endpoint_config.get('children')
        if children:
            for child_stream_name, child_endpoint_config in children.items():
                for _id in stream_ids:
                    sync_stream(client=client,
                                catalog=catalog,
                                state=state,
                                start_date=start_date,
                                streams_to_sync=streams_to_sync,
                                id_bag=id_bag,
                                stream_name=child_stream_name,
                                endpoint_config=child_endpoint_config,
                                bookmark_path=bookmark_path + [_id, child_stream_name],
                                id_path=id_path + [_id],
                                parent=child_endpoint_config.get('parent'),
                                parent_id=_id)


def get_selected_streams(catalog):
    selected_streams = set()
    for stream in catalog.streams:
        mdata = metadata.to_map(stream.metadata)
        root_metadata = mdata.get(())
        if root_metadata and root_metadata.get('selected') is True:
            selected_streams.add(stream.tap_stream_id)
    return list(selected_streams)

def should_sync_stream(streams_to_sync, dependents, stream_name):
    selected_streams = streams_to_sync['selected_streams']
    should_persist = stream_name in selected_streams
    last_stream = streams_to_sync['last_stream']
    if last_stream == stream_name or last_stream is None:
        if last_stream is not None:
            streams_to_sync['last_stream'] = None
            return True, should_persist
        if should_persist or set(dependents).intersection(selected_streams):
            return True, should_persist
    return False, should_persist

def sync(client, config, catalog, state):
    if 'start_date' in config:
        start_date = config['start_date']
    if 'customer_id' in config:
        customer_id = config['customer_id']
    if 'facility_id' in config:
        facility_id = config['facility_id']
    streams_to_sync = {
        'selected_streams': get_selected_streams(catalog),
        'last_stream': state.get('current_stream')
    }

    if not streams_to_sync['selected_streams']:
        return

    id_bag = {}

    endpoints = {
        'customers': {
            'path': 'customers',
            'params': {
                'pgsiz': 100,
                'sort': 'ReadOnly.CreationDate'
            },
            'data_path': 'ResourceList',
            'bookmark_field': 'creation_date',
            'store_ids': True,
            'children': {
               'customer_items': {
                    'path': 'customers/{}/items',
                    'params': {
                        'pgsiz': 100,
                        'sort': 'ReadOnly.lastModifiedDate'
                    },
                    'data_path': 'ResourceList',
                    'bookmark_field': 'last_modified_date',
                    'bookmark_query_field': 'ReadOnly.lastModifiedDate',
                    'parent': 'customer'
                },
                'customer_stock_details': {
                    'path': 'inventory/stockdetails',
                    'params': {
                        'pgsiz': 100,
                        'customerid': customer_id,
                        'facilityid': facility_id,
                        'sort': 'ReadOnly.lastModifiedDate'
                    },
                    'data_path': 'ResourceList',
                    'bookmark_field': 'last_modified_date',
                    'bookmark_query_field': 'ReadOnly.lastModifiedDate',
                    'parent': 'customer'
                }
            }
        },
        
        'inventory': {
            'path': 'inventory',
            'params': {
                'pgsiz': 500,
                'sort': 'receivedDate'
            },
            'data_path': 'ResourceList',
            'bookmark_field': 'received_date',
            'bookmark_query_field': 'receivedDate'
        },

        'orders': {
            'path': 'orders',
            'params': {
                'pgsiz': 500,
                'detail': 'BillingDetails,SavedElements,Contacts,ProposedBilling,OutboundSerialNumbers',
                'sort': 'ReadOnly.lastModifiedDate'
            },
            'data_path': 'ResourceList',
            'bookmark_field': 'last_modified_date',
            'bookmark_query_field': 'ReadOnly.lastModifiedDate',
            'store_ids': True,
            'children': {
               'order_items': {
                    'path': 'orders/{}/items',
                    'params': {
                        'detail': 'All'
                    },
                    'data_path': 'ResourceList',
                    'bookmark_field': 'order_item_id',
                    'parent': 'order'
                },
                'order_packages': {
                    'path': 'orders/{}/packages',
                    'params': {},
                    'data_path': 'ResourceList',
                    'bookmark_field': 'create_date',
                    'parent': 'order'
                },
            }
        },
        
        'stock_summaries': {
            'path': 'inventory/stocksummaries',
            'params': {
                'pgsiz': 500
            },
            'data_path': 'Summaries'
        }

    }

    for stream_name, endpoint_config in endpoints.items():
        sync_stream(client,
                    catalog,
                    state,
                    start_date,
                    streams_to_sync,
                    id_bag,
                    stream_name,
                    endpoint_config)
