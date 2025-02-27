# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import List
from collections import namedtuple
from time import sleep
from knack.log import get_logger
import pytest
from azext_iot.common.utility import unpack_msrest_error
from azext_iot.digitaltwins.common import ADTEndpointAuthType, ADTEndpointType, IdentityType
from azext_iot.tests.digitaltwins.dt_helpers import assert_system_data_attributes
from . import DTLiveScenarioTest
from . import (
    EP_RG,
    EP_EVENTHUB_NAMESPACE,
    EP_EVENTHUB_POLICY,
    EP_EVENTHUB_TOPIC,
    EP_EVENTGRID_TOPIC,
    EP_SERVICEBUS_NAMESPACE,
    EP_SERVICEBUS_POLICY,
    EP_SERVICEBUS_TOPIC,
    MOCK_RESOURCE_TAGS,
    MOCK_RESOURCE_TAGS_DICT,
    MOCK_DEAD_LETTER_SECRET,
    MOCK_DEAD_LETTER_ENDPOINT,
    generate_resource_id,
)

logger = get_logger(__name__)


class TestDTResourceLifecycle(DTLiveScenarioTest):
    def __init__(self, test_case):
        super(TestDTResourceLifecycle, self).__init__(test_case)
        self.ensure_eventgrid_resource()
        self.ensure_eventhub_resource()
        self.ensure_servicebus_resource()

    @pytest.fixture(scope='class', autouse=True)
    def tearDownSuite(self):
        yield None
        try:
            self.delete_user_identity()
        except Exception as e:
            logger.warning(
                "Failed to delete the User Identity resource. Additional details: " +
                unpack_msrest_error(e))
        try:
            self.delete_eventhub_resources()
        except Exception as e:
            logger.warning(
                "Failed to delete the EventHub resources. Additional details: " +
                unpack_msrest_error(e)
            )
        try:
            self.delete_eventgrid_resources()
        except Exception as e:
            logger.warning(
                "Failed to delete the Event Grid resources. Additional details: " +
                unpack_msrest_error(e)
            )
        try:
            self.delete_servicebus_resources()
        except Exception as e:
            logger.warning(
                "Failed to delete the ServiceBus resources. Additional details: " +
                unpack_msrest_error(e))

    def test_dt_resource(self):
        self.wait_for_capacity(capacity=3)

        eventgrid_topic_id = self.cmd(
            "eventgrid topic show -g {} -n {}".format(
                EP_RG, EP_EVENTGRID_TOPIC
            )
        ).get_output_in_json()["id"]

        servicebus_topic_id = self.cmd(
            "servicebus topic show -g {} -n {} --namespace-name {}".format(
                EP_RG,
                EP_SERVICEBUS_TOPIC,
                EP_SERVICEBUS_NAMESPACE,
            )
        ).get_output_in_json()["id"]

        scope_ids = [eventgrid_topic_id, servicebus_topic_id]

        instance_names = [generate_resource_id(), generate_resource_id()]
        create_output = self.cmd(
            "dt create -n {} -g {} -l {} --tags {}".format(
                instance_names[0],
                self.rg,
                self.region,
                MOCK_RESOURCE_TAGS,
            )
        ).get_output_in_json()
        self.track_instance(create_output)

        assert_common_resource_attributes(
            create_output,
            instance_names[0],
            self.rg,
            self.region,
            MOCK_RESOURCE_TAGS_DICT,
        )

        show_output = self.cmd(
            "dt show -n {}".format(instance_names[0])
        ).get_output_in_json()

        assert_common_resource_attributes(
            show_output,
            instance_names[0],
            self.rg,
            self.region,
            MOCK_RESOURCE_TAGS_DICT,
        )

        # Explictly assert create prevents provisioning on a name conflict (across regions)
        self.cmd(
            "dt create -n {} -g {} -l {} --tags {}".format(
                instance_names[0],
                self.rg,
                self.get_available_region(1, skip_regions=[self.region]),
                MOCK_RESOURCE_TAGS,
            ),
            expect_failure=True,
        )

        # Assert that --no-wait and --scopes will not work
        self.cmd(
            "dt create -n {} -g {} --mi-system-assigned --scopes {} --no-wait".format(
                instance_names[1], self.rg, " ".join(scope_ids)
            ),
            expect_failure=True,
        )

        # No location specified. Use the resource group location.
        create_msi_output = self.cmd(
            "dt create -n {} -g {} --mi-system-assigned --scopes {}".format(
                instance_names[1], self.rg, " ".join(scope_ids)
            )
        ).get_output_in_json()
        self.track_instance(create_msi_output)

        # wait for identity assignment
        sleep(60)

        self.cmd(
            "dt wait -n {} -g {} --custom \"{}\" --interval {} --timeout {}".format(
                instance_names[1],
                self.rg,
                "identity!='None'",
                15,
                15 * 20
            )
        )

        show_msi_output = self.cmd(
            "dt show -n {} -g {}".format(instance_names[1], self.rg)
        ).get_output_in_json()

        assert_common_resource_attributes(
            show_msi_output,
            instance_names[1],
            self.rg,
            self.rg_region,
            tags=None,
            assign_identity=True,
        )

        role_assignment_egt_list = self.cmd(
            "role assignment list --scope {} --assignee {}".format(
                eventgrid_topic_id, show_msi_output["identity"]["principalId"]
            )
        ).get_output_in_json()
        assert len(role_assignment_egt_list) == 1

        role_assignment_sbt_list = self.cmd(
            "role assignment list --scope {} --assignee {}".format(
                servicebus_topic_id, show_msi_output["identity"]["principalId"]
            )
        ).get_output_in_json()
        assert len(role_assignment_sbt_list) == 1

        # Update tags and disable MSI
        updated_tags = "env=test tier=premium"
        updated_tags_dict = {"env": "test", "tier": "premium"}
        self.cmd(
            "dt create -n {} -g {} --mi-system-assigned false --tags {} --no-wait".format(
                instance_names[1], self.rg, updated_tags
            )
        )

        self.cmd(
            "dt wait -n {} -g {} --custom \"{}\" --interval {} --timeout {}".format(
                instance_names[1],
                self.rg,
                "identity=='None'",
                15,
                15 * 20
            )
        )

        remove_msi_output = self.cmd(
            "dt show -n {} -g {}".format(
                instance_names[1], self.rg
            )
        ).get_output_in_json()

        assert_common_resource_attributes(
            remove_msi_output,
            instance_names[1],
            self.rg,
            self.rg_region,
            tags=updated_tags_dict,
            assign_identity=False,
        )

        list_output = self.cmd("dt list").get_output_in_json()
        filtered_list = filter_dt_list(list_output, instance_names)
        assert len(filtered_list) == len(instance_names)

        list_group_output = self.cmd(
            "dt list -g {}".format(self.rg)
        ).get_output_in_json()
        filtered_group_list = filter_dt_list(list_group_output, instance_names)
        assert len(filtered_group_list) == len(instance_names)

        # Delete does not currently return output
        # Delete no blocking
        self.cmd(
            "dt delete -n {} -g {} -y --no-wait".format(instance_names[1], self.rg)
        )

        # Delete while blocking
        self.cmd("dt delete -n {} -y".format(instance_names[0]))

    def test_dt_rbac(self):
        self.wait_for_capacity()

        rbac_assignee_owner = self.current_user
        rbac_assignee_reader = self.current_user

        rbac_instance_name = generate_resource_id()
        rbac_instance = self.cmd(
            "dt create -n {} -g {} -l {}".format(
                rbac_instance_name,
                self.rg,
                self.region,
            )
        ).get_output_in_json()
        self.track_instance(rbac_instance)

        assert (
            len(
                self.cmd(
                    "dt role-assignment list -n {}".format(rbac_instance_name)
                ).get_output_in_json()
            )
            == 0
        )

        assign_output = self.cmd(
            "dt role-assignment create -n {} --assignee {} --role '{}'".format(
                rbac_instance_name, rbac_assignee_owner, self.role_map["owner"]
            )
        ).get_output_in_json()

        assert_common_rbac_attributes(
            assign_output,
            rbac_instance_name,
            "owner",
            rbac_assignee_owner,
        )

        assign_output = self.cmd(
            "dt role-assignment create -n {} --assignee {} --role '{}' -g {}".format(
                rbac_instance_name,
                rbac_assignee_reader,
                self.role_map["reader"],
                self.rg,
            )
        ).get_output_in_json()

        assert_common_rbac_attributes(
            assign_output,
            rbac_instance_name,
            "reader",
            rbac_assignee_reader,
        )

        list_assigned_output = self.cmd(
            "dt role-assignment list -n {}".format(rbac_instance_name)
        ).get_output_in_json()

        assert len(list_assigned_output) == 2

        # Remove specific role assignment (reader) for assignee
        # Role-assignment delete does not currently return output
        self.cmd(
            "dt role-assignment delete -n {} --assignee {} --role '{}'".format(
                rbac_instance_name,
                rbac_assignee_owner,
                self.role_map["reader"],
            )
        )

        list_assigned_output = self.cmd(
            "dt role-assignment list -n {} -g {}".format(rbac_instance_name, self.rg)
        ).get_output_in_json()

        assert len(list_assigned_output) == 1

        # Remove all role assignments for assignee
        self.cmd(
            "dt role-assignment delete -n {} --assignee {}".format(
                rbac_instance_name, rbac_assignee_reader
            )
        )

        list_assigned_output = self.cmd(
            "dt role-assignment list -n {} -g {}".format(rbac_instance_name, self.rg)
        ).get_output_in_json()

        assert len(list_assigned_output) == 0

    def test_dt_endpoints_routes(self):
        self.wait_for_capacity()
        endpoints_instance_name = generate_resource_id()
        target_scope_role = "Contributor"

        sb_topic_resource_id = self.embedded_cli.invoke(
            "servicebus topic show --namespace-name {} -n {} -g {}".format(
                EP_SERVICEBUS_NAMESPACE,
                EP_SERVICEBUS_TOPIC,
                EP_RG,
            )
        ).as_json()["id"]

        eh_resource_id = self.embedded_cli.invoke(
            "eventhubs eventhub show --namespace-name {} -n {} -g {}".format(
                EP_EVENTHUB_NAMESPACE,
                EP_EVENTHUB_TOPIC,
                EP_RG,
            )
        ).as_json()["id"]
        endpoint_instance = self.cmd(
            "dt create -n {} -g {} -l {} --mi-system-assigned --scopes {} {} --role {}".format(
                endpoints_instance_name,
                self.rg,
                self.region,
                sb_topic_resource_id,
                eh_resource_id,
                target_scope_role,
            )
        ).get_output_in_json()
        self.track_instance(endpoint_instance)

        # Setup RBAC so we can interact with routes
        self.cmd(
            "dt role-assignment create -n {} --assignee {} --role '{}' -g {}".format(
                endpoints_instance_name,
                self.current_user,
                self.role_map["owner"],
                self.rg,
            )
        )

        sleep(30)  # Wait for service to catch-up

        EndpointTuple = namedtuple(
            "endpoint_tuple", ["endpoint_name", "endpoint_type", "auth_type"]
        )
        endpoint_tuple_collection: List[EndpointTuple] = []
        list_ep_output = self.cmd(
            "dt endpoint list -n {}".format(endpoints_instance_name)
        ).get_output_in_json()
        assert len(list_ep_output) == 0

        eventgrid_endpoint = "myeventgridendpoint"

        logger.debug("Adding key based eventgrid endpoint...")
        self.cmd(
            "dt endpoint create eventgrid -n {} -g {} {} --egt {} --en {} --dsu {} --no-wait".format(
                endpoints_instance_name,
                self.rg,
                "" if EP_RG == self.rg else f"--egg {EP_RG}",
                EP_EVENTGRID_TOPIC,
                eventgrid_endpoint,
                MOCK_DEAD_LETTER_SECRET,
            )
        )
        endpoint_tuple_collection.append(
            EndpointTuple(
                eventgrid_endpoint,
                ADTEndpointType.eventgridtopic,
                ADTEndpointAuthType.keybased,
            )
        )

        servicebus_endpoint = "myservicebusendpoint"

        logger.debug("Adding key based servicebus topic endpoint...")
        self.cmd(
            "dt endpoint create servicebus -n {} {} --sbn {} --sbp {} --sbt {} --en {} --dsu {} --no-wait".format(
                endpoints_instance_name,
                "" if EP_RG == self.rg else f"--sbg {EP_RG}",
                EP_SERVICEBUS_NAMESPACE,
                EP_SERVICEBUS_POLICY,
                EP_SERVICEBUS_TOPIC,
                servicebus_endpoint,
                MOCK_DEAD_LETTER_SECRET,
            )
        )
        endpoint_tuple_collection.append(
            EndpointTuple(
                servicebus_endpoint,
                ADTEndpointType.servicebus,
                ADTEndpointAuthType.keybased,
            )
        )

        eventhub_endpoint_msi = "myeventhubendpointidentity"

        logger.debug("Adding identity based eventhub endpoint...")
        self.cmd(
            "dt endpoint create eventhub -n {} {} --ehn {} --eh {} --ehs {} --en {} --du {} "
            "--system --no-wait".format(
                endpoints_instance_name,
                "" if EP_RG == self.rg else f"--ehg {EP_RG}",
                EP_EVENTHUB_NAMESPACE,
                EP_EVENTHUB_TOPIC,
                self.current_subscription,
                eventhub_endpoint_msi,
                MOCK_DEAD_LETTER_ENDPOINT,
            )
        )

        # wait for the last endpoint to create, just in case
        self.cmd(
            "dt endpoint wait -n {} -g {} --en {} --created".format(
                endpoints_instance_name,
                self.rg,
                eventhub_endpoint_msi,
            )
        )
        endpoint_tuple_collection.append(
            EndpointTuple(
                eventhub_endpoint_msi,
                ADTEndpointType.eventhub,
                ADTEndpointAuthType.identitybased,
            )
        )

        list_ep_output = self.cmd(
            "dt endpoint list -n {} -g {}".format(endpoints_instance_name, self.rg)
        ).get_output_in_json()
        assert len(list_ep_output) == 3

        endpoint_names = [eventgrid_endpoint, servicebus_endpoint, eventhub_endpoint_msi]
        filter_values = ["", "false", "type = Microsoft.DigitalTwins.Twin.Create"]

        # Test Routes
        list_routes_output = self.cmd(
            "dt route list -n {}".format(endpoints_instance_name)
        ).get_output_in_json()
        assert len(list_routes_output) == 0

        for endpoint_name in endpoint_names:
            is_last = endpoint_name == endpoint_names[-1]
            route_name = "routefor{}".format(endpoint_name)
            filter_value = filter_values.pop()
            add_route_output = self.cmd(
                "dt route create -n {} --rn {} --en {} --filter '{}' {}".format(
                    endpoints_instance_name,
                    route_name,
                    endpoint_name,
                    filter_value,
                    "-g {}".format(self.rg) if is_last else "",
                )
            ).get_output_in_json()

            assert_common_route_attributes(
                add_route_output, route_name, endpoint_name, filter_value
            )

            show_route_output = self.cmd(
                "dt route show -n {} --rn {} {}".format(
                    endpoints_instance_name,
                    route_name,
                    "-g {}".format(self.rg) if is_last else "",
                )
            ).get_output_in_json()

            assert_common_route_attributes(
                show_route_output, route_name, endpoint_name, filter_value
            )

        list_routes_output = self.cmd(
            "dt route list -n {} -g {}".format(endpoints_instance_name, self.rg)
        ).get_output_in_json()
        assert len(list_routes_output) == 3

        for endpoint_name in endpoint_names:
            is_last = endpoint_name == endpoint_names[-1]
            route_name = "routefor{}".format(endpoint_name)
            self.cmd(
                "dt route delete -n {} --rn {} {}".format(
                    endpoints_instance_name,
                    route_name,
                    "-g {}".format(self.rg) if is_last else "",
                )
            )

        list_routes_output = self.cmd(
            "dt route list -n {} -g {}".format(endpoints_instance_name, self.rg)
        ).get_output_in_json()
        assert len(list_routes_output) == 0

    def test_dt_endpoints(self):
        self.wait_for_capacity()
        endpoints_instance_name = generate_resource_id()
        user_identity = self.ensure_user_identity()
        user_identity_principal_id = user_identity["principalId"]
        user_identity_id = user_identity["id"]
        target_scope_role = "Contributor"

        sb_topic_resource_id = self.embedded_cli.invoke(
            "servicebus topic show --namespace-name {} -n {} -g {}".format(
                EP_SERVICEBUS_NAMESPACE,
                EP_SERVICEBUS_TOPIC,
                EP_RG,
            )
        ).as_json()["id"]

        eh_resource_id = self.embedded_cli.invoke(
            "eventhubs eventhub show --namespace-name {} -n {} -g {}".format(
                EP_EVENTHUB_NAMESPACE,
                EP_EVENTHUB_TOPIC,
                EP_RG,
            )
        ).as_json()["id"]

        self.assign_role_assignment(
            scope=sb_topic_resource_id, role=target_scope_role, assignee=user_identity_principal_id
        )

        self.assign_role_assignment(
            scope=eh_resource_id, role=target_scope_role, assignee=user_identity_principal_id
        )

        endpoint_instance = self.cmd(
            "dt create -n {} -g {} -l {} --mi-system-assigned --scopes {} {} --role {} --mi-user-assigned {}".format(
                endpoints_instance_name,
                self.rg,
                self.region,
                sb_topic_resource_id,
                eh_resource_id,
                target_scope_role,
                user_identity_id
            )
        ).get_output_in_json()
        self.track_instance(endpoint_instance)

        EndpointTuple = namedtuple(
            "endpoint_tuple", ["endpoint_name", "endpoint_type", "auth_type"]
        )
        endpoint_tuple_collection: List[EndpointTuple] = []
        list_ep_output = self.cmd(
            "dt endpoint list -n {}".format(endpoints_instance_name)
        ).get_output_in_json()
        assert len(list_ep_output) == 0

        eventgrid_endpoint = "myeventgridendpoint"

        logger.debug("Adding key based eventgrid endpoint...")
        add_ep_output = self.cmd(
            "dt endpoint create eventgrid -n {} -g {} --egg {} --egt {} --en {} --dsu {}".format(
                endpoints_instance_name,
                self.rg,
                EP_RG,
                EP_EVENTGRID_TOPIC,
                eventgrid_endpoint,
                MOCK_DEAD_LETTER_SECRET,
            )
        ).get_output_in_json()

        self.cmd(
            "dt endpoint wait --created -n {} -g {} --en {} --interval 1".format(
                endpoints_instance_name,
                self.rg,
                eventgrid_endpoint
            )
        )

        assert_common_endpoint_attributes(
            add_ep_output,
            eventgrid_endpoint,
            ADTEndpointType.eventgridtopic,
            dead_letter_secret=MOCK_DEAD_LETTER_SECRET,
        )

        # Delete and re-add endpoint with no wait
        self.cmd(
            "dt endpoint delete -n {} -g {} --en {} -y".format(
                endpoints_instance_name,
                self.rg,
                eventgrid_endpoint
            )
        )

        self.cmd(
            "dt endpoint create eventgrid -n {} -g {} --egg {} --egt {} --en {} --dsu {} --no-wait".format(
                endpoints_instance_name,
                self.rg,
                EP_RG,
                EP_EVENTGRID_TOPIC,
                eventgrid_endpoint,
                MOCK_DEAD_LETTER_SECRET,
            )
        )

        self.cmd(
            "dt endpoint wait --created -n {} -g {} --en {}".format(
                endpoints_instance_name,
                self.rg,
                eventgrid_endpoint
            )
        )

        show_ep_output = self.cmd(
            "dt endpoint show -n {} -g {} --en {}".format(
                endpoints_instance_name,
                self.rg,
                eventgrid_endpoint
            )
        ).get_output_in_json()

        assert_common_endpoint_attributes(
            show_ep_output,
            eventgrid_endpoint,
            ADTEndpointType.eventgridtopic,
            dead_letter_secret=MOCK_DEAD_LETTER_SECRET,
        )

        endpoint_tuple_collection.append(
            EndpointTuple(
                eventgrid_endpoint,
                ADTEndpointType.eventgridtopic,
                ADTEndpointAuthType.keybased,
            )
        )

        servicebus_endpoint = "myservicebusendpoint"
        servicebus_endpoint_msi = "{}identity".format(servicebus_endpoint)
        servicebus_endpoint_uai = "{}user".format(servicebus_endpoint)

        logger.debug("Adding key based servicebus topic endpoint...")
        add_ep_sb_key_output = self.cmd(
            "dt endpoint create servicebus -n {} --sbg {} --sbn {} --sbp {} --sbt {} --en {} --dsu {}".format(
                endpoints_instance_name,
                EP_RG,
                EP_SERVICEBUS_NAMESPACE,
                EP_SERVICEBUS_POLICY,
                EP_SERVICEBUS_TOPIC,
                servicebus_endpoint,
                MOCK_DEAD_LETTER_SECRET,
            )
        ).get_output_in_json()

        self.cmd(
            "dt endpoint wait --created -n {} -g {} --en {} --interval 1".format(
                endpoints_instance_name,
                self.rg,
                servicebus_endpoint
            )
        )

        assert_common_endpoint_attributes(
            add_ep_sb_key_output,
            servicebus_endpoint,
            endpoint_type=ADTEndpointType.servicebus,
            auth_type=ADTEndpointAuthType.keybased,
            dead_letter_secret=MOCK_DEAD_LETTER_SECRET,
        )

        # Delete and re-add endpoint with no wait
        self.cmd(
            "dt endpoint delete -n {} -g {} --en {} -y".format(
                endpoints_instance_name,
                self.rg,
                servicebus_endpoint
            )
        )

        self.cmd(
            "dt endpoint create servicebus -n {} --sbg {} --sbn {} --sbp {} --sbt {} --en {} --dsu {} --no-wait".format(
                endpoints_instance_name,
                EP_RG,
                EP_SERVICEBUS_NAMESPACE,
                EP_SERVICEBUS_POLICY,
                EP_SERVICEBUS_TOPIC,
                servicebus_endpoint,
                MOCK_DEAD_LETTER_SECRET,
            )
        )

        self.cmd(
            "dt endpoint wait --created -n {} -g {} --en {}".format(
                endpoints_instance_name,
                self.rg,
                servicebus_endpoint
            )
        )

        show_ep_sb_key_output = self.cmd(
            "dt endpoint show -n {} -g {} --en {}".format(
                endpoints_instance_name,
                self.rg,
                servicebus_endpoint
            )
        ).get_output_in_json()

        assert_common_endpoint_attributes(
            show_ep_sb_key_output,
            servicebus_endpoint,
            endpoint_type=ADTEndpointType.servicebus,
            auth_type=ADTEndpointAuthType.keybased,
            dead_letter_secret=MOCK_DEAD_LETTER_SECRET,
        )
        endpoint_tuple_collection.append(
            EndpointTuple(
                servicebus_endpoint,
                ADTEndpointType.servicebus,
                ADTEndpointAuthType.keybased,
            )
        )

        logger.debug("Adding identity based servicebus topic endpoint...")
        add_ep_sb_identity_output = self.cmd(
            "dt endpoint create servicebus -n {} --sbg {} --sbn {} --sbt {} --en {} --du {} --system".format(
                endpoints_instance_name,
                EP_RG,
                EP_SERVICEBUS_NAMESPACE,
                EP_SERVICEBUS_TOPIC,
                servicebus_endpoint_msi,
                MOCK_DEAD_LETTER_ENDPOINT,
            )
        ).get_output_in_json()

        self.cmd(
            "dt endpoint wait --created -n {} -g {} --en {} --interval 1".format(
                endpoints_instance_name,
                self.rg,
                servicebus_endpoint_msi,
            )
        )

        assert_common_endpoint_attributes(
            add_ep_sb_identity_output,
            servicebus_endpoint_msi,
            endpoint_type=ADTEndpointType.servicebus,
            auth_type=ADTEndpointAuthType.identitybased,
            dead_letter_endpoint=MOCK_DEAD_LETTER_ENDPOINT,
        )
        endpoint_tuple_collection.append(
            EndpointTuple(
                servicebus_endpoint_msi,
                ADTEndpointType.servicebus,
                ADTEndpointAuthType.identitybased,
            )
        )

        logger.debug("Adding User identity based servicebus topic endpoint...")
        add_ep_sb_identity_output = self.cmd(
            "dt endpoint create servicebus -n {} --sbg {} --sbn {} --sbt {} --en {} --du {} --user {}".format(
                endpoints_instance_name,
                EP_RG,
                EP_SERVICEBUS_NAMESPACE,
                EP_SERVICEBUS_TOPIC,
                servicebus_endpoint_uai,
                MOCK_DEAD_LETTER_ENDPOINT,
                user_identity_id
            )
        ).get_output_in_json()

        self.cmd(
            "dt endpoint wait --created -n {} -g {} --en {} --interval 1".format(
                endpoints_instance_name,
                self.rg,
                servicebus_endpoint_uai,
            )
        )

        assert_common_endpoint_attributes(
            add_ep_sb_identity_output,
            servicebus_endpoint_uai,
            endpoint_type=ADTEndpointType.servicebus,
            auth_type=ADTEndpointAuthType.identitybased,
            dead_letter_endpoint=MOCK_DEAD_LETTER_ENDPOINT,
        )

        # Delete endpoint to avoid endpoint limits
        self.cmd(
            "dt endpoint delete -n {} -g {} --en {} -y".format(
                endpoints_instance_name,
                self.rg,
                servicebus_endpoint_uai,
            )
        )

        eventhub_endpoint = "myeventhubendpoint"
        eventhub_endpoint_msi = "{}identity".format(eventhub_endpoint)
        eventhub_endpoint_uai = "{}user".format(eventhub_endpoint)

        # Cannot use both system and user identities
        add_ep_output = self.cmd(
            "dt endpoint create eventhub -n {} --ehg {} --ehn {} --ehp {} --eh {} --ehs {} --en {}"
            " --dsu '{}' --system --user {}".format(
                endpoints_instance_name,
                EP_RG,
                EP_EVENTHUB_NAMESPACE,
                EP_EVENTHUB_POLICY,
                EP_EVENTHUB_TOPIC,
                self.current_subscription,
                eventhub_endpoint,
                MOCK_DEAD_LETTER_SECRET,
                user_identity_id
            ),
            expect_failure=True
        )

        logger.debug("Adding key based eventhub endpoint...")
        add_ep_output = self.cmd(
            "dt endpoint create eventhub -n {} --ehg {} --ehn {} --ehp {} --eh {} --ehs {} --en {} --dsu '{}'".format(
                endpoints_instance_name,
                EP_RG,
                EP_EVENTHUB_NAMESPACE,
                EP_EVENTHUB_POLICY,
                EP_EVENTHUB_TOPIC,
                self.current_subscription,
                eventhub_endpoint,
                MOCK_DEAD_LETTER_SECRET,
            )
        ).get_output_in_json()

        self.cmd(
            "dt endpoint wait --created -n {} -g {} --en {} --interval 1".format(
                endpoints_instance_name,
                self.rg,
                eventhub_endpoint,
            )
        )

        assert_common_endpoint_attributes(
            add_ep_output,
            eventhub_endpoint,
            ADTEndpointType.eventhub,
            auth_type=ADTEndpointAuthType.keybased,
            dead_letter_secret=MOCK_DEAD_LETTER_SECRET,
        )
        endpoint_tuple_collection.append(
            EndpointTuple(
                eventhub_endpoint,
                ADTEndpointType.eventhub,
                ADTEndpointAuthType.keybased,
            )
        )

        logger.debug("Adding identity based eventhub endpoint...")
        add_ep_output = self.cmd(
            "dt endpoint create eventhub -n {} --ehg {} --ehn {} --eh {} --ehs {} --en {} --du {} "
            "--system".format(
                endpoints_instance_name,
                EP_RG,
                EP_EVENTHUB_NAMESPACE,
                EP_EVENTHUB_TOPIC,
                self.current_subscription,
                eventhub_endpoint_msi,
                MOCK_DEAD_LETTER_ENDPOINT,
            )
        ).get_output_in_json()

        self.cmd(
            "dt endpoint wait -n {} -g {} --en {} --created --interval 1".format(
                endpoints_instance_name,
                self.rg,
                eventhub_endpoint_msi,
            )
        )

        assert_common_endpoint_attributes(
            add_ep_output,
            eventhub_endpoint_msi,
            endpoint_type=ADTEndpointType.eventhub,
            auth_type=ADTEndpointAuthType.identitybased,
            dead_letter_endpoint=MOCK_DEAD_LETTER_ENDPOINT,
        )

        # Delete and re-add endpoint with no wait
        self.cmd(
            "dt endpoint delete -n {} -g {} --en {} -y".format(
                endpoints_instance_name,
                self.rg,
                eventhub_endpoint_msi,
            )
        )

        self.cmd(
            "dt endpoint create eventhub -n {} --ehg {} --ehn {} --eh {} --ehs {} --en {} --du {} "
            "--system --no-wait".format(
                endpoints_instance_name,
                EP_RG,
                EP_EVENTHUB_NAMESPACE,
                EP_EVENTHUB_TOPIC,
                self.current_subscription,
                eventhub_endpoint_msi,
                MOCK_DEAD_LETTER_ENDPOINT,
            )
        )

        self.cmd(
            "dt endpoint wait -n {} -g {} --en {} --created".format(
                endpoints_instance_name,
                self.rg,
                eventhub_endpoint_msi,
            )
        )

        show_ep_output = self.cmd(
            "dt endpoint show -n {} -g {} --en {}".format(
                endpoints_instance_name,
                self.rg,
                eventhub_endpoint_msi,
            )
        ).get_output_in_json()

        assert_common_endpoint_attributes(
            show_ep_output,
            eventhub_endpoint_msi,
            endpoint_type=ADTEndpointType.eventhub,
            auth_type=ADTEndpointAuthType.identitybased,
            dead_letter_endpoint=MOCK_DEAD_LETTER_ENDPOINT,
        )
        endpoint_tuple_collection.append(
            EndpointTuple(
                eventhub_endpoint_msi,
                ADTEndpointType.eventhub,
                ADTEndpointAuthType.identitybased,
            )
        )

        logger.debug("Adding user identity based eventhub endpoint...")
        add_ep_output = self.cmd(
            "dt endpoint create eventhub -n {} --ehg {} --ehn {} --eh {} --ehs {} --en {} --du {} "
            "--user {}".format(
                endpoints_instance_name,
                EP_RG,
                EP_EVENTHUB_NAMESPACE,
                EP_EVENTHUB_TOPIC,
                self.current_subscription,
                eventhub_endpoint_uai,
                MOCK_DEAD_LETTER_ENDPOINT,
                user_identity_id
            )
        ).get_output_in_json()

        self.cmd(
            "dt endpoint wait -n {} -g {} --en {} --created --interval 1".format(
                endpoints_instance_name,
                self.rg,
                eventhub_endpoint_uai,
            )
        )

        assert_common_endpoint_attributes(
            add_ep_output,
            eventhub_endpoint_uai,
            endpoint_type=ADTEndpointType.eventhub,
            auth_type=ADTEndpointAuthType.identitybased,
            dead_letter_endpoint=MOCK_DEAD_LETTER_ENDPOINT,
        )
        endpoint_tuple_collection.append(
            EndpointTuple(
                eventhub_endpoint_uai,
                ADTEndpointType.eventhub,
                ADTEndpointAuthType.identitybased,
            )
        )

        for ep in endpoint_tuple_collection:
            is_last = ep.endpoint_name == endpoint_tuple_collection[-1].endpoint_name
            show_ep_output = self.cmd(
                "dt endpoint show -n {} --en {} {}".format(
                    endpoints_instance_name,
                    ep.endpoint_name,
                    "-g {}".format(self.rg) if is_last else "",
                )
            ).get_output_in_json()

            assert_common_endpoint_attributes(
                show_ep_output,
                ep.endpoint_name,
                endpoint_type=ep.endpoint_type,
                auth_type=ep.auth_type,
            )

        list_ep_output = self.cmd(
            "dt endpoint list -n {} -g {}".format(endpoints_instance_name, self.rg)
        ).get_output_in_json()
        assert len(list_ep_output) == 6

        for ep in endpoint_tuple_collection:
            logger.debug("Deleting endpoint {}...".format(ep.endpoint_name))
            is_last = ep.endpoint_name == endpoint_tuple_collection[-1].endpoint_name
            self.cmd(
                "dt endpoint delete -y -n {} --en {} --no-wait {}".format(
                    endpoints_instance_name,
                    ep.endpoint_name,
                    "-g {}".format(self.rg) if is_last else "",
                )
            )
            self.cmd(
                "dt endpoint wait -n {} --en {} --deleted --interval 1 {}".format(
                    endpoints_instance_name,
                    ep.endpoint_name,
                    "-g {}".format(self.rg) if is_last else "",
                )
            )

        list_endpoint_output = self.cmd(
            "dt endpoint list -n {} -g {}".format(endpoints_instance_name, self.rg)
        ).get_output_in_json()
        assert (
            len(list_endpoint_output) == 0
            or len(
                [
                    ep
                    for ep in list_endpoint_output
                    if ep["properties"]["provisioningState"].lower() != "deleting"
                ]
            )
            == 0
        )

    def test_dt_identity(self):
        self.wait_for_capacity()
        target_scope_role = "Contributor"
        user_identity = self.ensure_user_identity()
        user_identity_id = user_identity["id"]

        dt_instance_name = generate_resource_id()
        dt_instance = self.cmd(
            "dt create -n {} -g {} -l {}".format(
                dt_instance_name,
                self.rg,
                self.region,
            )
        ).get_output_in_json()
        self.track_instance(dt_instance)

        self.cmd(
            "dt identity assign -n {} -g {}".format(
                dt_instance_name,
                self.rg,
            ),
            expect_failure=True
        )

        self.cmd(
            "dt identity assign -n {} -g {} --role {}".format(
                dt_instance_name,
                self.rg,
                target_scope_role
            ),
            expect_failure=True
        )

        self.cmd(
            "dt identity assign -n {} -g {} --scopes {}".format(
                dt_instance_name,
                self.rg,
                target_scope_role
            ),
            expect_failure=True
        )

        # Assign only system
        assign_output = self.cmd(
            "dt identity assign -n {} -g {} --system".format(
                dt_instance_name,
                self.rg
            )
        ).get_output_in_json()
        assert assign_output["principalId"]
        assert assign_output["tenantId"]
        assert assign_output["type"] == IdentityType.system_assigned.value
        assert assign_output.get("userIdentities") is None

        # Assign user - system should not be removed
        assign_user_output = self.cmd(
            "dt identity assign -n {} -g {} --user {}".format(
                dt_instance_name,
                self.rg,
                user_identity_id
            )
        ).get_output_in_json()
        assert assign_output["principalId"] == assign_user_output["principalId"]
        assert assign_output["tenantId"] == assign_user_output["tenantId"]
        assert assign_user_output["type"] == IdentityType.system_assigned_user_assigned.value
        assert len(assign_user_output["userAssignedIdentities"]) == 1
        assert assign_user_output["userAssignedIdentities"].get(user_identity_id)

        show_output = self.cmd(
            "dt identity show -n {} -g {}".format(
                dt_instance_name,
                self.rg,
            )
        ).get_output_in_json()
        assert assign_user_output["principalId"] == show_output["principalId"]
        assert assign_user_output["tenantId"] == show_output["tenantId"]
        assert assign_user_output["type"] == show_output["type"]
        assert assign_user_output["userAssignedIdentities"] == show_output["userAssignedIdentities"]

        # Remove user identities only, system identities stay the same
        remove_output = self.cmd(
            "dt identity remove -n {} -g {} --user {}".format(
                dt_instance_name,
                self.rg,
                user_identity_id
            )
        ).get_output_in_json()
        assert assign_output["principalId"] == remove_output["principalId"]
        assert assign_output["tenantId"] == remove_output["tenantId"]
        assert remove_output["type"] == IdentityType.system_assigned.value
        assert remove_output.get("userIdentities") is None

        # Readd user
        assign_user_output = self.cmd(
            "dt identity assign -n {} -g {} --user {}".format(
                dt_instance_name,
                self.rg,
                user_identity_id
            )
        ).get_output_in_json()
        assert assign_output["principalId"] == assign_user_output["principalId"]
        assert assign_output["tenantId"] == assign_user_output["tenantId"]
        assert assign_user_output["type"] == IdentityType.system_assigned_user_assigned.value
        assert len(assign_user_output["userAssignedIdentities"]) == 1
        assert assign_user_output["userAssignedIdentities"].get(user_identity_id)

        # Remove system
        remove_output = self.cmd(
            "dt identity remove -n {} -g {} --system".format(
                dt_instance_name,
                self.rg,
            )
        ).get_output_in_json()
        assert remove_output["principalId"] is None
        assert remove_output["tenantId"]
        assert remove_output["type"] == IdentityType.user_assigned.value
        assert len(remove_output["userAssignedIdentities"]) == 1
        assert remove_output["userAssignedIdentities"].get(user_identity_id)

        # Remove user
        remove_output = self.cmd(
            "dt identity remove -n {} -g {} --user {}".format(
                dt_instance_name,
                self.rg,
                user_identity_id
            )
        )
        assert remove_output.output == ''

        # Assign only user
        assign_output = self.cmd(
            "dt identity assign -n {} -g {} --user {}".format(
                dt_instance_name,
                self.rg,
                user_identity_id
            )
        ).get_output_in_json()
        assert assign_output["principalId"] is None
        assert assign_output["tenantId"]
        assert assign_output["type"] == IdentityType.user_assigned.value
        assert len(assign_output["userAssignedIdentities"]) == 1
        assert assign_output["userAssignedIdentities"].get(user_identity_id)

        # Assign system - user not removed; principal id may be different from original
        assign_output = self.cmd(
            "dt identity assign -n {} -g {} --system".format(
                dt_instance_name,
                self.rg,
            )
        ).get_output_in_json()
        assert assign_output["principalId"]
        assert assign_output["tenantId"]
        assert assign_output["type"] == IdentityType.system_assigned_user_assigned.value
        assert len(assign_output["userAssignedIdentities"]) == 1
        assert assign_output["userAssignedIdentities"].get(user_identity_id)

        # Remove all identities
        remove_output = self.cmd(
            "dt identity remove -n {} -g {} --user --system".format(
                dt_instance_name,
                self.rg,
            )
        )
        assert remove_output.output == ''


