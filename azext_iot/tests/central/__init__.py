# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import json
import time
import os
from typing import Tuple

from azure.cli.core.azclierror import CLIInternalError
from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.conftest import get_context_path
from azext_iot.tests.generators import generate_generic_id
from azext_iot.tests.helpers import add_test_tag, create_storage_account, CERT_ENDING
from azext_iot.tests.settings import DynamoSettings
from azext_iot.tests.test_utils import create_certificate
from azext_iot.common import utility
from azext_iot.central.models.enum import Role, UserType
from azext_iot.tests.test_constants import ResourceTypes
from knack.log import get_logger


logger = get_logger(__name__)
DEFAULT_CONTAINER = "devices"
CENTRAL_SETTINGS = [
    "azext_iot_testrg",
    "azext_iot_central_app_id",
    "azext_iot_central_primarykey",
    "azext_iot_central_scope_id",
    "azext_iot_central_token",
    "azext_iot_central_dns_suffix",
    "azext_iot_teststorageaccount",
    "azext_iot_central_storage_container",
]
settings = DynamoSettings(opt_env_set=CENTRAL_SETTINGS)
APP_RG = settings.env.azext_iot_testrg

# Storage Account
DEFAULT_CONTAINER = "central"
STORAGE_CONTAINER = (
    settings.env.azext_iot_central_storage_container or DEFAULT_CONTAINER
)
STORAGE_ACCOUNT = (
    settings.env.azext_iot_teststorageaccount or "iotstore" + generate_generic_id()[:4]
)
DEFAULT_FILE_UPLOAD_TTL = "PT1H"

# Device templates
device_template_path = get_context_path(__file__, "json/device_template_int_test.json")
edge_template_path_preview = get_context_path(
    __file__, "json/device_template_edge.json"
)
sync_command_params = get_context_path(__file__, "json/sync_command_args.json")
device_updated_properties_path = get_context_path(__file__, "json/device_update_properties.json")
device_updated_component_properties_path = get_context_path(__file__, "json/device_update_component_properties.json")

# Device attestation
attestation_payload = {
    'type': 'symmetricKey',
    'symmetricKey': {
        'primaryKey': utility.generate_key(),
        'secondaryKey': utility.generate_key()
    }
}

attestation_payload_update = {
    'type': 'symmetricKey',
    'symmetricKey': {
        'primaryKey': utility.generate_key(),
        'secondaryKey': utility.generate_key()
    }
}

scheduled_job_schedule = {
    "start": "3022-05-24T22:29:01Z",
    "recurrence": "daily"
}

scheduled_job_schedule_update = {
    "start": "3022-05-24T22:29:01Z",
    "recurrence": "daily"
}

scheduled_job_data = [
    {
        "type": "property",
        "target": "",
        "path": "testFirstProperty",
        "value": "updated value"
    }
]


