import json
import unittest
from unittest.mock import patch, MagicMock

from singer.catalog import Catalog, CatalogEntry, Schema
from tap_3plcentral.discover import discover
from tap_3plcentral.schema import get_schemas, STREAMS


class TestDiscover(unittest.TestCase):
    """Tests for the discover function."""

    def test_discover_returns_catalog(self):
        """Discover returns a Catalog object."""
        catalog = discover()
        self.assertIsInstance(catalog, Catalog)

    def test_discover_all_streams_present(self):
        """Discover returns an entry for every stream defined in STREAMS."""
        catalog = discover()
        stream_names = {entry.stream for entry in catalog.streams}
        for expected_stream in STREAMS:
            self.assertIn(expected_stream, stream_names)

    def test_discover_stream_key_properties(self):
        """Each catalog entry has the correct key_properties from STREAMS."""
        catalog = discover()
        for entry in catalog.streams:
            expected_keys = STREAMS[entry.stream]["key_properties"]
            self.assertEqual(entry.key_properties, expected_keys)

    def test_discover_stream_has_schema(self):
        """Each catalog entry has a non-empty schema."""
        catalog = discover()
        for entry in catalog.streams:
            schema_dict = entry.schema.to_dict()
            self.assertIn("properties", schema_dict)
            self.assertTrue(len(schema_dict["properties"]) > 0)

    def test_discover_stream_has_metadata(self):
        """Each catalog entry has metadata."""
        catalog = discover()
        for entry in catalog.streams:
            self.assertIsNotNone(entry.metadata)
            self.assertTrue(len(entry.metadata) > 0)


class TestGetSchemas(unittest.TestCase):
    """Tests for get_schemas."""

    def test_get_schemas_returns_all(self):
        """get_schemas returns schemas for all defined streams."""
        schemas, field_metadata = get_schemas()
        for stream_name in STREAMS:
            self.assertIn(stream_name, schemas)
            self.assertIn(stream_name, field_metadata)

    def test_get_schemas_valid_json(self):
        """Each schema returned is a valid dict with type and properties."""
        schemas, _ = get_schemas()
        for stream_name, schema in schemas.items():
            self.assertIn("type", schema)
            self.assertIn("properties", schema)

    def test_get_schemas_metadata_format(self):
        """Metadata is a list of dicts with breadcrumb and metadata keys."""
        _, field_metadata = get_schemas()
        for stream_name, mdata in field_metadata.items():
            self.assertIsInstance(mdata, list)
            for entry in mdata:
                self.assertIn("breadcrumb", entry)
                self.assertIn("metadata", entry)

    def test_get_schemas_replication_method(self):
        """Metadata root entry includes the correct replication method."""
        _, field_metadata = get_schemas()
        for stream_name, mdata in field_metadata.items():
            root_entries = [m for m in mdata if m["breadcrumb"] == ()]
            self.assertTrue(len(root_entries) > 0)
            root_metadata = root_entries[0]["metadata"]
            expected_method = STREAMS[stream_name]["replication_method"]
            self.assertEqual(
                root_metadata.get("forced-replication-method"), expected_method
            )

    def test_get_schemas_parent_stream_metadata(self):
        """Streams with a parent have parent-tap-stream-id in metadata."""
        _, field_metadata = get_schemas()
        for stream_name, stream_config in STREAMS.items():
            parent = stream_config.get("parent")
            mdata = field_metadata[stream_name]
            root_entries = [m for m in mdata if m["breadcrumb"] == ()]
            root_metadata = root_entries[0]["metadata"]

            if parent:
                # Singer expects parent-tap-stream-id to be a real parent stream id
                # Map any known misconfigured parent values to their actual stream ids.
                expected_parent_id = parent
                if parent == "customer":
                    expected_parent_id = "customers"

                self.assertEqual(
                    root_metadata.get("parent-tap-stream-id"),
                    expected_parent_id,
                    f"Expected parent '{expected_parent_id}' for stream '{stream_name}'",
                )
            else:
                self.assertNotIn("parent-tap-stream-id", root_metadata)


class TestStreamsConfig(unittest.TestCase):
    """Tests for the STREAMS configuration dictionary."""

    def test_all_streams_have_key_properties(self):
        for name, config in STREAMS.items():
            self.assertIn("key_properties", config, f"{name} missing key_properties")
            self.assertIsInstance(config["key_properties"], list)
            self.assertTrue(len(config["key_properties"]) > 0)

    def test_all_streams_have_replication_method(self):
        for name, config in STREAMS.items():
            self.assertIn(
                "replication_method", config, f"{name} missing replication_method"
            )
            self.assertIn(
                config["replication_method"],
                ["FULL_TABLE", "INCREMENTAL"],
                f"{name} has invalid replication_method",
            )

    def test_incremental_streams_have_replication_keys(self):
        for name, config in STREAMS.items():
            if config["replication_method"] == "INCREMENTAL":
                self.assertIn(
                    "replication_keys",
                    config,
                    f"Incremental stream '{name}' missing replication_keys",
                )
                self.assertTrue(len(config["replication_keys"]) > 0)

    def test_expected_stream_names(self):
        expected = {
            "customers",
            "sku_items",
            "stock_details",
            "stock_summaries",
            "locations",
            "inventory",
            "orders",
        }
        self.assertEqual(set(STREAMS.keys()), expected)


if __name__ == "__main__":
    unittest.main()