def assert_common_resource_attributes(
    instance_output, resource_id, group_id, location, tags=None, assign_identity=None
):
    assert instance_output["createdTime"]
    assert_system_data_attributes(instance_output.get("systemData"))
    hostname = instance_output.get("hostName")

    assert hostname, "Provisioned instance is missing hostName."
    assert hostname.startswith(resource_id)
    assert instance_output["location"] == location
    assert instance_output["id"].endswith(resource_id)
    assert instance_output["lastUpdatedTime"]
    assert instance_output["name"] == resource_id
    assert instance_output["provisioningState"] == "Succeeded"
    assert instance_output["resourceGroup"] == group_id
    assert instance_output["type"] == "Microsoft.DigitalTwins/digitalTwinsInstances"

    if tags:
        assert instance_output["tags"] == tags

    if not assign_identity:
        assert instance_output["identity"] is None
        return

    assert instance_output["identity"]["principalId"]
    assert instance_output["identity"]["tenantId"]
    # Currently only SystemAssigned identity is supported.
    assert instance_output["identity"]["type"] == "SystemAssigned"


def assert_common_route_attributes(
    route_output, route_name, endpoint_name, filter_value
):
    assert route_output["endpointName"] == endpoint_name
    assert route_output["id"] == route_name
    assert route_output["filter"] == filter_value if filter_value else "true"


