from datetime import datetime, timedelta

import rosa.cli
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
    command = "create custer --sts "
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
        ocm_env=cluster_data["ocm-env"],
        token=cluster_data["ocm-token"],
    )


def rosa_delete_cluster(cluster_data):
    command = f"delete cluster --cluster-name {cluster_data['cluster-name']}"
    rosa.cli.execute(
        command=command,
        ocm_env=cluster_data["ocm-env"],
        token=cluster_data["ocm-token"],
    )
