# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
shared: Define shared data types(enums); hub and dps connection string functions.

"""

from enum import Enum


class SdkType(Enum):
    """
    Target SDK for interop.
    """

    device_query_sdk = 0
    modules_sdk = 1
    device_twin_sdk = 2
    device_msg_sdk = 3
    custom_sdk = 4
    dps_sdk = 5
    device_sdk = 6
    service_sdk = 7


class EntityStatusType(Enum):
    """
    Resource status.
    """

    disabled = "disabled"
    enabled = "enabled"


class SettleType(Enum):
    """
    Settlement state of C2D message.
    """

    complete = "complete"
    abandon = "abandon"
    reject = "reject"


class DeviceAuthType(Enum):
    """
    Client based Device Authorization type.
    """

    shared_private_key = "shared_private_key"
    x509_thumbprint = "x509_thumbprint"
    x509_ca = "x509_ca"


class DeviceAuthApiType(Enum):
    """
    API based Device Authorization type.
    """

    sas = "sas"
    selfSigned = "selfSigned"
    certificateAuthority = "certificateAuthority"


class KeyType(Enum):
    """
    Shared private key.
    """

    primary = "primary"
    secondary = "secondary"


class AttestationType(Enum):
    """
    Type of atestation (TMP or certificate based).
    """

    tpm = "tpm"
    x509 = "x509"
    symmetricKey = "symmetricKey"


class ProtocolType(Enum):
    """
    Device message protocol.
    """

    http = "http"
    mqtt = "mqtt"


class AckType(Enum):
    """
    Type of request for acknowledgement of c2d message.
    """

    positive = "positive"
    negative = "negative"
    full = "full"


class QueryType(Enum):
    """
    Type of query.
    """

    twin = "twin"
    job = "job"


class MetricType(Enum):
    """
    Type of metric for IoT configurations.
    """

    system = "system"
    user = "user"


class ReprovisionType(Enum):
    """
    Type of re-provisioning for device data to different IoT Hub.
    """

    reprovisionandmigratedata = "reprovisionandmigratedata"
    reprovisionandresetdata = "reprovisionandresetdata"
    never = "never"


class AllocationType(Enum):
    """
    Type of allocation for device assigned to the Hub.
    """

    hashed = "hashed"
    geolatency = "geoLatency"
    static = "static"
    custom = "custom"


class DistributedTracingSamplingModeType(Enum):
    """
    Enable distributed tracing to add correlation IDs to messages.
    """

    off = "off"
    on = "on"


class ConfigType(Enum):
    """
    Type of configuration deployment.
    """

    edge = "edge"
    layered = "layered"
    adm = "adm"


class JobCreateType(Enum):
    """
    Type of creatable IoT Hub job v2
    """

    scheduleUpdateTwin = "scheduleUpdateTwin"
    scheduleDeviceMethod = "scheduleDeviceMethod"


class JobType(Enum):
    """
    Type of IoT Hub job
    """

    exportDevices = "export"
    importDevices = "import"
    scheduleUpdateTwin = "scheduleUpdateTwin"
    scheduleDeviceMethod = "scheduleDeviceMethod"


class JobVersionType(Enum):
    """
    Type of IoT Hub job
    """

    v1 = "v1"
    v2 = "v2"


class JobStatusType(Enum):
    """
    Type of IoT Hub job status.
    """

    unknown = "unknown"
    enqueued = "enqueued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    scheduled = "scheduled"
    queued = "queued"


class AuthenticationType(Enum):
    """
    Route or endpoint authentication mechanism.
    """

    keyBased = "key"
    identityBased = "identity"


class AuthenticationTypeDataplane(Enum):
    """
    Use a policy key or Oauth token from Azure AD.
    """

    key = "key"
    login = "login"


class RenewKeyType(Enum):
    """
    Target key type for regeneration.
    """

    primary = KeyType.primary.value
    secondary = KeyType.secondary.value
    swap = "swap"


class IoTHubStateType(Enum):
    """
    IoT Hub State Property
    """

    Activating = "Activating"
    Active = "Active"
    Deleting = "Deleting"
    Deleted = "Deleted"
    ActivationFailed = "ActivationFailed"
    DeletionFailed = "DeletionFailed"
    Transitioning = "Transitioning"
    Suspending = "Suspending"
    Suspended = "Suspended"
    Resuming = "Resuming"
    FailingOver = "FailingOver"
    FailoverFailed = "FailoverFailed"
    TenantCommitted = "TenantCommitted"
    Restoring = "Restoring"
    IdentityCreated = "IdentityCreated"
    KeyEncryptionKeyRevoking = "KeyEncryptionKeyRevoking"
    KeyEncryptionKeyRevoked = "KeyEncryptionKeyRevoked"
    ReActivating = "ReActivating"


class IoTDPSStateType(Enum):
    """
    IoT Hub Device Provisioning Service State Property
    """
    Activating = "Activating"
    ActivationFailed = "ActivationFailed"
    Active = "Active"
    Deleted = "Deleted"
    Deleting = "Deleting"
    DeletionFailed = "DeletionFailed"
    FailingOver = "FailingOver"
    FailoverFailed = "FailoverFailed"
    Resuming = "Resuming"
    Suspended = "Suspended"
    Suspending = "Suspending"
    Transitioning = "Transitioning"


class ConnectionStringParser(Enum):
    """
        All connection string parser with respective functions
    """
    from azext_iot.common._azure import (
        parse_iot_device_connection_string,
        parse_iot_device_module_connection_string,
        parse_iot_hub_connection_string
    )

    Module = parse_iot_device_module_connection_string
    Device = parse_iot_device_connection_string
    IotHub = parse_iot_hub_connection_string


class DiscoveryResourceType(Enum):
    """
    Resource types supported by discovery.
    """
    IoTHub = "IoT Hub"
    DPS = "IoT Hub Device Provisioning Service"


class SHAHashVersions(Enum):
    """
    Supported SHA types for generating the certificate thumbprint.
    """
    SHA1 = 1
    SHA256 = 256