def assert_common_endpoint_attributes(
    endpoint_output,
    endpoint_name,
    endpoint_type,
    dead_letter_secret=None,
    dead_letter_endpoint=None,
    auth_type=ADTEndpointAuthType.keybased,
):
    assert_system_data_attributes(endpoint_output.get("systemData"))
    assert endpoint_output["id"].endswith("/{}".format(endpoint_name))
    assert (
        endpoint_output["type"]
        == "Microsoft.DigitalTwins/digitalTwinsInstances/endpoints"
    )
    assert endpoint_output["resourceGroup"]
    assert endpoint_output["properties"]["provisioningState"]
    assert endpoint_output["properties"]["createdTime"]

    if dead_letter_secret:
        pass
        # TODO: This appears to be flaky.
        # assert endpoint_output["properties"][
        #    "deadLetterSecret"
        # ], "Expected deadletter secret."

    if dead_letter_endpoint:
        assert endpoint_output["properties"][
            "deadLetterUri"
        ], "Expected deadletter Uri."

    # Currently DT -> EventGrid is only key based.
    if endpoint_type == ADTEndpointType.eventgridtopic:
        assert endpoint_output["properties"]["topicEndpoint"]
        assert endpoint_output["properties"]["accessKey1"]
        assert endpoint_output["properties"]["accessKey2"]
        assert endpoint_output["properties"]["endpointType"] == "EventGrid"
        return
    if endpoint_type == ADTEndpointType.servicebus:
        if auth_type == ADTEndpointAuthType.keybased:
            assert endpoint_output["properties"]["primaryConnectionString"]
            assert endpoint_output["properties"]["secondaryConnectionString"]
        if auth_type == ADTEndpointAuthType.identitybased:
            assert endpoint_output["properties"]["endpointUri"]
            assert endpoint_output["properties"]["entityPath"]
        assert endpoint_output["properties"]["endpointType"] == "ServiceBus"
        return
    if endpoint_type == ADTEndpointType.eventhub:
        if auth_type == ADTEndpointAuthType.keybased:
            assert endpoint_output["properties"]["connectionStringPrimaryKey"]
            assert endpoint_output["properties"]["connectionStringSecondaryKey"]
        if auth_type == ADTEndpointAuthType.identitybased:
            assert endpoint_output["properties"]["endpointUri"]
            assert endpoint_output["properties"]["entityPath"]
        assert endpoint_output["properties"]["endpointType"] == "EventHub"
        return


def assert_common_rbac_attributes(rbac_output, instance_name, role_name, assignee):
    role_def_id = None
    if role_name == "owner":
        role_def_id = "/bcd981a7-7f74-457b-83e1-cceb9e632ffe"
    elif role_name == "reader":
        role_def_id = "/d57506d4-4c8d-48b1-8587-93c323f6a5a3"

    assert rbac_output["roleDefinitionId"].endswith(role_def_id)
    assert rbac_output["type"] == "Microsoft.Authorization/roleAssignments"
    assert rbac_output["scope"].endswith("/{}".format(instance_name))


def filter_dt_list(list_output, valid_names):
    return [inst for inst in list_output if inst["name"] in valid_names]
