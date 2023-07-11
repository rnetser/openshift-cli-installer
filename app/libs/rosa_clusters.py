import os
from datetime import datetime, timedelta

import rosa.cli
from ocm_python_wrapper.cluster import Cluster
from ocm_python_wrapper.ocm_client import OCMPythonClient
from utils.const import HYPERSHIFT_STR


def prepare_clusters_data(clusters, ocm_token, ocm_env):
    for _cluster in clusters:
        _cluster["cluster-name"] = _cluster["name"]
        _cluster["ocm-token"] = ocm_token
        _cluster["ocm-env"] = ocm_env
        if _cluster["platform"] == HYPERSHIFT_STR:
            _cluster["hosted-cp"] = "true"

        expiration_time = _cluster.get("expiration-time")
        if expiration_time:
            _cluster[
                "expiration-time"
            ] = f"{(datetime.now() + timedelta(hours=expiration_time)).isoformat()}Z"

    return clusters


def rosa_create_cluster(cluster_data):
    hosted_cp_arg = "--hosted-cp"
    ignore_keys = ("name", "platform", "ocm-env", "ocm-token")
    ocm_token = cluster_data["ocm-token"]
    ocm_env = cluster_data["ocm-env"]
    ocm_env_url = (
        None if ocm_env == "production" else f"https://api.{ocm_env}.openshift.com"
    )
    command = "create cluster --sts "
    command_kwargs = {
        f"--{_key}={_val}"
        for _key, _val in cluster_data.items()
        if _key not in ignore_keys
    }
    for cmd in command_kwargs:
        if hosted_cp_arg in cmd:
            command += f"{hosted_cp_arg} "
        else:
            command += f"{cmd} "

    rosa.cli.execute(
        command=command,
        ocm_env=ocm_env_url,
        token=ocm_token,
        aws_region=cluster_data["region"],
    )
    ocm_client = OCMPythonClient(
        token=ocm_token,
        endpoint="https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token",
        api_host=ocm_env,
    )
    cluster_object = Cluster(
        client=ocm_client.client, name=cluster_data["cluster-name"]
    )
    with open(
        os.path.join(cluster_data["install-dir"], "auth", "kubeconfig"), "w"
    ) as fd:
        fd.write(cluster_object.kubeconfig)

    # TODO: wait for the cluster to be ready
    # oc get jobs -n openshift-monitoring osd-cluster-ready


def rosa_delete_cluster(cluster_data):
    command = f"delete cluster --cluster-name {cluster_data['cluster-name']}"
    rosa.cli.execute(
        command=command,
        ocm_env=cluster_data["ocm-env"],
        token=cluster_data["ocm-token"],
    )
    # TODO: wait for the cluster to be deleted and clean extra resources after
