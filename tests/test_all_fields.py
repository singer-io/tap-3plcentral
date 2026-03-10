from base import ThreePLCentralBaseTest
from tap_tester.base_suite_tests.all_fields_test import AllFieldsTest


class ThreePLCentralAllFieldsTest(AllFieldsTest, ThreePLCentralBaseTest):
    """Ensure running the tap with all streams and fields selected results in
    the replication of all fields."""

    MISSING_FIELDS = {}

    @staticmethod
    def name():
        return "tap_tester_3plcentral_all_fields_test"

    def streams_to_test(self):
        streams_to_exclude = set()
        return self.expected_stream_names().difference(streams_to_exclude)
