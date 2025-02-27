# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import pytest

from azext_iot.tests.iothub import IoTLiveScenarioTest
from azext_iot.common.shared import AuthenticationTypeDataplane

# The current implementation of preview distributed tracing commands do not work with a cstring.

custom_auth_types = [
    AuthenticationTypeDataplane.key.value,
    AuthenticationTypeDataplane.login.value,
]


class TestIoTHubDistributedTracing(IoTLiveScenarioTest):
    def __init__(self, test_case):
        super(TestIoTHubDistributedTracing, self).__init__(test_case)

    def test_iothub_device_distributed_tracing(self):
        # Region specific test
        if self.region not in ["West US 2", "North Europe", "Southeast Asia"]:
            pytest.skip(
                msg="Skipping distributed-tracing tests. IoT Hub not in supported region!"
            )
            return

        for auth_phase in custom_auth_types:
            device_count = 1
            device_ids = self.generate_device_names(device_count)

            self.cmd(
                self.set_cmd_auth_type(
                    f"iot hub device-identity create -d {device_ids[0]} -n {self.entity_name} -g {self.entity_rg}",
                    auth_type=auth_phase,
                )
            )

            self.cmd(
                self.set_cmd_auth_type(
                    f"iot hub distributed-tracing show -d {device_ids[0]} -n {self.entity_name} -g {self.entity_rg}",
                    auth_type=auth_phase,
                ),
                checks=self.is_empty(),
            )

            result = self.cmd(
                self.set_cmd_auth_type(
                    f"iot hub distributed-tracing update "
                    f"-d {device_ids[0]} -n {self.entity_name} -g { self.entity_rg} --sm on --sr 50",
                    auth_type=auth_phase,
                )
            ).get_output_in_json()

            assert result["deviceId"] == device_ids[0]
            assert result["samplingMode"] == "enabled"
            assert result["samplingRate"] == "50%"
            assert not result["isSynced"]
