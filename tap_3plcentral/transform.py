import re
import os
import json

# Convert camelCase to snake_case
def convert(name):
    regsub = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', regsub).lower()


# Convert keys in json array
def convert_array(arr):
    new_arr = []
    for i in arr:
        if isinstance(i, list):
            new_arr.append(convert_array(i))
        elif isinstance(i, dict):
            new_arr.append(convert_json(i))
        else:
            new_arr.append(i)
    return new_arr


# Convert keys in json
def convert_json(this_json):
    out = {}
    for key in this_json:
        new_key = convert(key)
        if isinstance(this_json[key], dict):
            out[new_key] = convert_json(this_json[key])
        elif isinstance(this_json[key], list):
            out[new_key] = convert_array(this_json[key])
        else:
            out[new_key] = this_json[key]
    return out


# Remove all _links and _embedded nodes from json
def remove_embedded_links(this_json):
    if not isinstance(this_json, (dict, list)):
        return this_json
    if isinstance(this_json, list):
        return [remove_embedded_links(vv) for vv in this_json]
    return {kk: remove_embedded_links(vv) for kk, vv in this_json.items()
            if kk not in {'_embedded', '_links'}}


# Copy path/_embedded sub-nodes up to path
def denest_embedded_readonly_nodes(this_json, path=None):
    if path is None:
        return this_json
    i = 0
    nodes = ['item']
    for record in this_json[path]:
        if "ReadOnly" in record:
            for key in record['ReadOnly']:
                record[key] = record['ReadOnly'][key]
            del record['ReadOnly']
        if "_embedded" in record:
            for node in nodes:
                if node in record['_embedded']:
                    this_json[path][i][node] = this_json[path][i]['_embedded'][node]    
                i = i + 1
            del record['embedded']
    return this_json


# Stock Summaries: de-nest item_id
def transform_stock_summaries(this_json, path):
    new_json = this_json
    i = 0
    for record in list(this_json[path]):
        item_id = record.get('item_identifier', {}).get('id')
        new_json[path][i]['item_id'] = item_id
        i = i + 1
    return new_json


# Locations: de-nest location_id and facility_id
def transform_locations(this_json, path):
    new_json = this_json
    i = 0
    for record in list(this_json[path]):
        location_id = record.get('location_identifier', {}).get('id')
        facility_id = record.get('location_identifier', {}).get('name_key', {}).get(
            'facility_identifier', {}).get('id')
        new_json[path][i]['location_id'] = location_id
        new_json[path][i]['facility_id'] = facility_id
        i = i + 1
    return new_json


# Run all transforms: denests _embedded and ReadOnly, removes _embedded/_links, and
#  converts camelCase to snake_case for fieldname keys.
def transform_json(this_json, stream, path):
    denested_json = denest_embedded_readonly_nodes(this_json, path)
    removed_json = remove_embedded_links(denested_json)
    converted_json = convert_json(removed_json)
    transformed_json = converted_json
    if stream == 'stock_summaries':
        transformed_json = transform_stock_summaries(converted_json, convert(path))
    elif stream == 'locations':
        transformed_json = transform_locations(converted_json, convert(path))
    return transformed_json
