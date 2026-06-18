import json
import unittest
from unittest.mock import patch, MagicMock

from singer.catalog import Catalog, CatalogEntry, Schema
from tap_3plcentral.discover import (
    discover,
    check_stream_access,
    _prune_inaccessible_children,
    _apply_access_checks,
)
from tap_3plcentral.schema import get_schemas, STREAMS
from tap_3plcentral.client import TPLAPIError


# ---------------------------------------------------------------------------
# check_stream_access
# ---------------------------------------------------------------------------

class TestCheckStreamAccess(unittest.TestCase):

    def test_returns_true_when_accessible(self):
        client = MagicMock()
        result = check_stream_access(client, 'customers')
        self.assertTrue(result)
        client.get.assert_called_once_with(
            resource_path='customers',
            querystring='pgsiz=1',
            endpoint='customers',
        )

    def test_returns_false_on_401(self):
        client = MagicMock()
        client.get.side_effect = TPLAPIError('Unauthorized', error_code=401)
        result = check_stream_access(client, 'customers')
        self.assertFalse(result)

    def test_returns_false_on_403(self):
        client = MagicMock()
        client.get.side_effect = TPLAPIError('Forbidden', error_code=403)
        result = check_stream_access(client, 'orders')
        self.assertFalse(result)

    def test_returns_false_on_404(self):
        client = MagicMock()
        client.get.side_effect = TPLAPIError('Not Found', error_code=404)
        result = check_stream_access(client, 'locations', facility_id='123')
        self.assertFalse(result)

    def test_uses_mapped_stock_summaries_resource_path(self):
        client = MagicMock()
        result = check_stream_access(client, 'stock_summaries')
        self.assertTrue(result)
        client.get.assert_called_once_with(
            resource_path='inventory/stocksummaries',
            querystring='pgsiz=1',
            endpoint='stock_summaries',
        )

    def test_uses_locations_path_with_facility_id(self):
        client = MagicMock()
        result = check_stream_access(client, 'locations', facility_id='789')
        self.assertTrue(result)
        client.get.assert_called_once_with(
            resource_path='inventory/facilities/789/locations',
            querystring='pgsiz=1',
            endpoint='locations',
        )

    def test_reraises_non_auth_tpl_error(self):
        """TPLAPIError with a non-auth code (e.g. 500) is re-raised."""
        client = MagicMock()
        client.get.side_effect = TPLAPIError('Internal Server Error', error_code=500)
        with self.assertRaises(TPLAPIError):
            check_stream_access(client, 'customers')

    def test_reraises_other_exceptions(self):
        client = MagicMock()
        client.get.side_effect = ConnectionError('network error')
        with self.assertRaises(ConnectionError):
            check_stream_access(client, 'customers')


# ---------------------------------------------------------------------------
# _prune_inaccessible_children
# ---------------------------------------------------------------------------

class TestPruneInaccessibleChildren(unittest.TestCase):

    def test_removes_child_when_parent_absent(self):
        """sku_items is pruned when its parent 'customers' is not in schemas."""
        schemas = {'sku_items': {}, 'orders': {}}
        field_metadata = {'sku_items': [], 'orders': []}
        _prune_inaccessible_children(schemas, field_metadata)
        self.assertNotIn('sku_items', schemas)
        self.assertNotIn('sku_items', field_metadata)

    def test_keeps_child_when_parent_present(self):
        schemas = {'customers': {}, 'sku_items': {}}
        field_metadata = {'customers': [], 'sku_items': []}
        _prune_inaccessible_children(schemas, field_metadata)
        self.assertIn('sku_items', schemas)

    def test_keeps_top_level_streams_unchanged(self):
        schemas = {'customers': {}, 'orders': {}}
        field_metadata = {'customers': [], 'orders': []}
        _prune_inaccessible_children(schemas, field_metadata)
        self.assertIn('customers', schemas)
        self.assertIn('orders', schemas)

    def test_removes_multiple_children_when_parent_absent(self):
        """Both sku_items and stock_details are pruned when 'customers' is absent."""
        schemas = {'sku_items': {}, 'stock_details': {}, 'orders': {}}
        field_metadata = {'sku_items': [], 'stock_details': [], 'orders': []}
        _prune_inaccessible_children(schemas, field_metadata)
        self.assertNotIn('sku_items', schemas)
        self.assertNotIn('stock_details', schemas)
        self.assertIn('orders', schemas)


# ---------------------------------------------------------------------------
# _apply_access_checks
# ---------------------------------------------------------------------------

