"""Mock integration test: automatic (primary key / replication key) fields are
always marked as inclusion=automatic in metadata."""
import unittest

from singer import metadata

from tap_3plcentral.discover import discover
from tap_3plcentral.schema import STREAMS


class AutomaticFieldsIntegrationTest(unittest.TestCase):

    def test_primary_and_replication_keys_are_automatic(self):
        """Verify that all primary keys and replication keys are marked
        as inclusion=automatic in discovery metadata."""
        catalog = discover()

        for stream in catalog.streams:
            with self.subTest(stream=stream.tap_stream_id):
                root = [
                    m for m in stream.metadata
                    if m.get("breadcrumb") in ((), [])
                ][0]
                key_props = set(root.get("metadata", {}).get("table-key-properties", []))
                rep_keys = root.get("metadata", {}).get("valid-replication-keys", [])
                if isinstance(rep_keys, str):
                    rep_keys = {rep_keys}
                else:
                    rep_keys = set(rep_keys)

                expected_auto = key_props | rep_keys

                actual_auto = set()
                for entry in stream.metadata:
                    breadcrumb = entry.get("breadcrumb", ())
                    if len(breadcrumb) == 2 and breadcrumb[0] == "properties":
                        if entry.get("metadata", {}).get("inclusion") == "automatic":
                            actual_auto.add(breadcrumb[1])

                self.assertTrue(
                    expected_auto.issubset(actual_auto),
                    f"Stream '{stream.tap_stream_id}': expected automatic fields "
                    f"{expected_auto} but got {actual_auto}",
                )
