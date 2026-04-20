"""Mock integration test: discovery produces correct catalog and metadata."""
import unittest

from singer import metadata

from tap_3plcentral.discover import discover
from tap_3plcentral.schema import get_schemas, STREAMS

try:
    from .base import ThreePLCentralMockBaseTest
except ImportError:
    from base import ThreePLCentralMockBaseTest


class DiscoveryIntegrationTest(ThreePLCentralMockBaseTest, unittest.TestCase):

    def test_discovery_expected_streams_and_metadata(self):
        """Verify discover() returns all expected streams with correct metadata."""
        catalog = discover()
        stream_map = {stream.tap_stream_id: stream for stream in catalog.streams}
        expected_streams = self.expected_metadata()

        self.assertEqual(set(stream_map.keys()), set(expected_streams.keys()))

        for stream_name, stream_expected in expected_streams.items():
            with self.subTest(stream=stream_name):
                root_metadata = metadata.to_map(stream_map[stream_name].metadata)[()]
                self.assertEqual(
                    set(root_metadata.get("table-key-properties", [])),
                    stream_expected[self.PRIMARY_KEYS],
                )
                self.assertEqual(
                    root_metadata.get("forced-replication-method"),
                    stream_expected[self.REPLICATION_METHOD],
                )

                actual_replication_keys = root_metadata.get("valid-replication-keys", [])
                if isinstance(actual_replication_keys, str):
                    actual_replication_keys = {actual_replication_keys}
                else:
                    actual_replication_keys = set(actual_replication_keys)

                self.assertEqual(
                    actual_replication_keys,
                    stream_expected[self.REPLICATION_KEYS],
                )

    def test_discovery_parent_stream_metadata(self):
        """Streams with parent have parent-tap-stream-id in metadata."""
        catalog = discover()
        stream_map = {stream.tap_stream_id: stream for stream in catalog.streams}

        parent_expectations = {
            "sku_items": "customers",
            "stock_details": "customers",
        }

        for stream_name, expected_parent in parent_expectations.items():
            with self.subTest(stream=stream_name):
                root_md = metadata.to_map(stream_map[stream_name].metadata)[()]
                self.assertEqual(
                    root_md.get("parent-tap-stream-id"),
                    expected_parent,
                )

        orphan_streams = {"customers", "stock_summaries", "locations", "inventory", "orders"}
        for stream_name in orphan_streams:
            with self.subTest(stream=stream_name):
                root_md = metadata.to_map(stream_map[stream_name].metadata)[()]
                self.assertNotIn("parent-tap-stream-id", root_md)

    def test_discovery_schema_properties_exist(self):
        """Each stream schema has at least one property."""
        catalog = discover()
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                schema = entry.schema.to_dict()
                self.assertIn("properties", schema)
                self.assertTrue(len(schema["properties"]) > 0)