class TestApplyAccessChecks(unittest.TestCase):

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_removes_inaccessible_top_level_stream(self, mock_check):
        mock_check.side_effect = lambda client, name, **kwargs: name != 'orders'
        schemas = {'customers': {}, 'orders': {}, 'sku_items': {}}
        field_metadata = {'customers': [], 'orders': [], 'sku_items': []}
        _apply_access_checks(MagicMock(), schemas, field_metadata)
        self.assertNotIn('orders', schemas)
        self.assertNotIn('orders', field_metadata)
        self.assertIn('customers', schemas)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_prunes_child_when_parent_removed(self, mock_check):
        mock_check.side_effect = lambda client, name, **kwargs: name != 'customers'
        schemas = {'customers': {}, 'sku_items': {}, 'orders': {}}
        field_metadata = {'customers': [], 'sku_items': [], 'orders': []}
        _apply_access_checks(MagicMock(), schemas, field_metadata)
        self.assertNotIn('customers', schemas)
        self.assertNotIn('sku_items', schemas)
        self.assertIn('orders', schemas)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_does_not_probe_child_streams(self, mock_check):
        """check_stream_access is never called for child streams."""
        mock_check.return_value = True
        schemas = {'customers': {}, 'sku_items': {}, 'orders': {}}
        field_metadata = {'customers': [], 'sku_items': [], 'orders': []}
        _apply_access_checks(MagicMock(), schemas, field_metadata)
        probed = [call.args[1] for call in mock_check.call_args_list]
        self.assertNotIn('sku_items', probed)
        self.assertNotIn('stock_details', probed)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_raises_when_all_inaccessible(self, mock_check):
        mock_check.return_value = False
        schemas = {'customers': {}, 'orders': {}, 'sku_items': {}}
        field_metadata = {'customers': [], 'orders': [], 'sku_items': []}
        with self.assertRaises(TPLAPIError) as ctx:
            _apply_access_checks(MagicMock(), schemas, field_metadata)
        self.assertIn("do not have 'read' access to any", str(ctx.exception))

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_no_changes_when_all_accessible(self, mock_check):
        mock_check.return_value = True
        schemas = {'customers': {}, 'orders': {}, 'sku_items': {}}
        field_metadata = {'customers': [], 'orders': [], 'sku_items': []}
        _apply_access_checks(MagicMock(), schemas, field_metadata)
        self.assertIn('customers', schemas)
        self.assertIn('orders', schemas)
        self.assertIn('sku_items', schemas)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_logs_warning_for_inaccessible_stream(self, mock_check):
        mock_check.side_effect = lambda client, name, **kwargs: name != 'orders'
        schemas = {'customers': {}, 'orders': {}, 'sku_items': {}}
        field_metadata = {'customers': [], 'orders': [], 'sku_items': []}
        with patch('tap_3plcentral.discover.LOGGER') as mock_logger:
            _apply_access_checks(MagicMock(), schemas, field_metadata)
        warning_msgs = ' '.join(str(c) for c in mock_logger.warning.call_args_list)
        self.assertIn('orders', warning_msgs)


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------

class TestDiscover(unittest.TestCase):

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_discover_returns_catalog(self, mock_check):
        mock_check.return_value = True
        catalog = discover(MagicMock())
        self.assertIsInstance(catalog, Catalog)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_discover_all_streams_present(self, mock_check):
        """Discover returns an entry for every stream when all accessible."""
        mock_check.return_value = True
        catalog = discover(MagicMock())
        stream_names = {entry.stream for entry in catalog.streams}
        for expected_stream in STREAMS:
            self.assertIn(expected_stream, stream_names)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_discover_stream_key_properties(self, mock_check):
        """Each catalog entry has the correct key_properties from STREAMS."""
        mock_check.return_value = True
        catalog = discover(MagicMock())
        for entry in catalog.streams:
            expected_keys = STREAMS[entry.stream]['key_properties']
            self.assertEqual(entry.key_properties, expected_keys)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_discover_stream_has_schema(self, mock_check):
        """Each catalog entry has a non-empty schema."""
        mock_check.return_value = True
        catalog = discover(MagicMock())
        for entry in catalog.streams:
            schema_dict = entry.schema.to_dict()
            self.assertIn('properties', schema_dict)
            self.assertTrue(len(schema_dict['properties']) > 0)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_discover_stream_has_metadata(self, mock_check):
        """Each catalog entry has metadata."""
        mock_check.return_value = True
        catalog = discover(MagicMock())
        for entry in catalog.streams:
            self.assertIsNotNone(entry.metadata)
            self.assertTrue(len(entry.metadata) > 0)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_inaccessible_stream_excluded(self, mock_check):
        """A stream that fails the access check is excluded from the catalog."""
        mock_check.side_effect = lambda client, name, **kwargs: name != 'orders'
        catalog = discover(MagicMock())
        stream_names = [s.stream for s in catalog.streams]
        self.assertNotIn('orders', stream_names)
        self.assertIn('customers', stream_names)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_child_excluded_when_parent_inaccessible(self, mock_check):
        """Child streams are excluded when their parent is inaccessible."""
        mock_check.side_effect = lambda client, name, **kwargs: name != 'customers'
        catalog = discover(MagicMock())
        stream_names = [s.stream for s in catalog.streams]
        self.assertNotIn('customers', stream_names)
        self.assertNotIn('sku_items', stream_names)
        self.assertNotIn('stock_details', stream_names)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_child_included_when_parent_accessible(self, mock_check):
        mock_check.return_value = True
        catalog = discover(MagicMock())
        stream_names = [s.stream for s in catalog.streams]
        self.assertIn('customers', stream_names)
        self.assertIn('sku_items', stream_names)
        self.assertIn('stock_details', stream_names)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_child_not_probed_directly(self, mock_check):
        """check_stream_access is never called for child streams."""
        mock_check.return_value = True
        discover(MagicMock())
        probed = [call.args[1] for call in mock_check.call_args_list]
        self.assertNotIn('sku_items', probed)
        self.assertNotIn('stock_details', probed)

    @patch('tap_3plcentral.discover.check_stream_access')
    def test_all_inaccessible_raises_exception(self, mock_check):
        """When all top-level streams are inaccessible, discover() raises."""
        mock_check.return_value = False
        with self.assertRaises(TPLAPIError) as ctx:
            discover(MagicMock())
        self.assertIn("do not have 'read' access to any", str(ctx.exception))