class CentralLiveScenarioTest(CaptureOutputLiveScenarioTest):
    def __init__(self, test_scenario):
        super(CentralLiveScenarioTest, self).__init__(test_scenario)
        self._create_app()
        # Do not add tagging to non-prod central apps
        if (
            not settings.env.azext_iot_central_dns_suffix
            and not settings.env.azext_iot_central_token
        ):
            add_test_tag(
                cmd=self.cmd,
                name=self.app_id,
                rg=self.app_rg,
                rtype=ResourceTypes.central.value,
                test_tag=test_scenario,
            )

    def cmd(  # pylint: disable=arguments-renamed
        self,
        command,
        api_version=None,
        checks=None,
        expect_failure=False,
        include_opt_args=True,
    ):
        if include_opt_args:
            command = self._appendOptionalArgsToCommand(
                command, api_version=api_version
            )
        return super().cmd(command, checks=checks, expect_failure=expect_failure)

    def _create_app(self):
        """
        Create an Iot Central Application if a name is not given in the pytest configuration.

        Will populate the following variables based on given pytest configuration:
          - app_id
          - app_rg
          - app_primary_key
          - _scope_id
          - token
          - dns_suffix
        """
        self.app_id = (
            settings.env.azext_iot_central_app_id or "test-app-" + generate_generic_id()
        )
        self._scope_id = settings.env.azext_iot_central_scope_id

        # only populate these if given in the test configuration variables
        self.app_primary_key = settings.env.azext_iot_central_primarykey
        self.dns_suffix = settings.env.azext_iot_central_dns_suffix
        self.token = settings.env.azext_iot_central_token

        # Create Central App if it does not exist. Note that app_primary_key will be nullified since
        # there is no current way to get the app_primary_key and not all tests can be executed.
        if not settings.env.azext_iot_central_app_id:
            if not APP_RG:
                raise Exception("Tests need either app name or resource group.")
            if (
                settings.env.azext_iot_central_dns_suffix
                or settings.env.azext_iot_central_token
            ):
                raise Exception(
                    "Create an IoT Central App with a valid API token and populate the azext_iot_central_app_id, "
                    "azext_iot_central_dns_suffix, and azext_iot_central_token variables for testing in non-prod environments."
                )

            app_list = self.cmd(
                'iot central app list -g "{}"'.format(APP_RG)
            ).get_output_in_json()

            # Check if the generated name is already used
            target_app = None
            for app in app_list:
                if app["name"] == self.app_id:
                    target_app = app
                    break

            # Create the min version app and assign the correct roles
            if not target_app:
                self.cmd(
                    "iot central app create -n {} -g {} -s {} -l {}".format(
                        self.app_id, APP_RG, self.app_id, "westus"
                    ),
                    include_opt_args=False,
                )

            self.app_primary_key = None
            # Will be repopulated with get_app_scope_id for tests that need it
            self._scope_id = None

        # Get Central App RG if possible
        if (
            settings.env.azext_iot_central_dns_suffix
            or settings.env.azext_iot_central_token
        ):
            if not APP_RG:
                logger.info(
                    "Tests will not have the resource group populated. If a storage account is not"
                    " specified, it will not be created and the respective tests will not run."
                )
            self.app_rg = APP_RG
        else:
            self.app_rg = self.cmd(
                "iot central app show -n {}".format(
                    self.app_id,
                )
            ).get_output_in_json()["resourceGroup"]

    def _create_device(self, api_version, **kwargs) -> Tuple[str, str]:
        """
        kwargs:
            instance_of: template_id (str)
            simulated: if the device is to be simulated (bool)
        """
        device_id = self.create_random_name(prefix="aztest", length=24)
        device_name = self.create_random_name(prefix="aztest", length=24)

        command = "iot central device create --app-id {} -d {} --device-name {}".format(
            self.app_id, device_id, device_name
        )

        checks = [
            self.check("displayName", device_name),
            self.check("id", device_id),
        ]

        checks.append(self.check("enabled", True))

        template = kwargs.get("template")
        if template:
            command = command + " --template {}".format(template)
            checks.append(self.check("template", template))

        simulated = bool(kwargs.get("simulated"))
        if simulated:
            command = command + " --simulated"

        checks.append(self.check("simulated", simulated))

        self.cmd(command, api_version=api_version, checks=checks)

        return (device_id, device_name)

    def get_app_scope_id(self, api_version):
        """
        Scope ID is taken from device credentials. If needed, create and delete a throwaway device
        so we can see the scope id.
        """
        if not self._scope_id:
            (device_id, _) = self._create_device(api_version=api_version)
            self._scope_id = self.cmd(
                "iot central device show-credentials -n {} -d {}".format(
                    self.app_id, device_id
                )
            ).get_output_in_json()["idScope"]

            self._delete_device(api_version=api_version, device_id=device_id)

        return self._scope_id

    def _create_users(self, api_version):
        users = []
        for role in Role:
            user_id = self.create_random_name(prefix="aztest", length=24)
            email = user_id + "@microsoft.com"
            command = "iot central user create --app-id {} --user-id {} -r {} --email {}".format(
                self.app_id,
                user_id,
                role.name,
                email,
            )

            checks = [
                self.check("id", user_id),
                self.check("email", email),
                self.check("type", UserType.email.value),
                self.check("roles[0].role", role.value),
            ]
            users.append(
                self.cmd(
                    command, api_version=api_version, checks=checks
                ).get_output_in_json()
            )

        return users

    def _delete_user(self, api_version, user_id) -> None:
        self.cmd(
            "iot central user delete --app-id {} --user-id {}".format(
                self.app_id, user_id
            ),
            api_version=api_version,
            checks=[self.check("result", "success")],
        )

    def _create_device_group(self, api_version, template_name, org_id):
        device_group_id = self.create_random_name(prefix="aztest", length=24)
        display_name = self.create_random_name(prefix="aztest", length=10)
        filter = f'"SELECT * FROM devices WHERE $template = \\"{template_name}\\""'
        description = self.create_random_name(prefix="aztest", length=30)
        organization = org_id

        command = f'''
            iot central device-group create \
            --app-id {self.app_id} \
            --device-group-id {device_group_id} \
            --display-name {display_name} \
            --filter {filter} \
            --description {description} \
            --organizations {organization}'''

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("displayName", display_name),
                self.check("description", description),
                self.check("filter", f'SELECT * FROM devices WHERE $template = \"{template_name}\"'),
                self.check("organizations[0]", organization),
            ],
        ).get_output_in_json()

    def _update_device_group(self, api_version, device_group_id):
        new_description = self.create_random_name(prefix="aztest", length=30)

        command = f'''
            iot central device-group update
            --app-id {self.app_id}
            --device-group-id {device_group_id}
            --description {new_description}'''

        update_result = self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("description", new_description),
            ],
        ).get_output_in_json()

        return (update_result, new_description)

    def _delete_device_group(self, api_version, device_group_id) -> None:
        self.cmd(
            "iot central device-group delete --app-id {} --device-group-id {}".format(
                self.app_id, device_group_id
            ),
            api_version=api_version,
            checks=[self.check("result", "success")],
        )

    def _create_device_attestation(self, api_version, device_id):
        command = f'''
            iot central device attestation create
            --app-id {self.app_id}
            --device-id {device_id}
            --content '{json.dumps(attestation_payload).replace("{", "{{").replace("}", "}}")}'
        '''

        return self.cmd(
            command,
            api_version=api_version,
        ).get_output_in_json()

    def _update_device_attestation(self, api_version, device_id):
        command = f'''
            iot central device attestation update
            --app-id {self.app_id}
            --device-id {device_id}
            --content '{json.dumps(attestation_payload_update).replace("{", "{{").replace("}", "}}")}'
        '''

        return self.cmd(
            command,
            api_version=api_version,
        ).get_output_in_json()

    def _update_device_properties(self, api_version, device_id):
        command = f'''
            iot central device twin update
            --app-id {self.app_id}
            --device-id {device_id}
            --content '{device_updated_properties_path}' '''
        return self.cmd(
            command,
            api_version=api_version,
        ).get_output_in_json()

    def _update_device_component_properties(self, api_version, device_id, component_name):
        command = f'''
            iot central device twin update
            --app-id {self.app_id}
            --device-id {device_id}
            --component-name {component_name}
            --content '{device_updated_component_properties_path}' '''
        return self.cmd(
            command,
            api_version=api_version,
        ).get_output_in_json()

    def _update_device_module_properties(self, api_version, device_id, module_name):
        command = f'''
            iot central device twin update
            --app-id {self.app_id}
            --device-id {device_id}
            --module-name {module_name}
            --content '{device_updated_properties_path}' '''
        return self.cmd(
            command,
            api_version=api_version,
        ).get_output_in_json()

    def _update_device_module_component_properties(self, api_version, device_id, module_name, component_name):
        command = f'''
            iot central device twin update
            --app-id {self.app_id}
            --device-id {device_id}
            --component-name {component_name}
            --module-name {module_name}
            --content '{device_updated_component_properties_path}' '''
        return self.cmd(
            command,
            api_version=api_version,
        ).get_output_in_json()

    def _create_api_tokens(self, api_version):
        tokens = []
        for role in Role:
            token_id = self.create_random_name(prefix="aztest", length=24)
            command = (
                "iot central api-token create --app-id {} --token-id {} -r {}".format(
                    self.app_id,
                    token_id,
                    role.name,
                )
            )

            checks = [
                self.check("id", token_id),
                self.check("roles[0].role", role.value),
            ]

            tokens.append(
                self.cmd(
                    command, api_version=api_version, checks=checks
                ).get_output_in_json()
            )
        return tokens

    def _delete_api_token(self, api_version, token_id) -> None:
        self.cmd(
            "iot central api-token delete --app-id {} --token-id {}".format(
                self.app_id, token_id
            ),
            api_version=api_version,
            checks=[self.check("result", "success")],
        )

    def _wait_for_provisioned(self, api_version, device_id):
        command = "iot central device show --app-id {} -d {}".format(
            self.app_id, device_id
        )

        while True:
            result = self.cmd(command, api_version=api_version)
            device = result.get_output_in_json()

            # return when its provisioned
            if device.get("provisioned"):
                return

            # wait 10 seconds for provisioning to complete
            time.sleep(10)

    def _delete_device(self, api_version, device_id) -> None:

        command = "iot central device delete --app-id {} -d {} ".format(
            self.app_id, device_id
        )

        self.cmd(
            command, api_version=api_version, checks=[self.check("result", "success")]
        )

    def _create_device_template(self, api_version, edge=False):
        if edge:
            template_path = edge_template_path_preview
        else:
            template_path = device_template_path

        template = utility.process_json_arg(
            template_path,
            argument_name="template_path",
        )

        template_name = template["displayName"]
        template_id = template_name + "id;1"

        if (
            edge
        ):  # check if template already exists as a create call does not work for edge templates
            # since deployment manifest cannot be changed
            try:
                command = "iot central device-template show --app-id {} --device-template-id {}".format(
                    self.app_id, template_id
                )
                result = self.cmd(command, api_version=api_version).get_output_in_json()

                if (
                    result
                    and result.get(self._get_template_id_key(api_version=api_version))
                    == template_id
                ):
                    return (template_id, template_name)
            except Exception:
                pass

        command = "iot central device-template create --app-id {} --device-template-id {} -k '{}'".format(
            self.app_id, template_id, template_path
        )

        result = self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("displayName", template_name),
            ],
        )
        json_result = result.get_output_in_json()

        assert (
            json_result[self._get_template_id_key(api_version=api_version)]
            == template_id
        )

        return (template_id, template_name)

    def _delete_device_template(self, api_version, template_id):
        attempts = range(0, 10)

        # retry logic to delete the template
        error = None
        for _ in attempts:
            try:
                error = None
                self.cmd(
                    command="iot central device-template delete --app-id {} --device-template-id {}".format(
                        self.app_id, template_id
                    ),
                    api_version=api_version,
                    checks=[self.check("result", "success")],
                )
                return
            except Exception as e:
                error = e
                # delete associated devices if any.
                devices = self.cmd(
                    command="iot central device list --app-id {}".format(self.app_id),
                    api_version=api_version,
                ).get_output_in_json()

                if devices:
                    for device in devices:
                        device_template = device["template"]
                        if device_template == template_id:
                            # delete attached children devices if any
                            children = []

                            list_children_command = "iot central device edge children list --app-id {} -d {}".format(
                                self.app_id, device["id"]
                            )
                            try:
                                children = self.cmd(
                                    list_children_command, api_version=api_version
                                ).get_output_in_json()
                            except Exception:
                                pass

                            for child in children:
                                try:
                                    self.cmd(
                                        "iot central device delete --app-id {} --device-id {}".format(
                                            self.app_id, child["id"]
                                        ),
                                        api_version=api_version,
                                    )
                                except Exception:
                                    pass

                            time.sleep(10)
                            try:
                                self.cmd(
                                    "iot central device delete --app-id {} --device-id {}".format(
                                        self.app_id, device["id"]
                                    ),
                                    api_version=api_version,
                                )
                            except Exception:
                                pass
                time.sleep(10)

        raise CLIInternalError(
            f"Device template {template_id} cannot be deleted."
            + (f" Error: {error}" if error is not None else "")
        )

    def _list_device_groups(self, api_version):
        command = "iot central device-group list --app-id {}".format(self.app_id)
        return self.cmd(command, api_version=api_version).get_output_in_json()

    def _list_roles(self, api_version):
        return self.cmd(
            "iot central role list --app-id {}".format(self.app_id),
            api_version=api_version,
        ).get_output_in_json()

    def _get_credentials(self, api_version, device_id):
        return self.cmd(
            "iot central device show-credentials --app-id {} -d {}".format(
                self.app_id, device_id
            ),
            api_version=api_version,
        ).get_output_in_json()

    def _get_validate_messages_output(
        self, device_id, enqueued_time, duration=60, max_messages=1, asserts=None
    ):
        if not asserts:
            asserts = []

        output = self.command_execute_assert(
            "iot central diagnostics validate-messages"
            " --app-id {} "
            " -d {} "
            " --et {} "
            " --duration {} "
            " --mm {} -y --style json".format(
                self.app_id, device_id, enqueued_time, duration, max_messages
            ),
            asserts,
        )

        if not output:
            output = ""

        return output

    def _get_monitor_events_output(
        self, api_version, device_id, enqueued_time, asserts=None
    ):
        if not asserts:
            asserts = []

        output = self.command_execute_assert(
            "iot central diagnostics monitor-events -n {} -d {} --et {} --to 1 -y".format(
                self.app_id, device_id, enqueued_time
            ),
            asserts,
        )

        if not output:
            output = ""

        return output

    def _create_fileupload(self, api_version, account_name=None, sasttl=None):
        command = (
            'iot central file-upload-config create --app-id {} -s "{}" -c "{}"'.format(
                self.app_id, self.storage_cstring, self.storage_container
            )
        )

        if account_name is not None:
            command += " --account {}".format(account_name)
        if sasttl is not None:
            command += " --sas-ttl {}".format(sasttl)

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("connectionString", self.storage_cstring),
                self.check("container", self.storage_container),
                self.check("account", None if account_name is None else account_name),
                self.check("state", "pending"),
                self.check(
                    "sasTtl", DEFAULT_FILE_UPLOAD_TTL if sasttl is None else sasttl
                ),
            ],
        ).get_output_in_json()

    def _delete_fileupload(self, api_version):
        command = "iot central file-upload-config delete --app-id {}".format(
            self.app_id
        )
        self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("result", "success"),
            ],
        )

    def _create_organization(self, api_version):
        org_id = self.create_random_name(prefix="aztest", length=24)
        command = "iot central organization create --app-id {} --org-id {}".format(
            self.app_id, org_id
        )

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("id", org_id),
            ],
        ).get_output_in_json()

    def _delete_organization(self, api_version, org_id):
        command = "iot central organization delete --app-id {} --org-id {}".format(
            self.app_id, org_id
        )
        self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("result", "success"),
            ],
        )

    def _create_enrollment_group(self, api_version):
        group_id = self.create_random_name(prefix="aztest", length=24)
        display_name = self.create_random_name(prefix="aztest", length=10)

        command = f'''
            iot central enrollment-group create
             --app-id {self.app_id}
             --group-id {group_id}
             --attestation 'symmetricKey'
             --display-name {display_name}
             --type 'iot'
        '''

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("id", group_id),
            ],
        ).get_output_in_json()

    def _update_enrollment_group(self, api_version, group_id):
        display_name = self.create_random_name(prefix="aztest", length=10)
        command = "iot central enrollment-group update \
            --app-id {} --group-id {}  --display-name {}".format(
            self.app_id, group_id, display_name
        )

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("id", group_id),
                self.check("displayName", display_name),
            ],
        ).get_output_in_json()

    def _delete_enrollment_group(self, api_version, group_id):
        command = "iot central enrollment-group delete --app-id {} --group-id {}".format(
            self.app_id, group_id
        )
        self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("result", "success"),
            ],
        )

    def _create_certs(self) -> dict:
        cert_output_dir = os.getcwd()
        if not os.path.isdir(cert_output_dir):
            os.makedirs(cert_output_dir)

        cert_name = "central_x509_" + generate_generic_id()
        root_cert_obj = create_certificate(
            subject=cert_name, valid_days=1, cert_output_dir=cert_output_dir
        )

        return {
            'cert_name': cert_name,
            'cert_output_dir': cert_output_dir,
            'root_cert_obj': root_cert_obj
        }

    def _create_enrollment_group_with_x509(self, api_version, cert_name):
        group_id = self.create_random_name(prefix="aztest", length=24)
        display_name = self.create_random_name(prefix="aztest", length=10)

        command = f'''
            iot central enrollment-group create
             --app-id {self.app_id}
             --group-id {group_id}
             --attestation 'x509'
             --cp {cert_name + CERT_ENDING}
             --display-name {display_name}
             --type 'iot'
        '''

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("id", group_id),
            ],
        ).get_output_in_json()

    def _create_enrollment_group_with_symmetric_key(self, api_version):
        group_id = self.create_random_name(prefix="aztest", length=24)
        display_name = self.create_random_name(prefix="aztest", length=10)

        command = f'''
            iot central enrollment-group create
             --app-id {self.app_id}
             --group-id {group_id}
             --attestation 'symmetricKey'
             --cp {attestation_payload['symmetricKey']['primaryKey']}
             --scp {attestation_payload['symmetricKey']['secondaryKey']}
             --display-name {display_name}
             --type 'iot'
        '''

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("id", group_id),
            ],
        ).get_output_in_json()

    def _generate_x509_verification_code(self, group_id, api_version):
        command = f'''
            iot central enrollment-group generate-verification-code
             --app-id {self.app_id}
             --group-id {group_id}
             --entry 'primary'
        '''
        return self.cmd(
            command,
            api_version=api_version,
        ).get_output_in_json()['verificationCode']

    def _verify_x509_certification(
        self,
        group_id,
        api_version,
        cert_output_dir,
        root_cert_obj,
        verification_code
    ):
        # Create verified certification
        create_certificate(
            subject=verification_code,
            valid_days=1,
            cert_output_dir=cert_output_dir,
            cert_object=root_cert_obj,
        )

        command = f'''
            iot central enrollment-group verify-certificate
             --app-id {self.app_id}
             --group-id {group_id}
             --cp {verification_code + CERT_ENDING}
        '''
        return self.cmd(
            command,
            api_version=api_version,
        ).get_output_in_json()

    def _remove_x509(self, group_id, api_version):
        command = f'''
            iot central enrollment-group update
             --app-id {self.app_id}
             --id {group_id}
             --entry 'primary'
             --remove-x509 'True'
        '''
        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("id", group_id),
            ],
        ).get_output_in_json()

    def _delete_test_certs(self, cert_output_dir):
        files_in_directory = os.listdir(cert_output_dir)
        filtered_files = [file for file in files_in_directory if file.endswith(".pem")]
        for file in filtered_files:
            os.remove(os.path.join(cert_output_dir, file))

    def _create_scheduled_job(self, api_version):
        # create a device group for scheduled job
        (template_id, template_name) = self._create_device_template(api_version=api_version)
        org = self._create_organization(api_version=api_version)
        device_group = self._create_device_group(api_version=api_version, template_name=template_name, org_id=org["id"])

        group_id = device_group["id"]
        job_id = self.create_random_name(prefix="aztest", length=10)
        display_name = self.create_random_name(prefix="aztest", length=10)
        scheduled_job_data[0]["target"] = template_id

        command = f'''
            iot central scheduled-job create
             --app-id {self.app_id}
             --job-id {job_id}
             --group-id {group_id}
             --job-name {display_name}
             --content '{json.dumps(scheduled_job_data).replace("{", "{{").replace("}", "}}")}'
             --schedule '{json.dumps(scheduled_job_schedule).replace("{", "{{").replace("}", "}}")}'
        '''

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("id", job_id),
                self.check("displayName", display_name),
                self.check("group", group_id),
            ],
        ).get_output_in_json()

    def _update_scheduled_job(self, api_version, job_id):
        display_name = self.create_random_name(prefix="aztest", length=10)
        command = f'''
            iot central scheduled-job update
             --app-id {self.app_id}
             --job-id {job_id}
             --job-name {display_name}
             --schedule '{json.dumps(scheduled_job_schedule_update).replace("{", "{{").replace("}", "}}")}'
        '''

        return self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("id", job_id),
                self.check("displayName", display_name),
            ],
        ).get_output_in_json()

    def _delete_scheduled_job(self, api_version, job_id):
        command = "iot central scheduled-job delete --app-id {} --job-id {}".format(
            self.app_id, job_id
        )
        self.cmd(
            command,
            api_version=api_version,
            checks=[
                self.check("result", "success"),
            ],
        )

    def _create_destination(self, api_version, dest_id):
        self.kwargs["authorization"] = json.dumps(
            {
                "type": "connectionString",
                "connectionString": self.storage_cstring,
                "containerName": self.storage_container,
            }
        )
        command = "iot central export destination create --app-id {} \
            --dest-id {} --type {} --name '{}' --authorization '{}'".format(
            self.app_id,
            dest_id,
            "blobstorage@v1",
            "Blob Storage",
            "{authorization}",
        )
        return self.cmd(
            command, api_version=api_version, checks=[self.check("id", dest_id)]
        ).get_output_in_json()

    def _delete_destination(self, api_version, dest_id):
        command = (
            "iot central export destination delete --app-id {} --dest-id {}".format(
                self.app_id, dest_id
            )
        )
        self.cmd(command, api_version=api_version)

    def _create_export(self, api_version, export_id, dest_id):

        self.kwargs["enrichments"] = json.dumps({"Simulated": {"path": "$simulated"}})
        self.kwargs["destinations"] = json.dumps([{"id": dest_id}])

        command = "iot central export create --app-id {} --export-id {} --name {} \
            --filter {} --source {} --enabled {} --enrichments '{}' --destinations '{}'".format(
            self.app_id,
            export_id,
            '"Test Export"',
            '"SELECT * FROM devices WHERE $simulated = true"',
            "Telemetry",
            "True",
            "{enrichments}",
            "{destinations}",
        )
        return self.cmd(
            command, api_version=api_version, checks=[self.check("id", export_id)]
        ).get_output_in_json()

    def _delete_export(self, api_version, export_id):
        command = "iot central export delete --app-id {} --export-id {}".format(
            self.app_id, export_id
        )
        self.cmd(command, api_version=api_version)

    def _create_storage_account(self):
        """
        Create a storage account and container if a storage account was not created yet and
        a resource group for the storage account is defined.
        Populate the following variables if needed:
          - storage_account_name
          - storage_container
          - storage_cstring
        """
        if self.app_rg:
            self.storage_account_name = STORAGE_ACCOUNT
            self.storage_container = STORAGE_CONTAINER

            self.storage_cstring = create_storage_account(
                cmd=super().cmd,
                account_name=self.storage_account_name,
                container_name=self.storage_container,
                rg=self.app_rg,
                resource_name=self.app_id,
                create_account=(not settings.env.azext_iot_teststorageaccount),
            )

    def _delete_storage_account(self):
        """
        Delete the storage account if it was created.
        """
        if not settings.env.azext_iot_teststorageaccount:
            self.cmd(
                "storage account delete -n {} -g {} -y".format(
                    self.storage_account_name, self.app_rg
                ),
                include_opt_args=False,
            )
        elif not settings.env.azext_iot_central_storage_container:
            self.cmd(
                "storage container delete -n {} --connection-string '{}'".format(
                    self.storage_account_name, self.storage_cstring
                ),
            )

    def _wait_for_storage_configured(self, api_version):
        command = "iot central file-upload-config show --app-id {}".format(self.app_id)

        while True:
            try:
                result = self.cmd(command, api_version=api_version)
            except Exception as e:
                if e.args[0] and "code" in e.args[0]:
                    err = dict(e.args[0])
                    if err["code"] == "NotFound":
                        # storage has been deleted
                        return
                    raise e
            file_upload = result.get_output_in_json()

            # return when its provisioned
            if file_upload.get("state") == "succeeded":
                return file_upload

            # wait 10 seconds for provisioning to complete
            time.sleep(10)

    def _appendOptionalArgsToCommand(self, command: str, api_version: str):
        if self.token:
            command += ' --token "{}"'.format(self.token)
        if self.dns_suffix:
            command += ' --central-dns-suffix "{}"'.format(self.dns_suffix)
        if api_version:
            command += " --api-version {}".format(api_version)
        return command

    def _get_template_id(self, api_version, template):
        return template["@id"]

    def _get_template_id_key(self, api_version):
        return "@id"

    def tearDown(self):
        if not settings.env.azext_iot_central_app_id:
            self.cmd(
                "iot central app delete -n {} -g {} -y".format(self.app_id, self.app_rg)
            )
