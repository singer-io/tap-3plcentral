#!/usr/bin/env python3

import sys
import json
import argparse

import singer
from singer import metadata
from tap_tplcentral.client import TPLClient
from tap_tplcentral.discover import discover
from tap_tplcentral.sync import sync

LOGGER = singer.get_logger()

REQUIRED_CONFIG_KEYS = [
    'base_url',
    'client_id',
    'client_secret',
    'tpl_key',
    'user_login_id',
    'user_agent',
    'customer_id',
    'facility_id',
    'start_date'
]

def do_discover(client):

    LOGGER.info('Starting discover')
    catalog = discover()
    json.dump(catalog.to_dict(), sys.stdout, indent=2)
    LOGGER.info('Finished discover')


@singer.utils.handle_top_exception(LOGGER)
def main():

    parsed_args = singer.utils.parse_args(REQUIRED_CONFIG_KEYS)

    with TPLClient(
        base_url=parsed_args.config['base_url'],
        client_id=parsed_args.config['client_id'],
        client_secret=parsed_args.config['client_secret'],
        tpl_key=parsed_args.config['tpl_key'],
        user_login_id=parsed_args.config['user_login_id'],
        user_agent=parsed_args.config['user_agent']) as client:

        if parsed_args.discover:
            do_discover(client)
        elif parsed_args.catalog:
            sync(client=client,
                 config=parse_args.config,
                 catalog=parsed_args.catalog,
                 state=parsed_args.state)

if __name__ == '__main__':
    main()