# ---------------------------------------------------------------------------
# get_schemas / STREAMS config (unchanged tests)
# ---------------------------------------------------------------------------

class TestGetSchemas(unittest.TestCase):

    def test_get_schemas_returns_all(self):
        schemas, field_metadata = get_schemas()
        for stream_name in STREAMS:
            self.assertIn(stream_name, schemas)
            self.assertIn(stream_name, field_metadata)

    def test_get_schemas_valid_json(self):
        schemas, _ = get_schemas()
        for stream_name, schema in schemas.items():
            self.assertIn('type', schema)
            self.assertIn('properties', schema)

    def test_get_schemas_metadata_format(self):
        _, field_metadata = get_schemas()
        for stream_name, mdata in field_metadata.items():
            self.assertIsInstance(mdata, list)
            for entry in mdata:
                self.assertIn('breadcrumb', entry)
                self.assertIn('metadata', entry)

    def test_get_schemas_replication_method(self):
        _, field_metadata = get_schemas()
        for stream_name, mdata in field_metadata.items():
            root_entries = [m for m in mdata if m['breadcrumb'] == ()]
            self.assertTrue(len(root_entries) > 0)
            root_metadata = root_entries[0]['metadata']
            expected_method = STREAMS[stream_name]['replication_method']
            self.assertEqual(root_metadata.get('forced-replication-method'), expected_method)

    def test_get_schemas_parent_stream_metadata(self):
        _, field_metadata = get_schemas()
        for stream_name, stream_config in STREAMS.items():
            parent = stream_config.get('parent')
            mdata = field_metadata[stream_name]
            root_entries = [m for m in mdata if m['breadcrumb'] == ()]
            root_metadata = root_entries[0]['metadata']
            if parent:
                self.assertEqual(root_metadata.get('parent-tap-stream-id'), parent)
            else:
                self.assertNotIn('parent-tap-stream-id', root_metadata)


class TestStreamsConfig(unittest.TestCase):

    def test_all_streams_have_key_properties(self):
        for name, config in STREAMS.items():
            self.assertIn('key_properties', config, f'{name} missing key_properties')
            self.assertIsInstance(config['key_properties'], list)
            self.assertTrue(len(config['key_properties']) > 0)

    def test_all_streams_have_replication_method(self):
        for name, config in STREAMS.items():
            self.assertIn('replication_method', config, f'{name} missing replication_method')
            self.assertIn(config['replication_method'], ['FULL_TABLE', 'INCREMENTAL'])

    def test_incremental_streams_have_replication_keys(self):
        for name, config in STREAMS.items():
            if config['replication_method'] == 'INCREMENTAL':
                self.assertIn('replication_keys', config)
                self.assertTrue(len(config['replication_keys']) > 0)

    def test_expected_stream_names(self):
        expected = {'customers', 'sku_items', 'stock_details', 'stock_summaries',
                    'locations', 'inventory', 'orders'}
        self.assertEqual(set(STREAMS.keys()), expected)


if __name__ == '__main__':
    unittest.main()
