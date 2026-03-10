"""Test that with no fields selected for a stream automatic fields are still
replicated."""
from base import ThreePLCentralBaseTest
from tap_tester.base_suite_tests.automatic_fields_test import MinimumSelectionTest


class ThreePLCentralAutomaticFieldsTest(MinimumSelectionTest, ThreePLCentralBaseTest):
    """Test that with no fields selected for a stream automatic fields are
    still replicated."""

    @staticmethod
    def name():
        return "tap_tester_3plcentral_automatic_fields_test"

    def streams_to_test(self):
        streams_to_exclude = set()
        return self.expected_stream_names().difference(streams_to_exclude)
