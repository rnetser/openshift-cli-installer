import os
import shlex

import click
from ocp_resources.managed_cluster import ManagedCluster
from ocp_resources.multi_cluster_hub import MultiClusterHub
from ocp_resources.secret import Secret
from ocp_resources.utils import TimeoutWatch
from ocp_utilities.utils import run_command

from openshift_cli_installer.utils.clusters import get_kubeconfig_path
from openshift_cli_installer.utils.const import (
    AWS_STR,
    ERROR_LOG_COLOR,
    SUCCESS_LOG_COLOR,
)
from openshift_cli_installer.utils.general import tts


def install_acm(
    hub_cluster_data,
    ocp_client,
    private_ssh_key_file,
    public_ssh_key_file,
    registry_config_file,
    timeout_watch,
    acm_cluster_kubeconfig,
):
    cluster_name = hub_cluster_data["name"]
    click.echo(f"Installing ACM on cluster {cluster_name}")
    run_command(
        command=shlex.split(f"cm install acm --kubeconfig {acm_cluster_kubeconfig}"),
    )
    cluster_hub = MultiClusterHub(
        client=ocp_client,
        name="multiclusterhub",
        namespace="open-cluster-management",
    )
    cluster_hub.wait_for_status(
        status=cluster_hub.Status.RUNNING, timeout=timeout_watch.remaining_time()
    )
    labels = {
        f"{cluster_hub.api_group}/credentials": "",
        f"{cluster_hub.api_group}/type": AWS_STR,
    }

    with open(private_ssh_key_file, "r") as fd:
        ssh_privatekey = fd.read()

    with open(public_ssh_key_file, "r") as fd:
        ssh_publickey = fd.read()

    secret_data = {
        "aws_access_key_id": hub_cluster_data["aws-access-key-id"],
        "aws_secret_access_key": hub_cluster_data["aws-secret-access-key"],
        "pullSecret": registry_config_file,
        "ssh-privatekey": ssh_privatekey,
        "ssh-publickey": ssh_publickey,
    }
    secret = Secret(
        client=ocp_client,
        name="aws-creds",
        namespace="default",
        label=labels,
        string_data=secret_data,
    )
    secret.deploy(wait=True)
    click.secho(
        f"ACM installed successfully on Cluster {cluster_name}",
        fg=SUCCESS_LOG_COLOR,
    )


def attach_cluster_to_acm(
    hub_cluster_name,
    managed_acm_cluster_name,
    acm_hub_ocp_client,
    acm_cluster_kubeconfig,
    managed_acm_cluster_kubeconfig,
    timeout_watch,
):
    click.echo(f"Attach {managed_acm_cluster_name} to ACM hub {hub_cluster_name}")
    run_command(
        command=shlex.split(
            f"cm --kubeconfig {acm_cluster_kubeconfig} attach cluster --cluster"
            f" {managed_acm_cluster_name} --cluster-kubeconfig"
            f" {managed_acm_cluster_kubeconfig}  --wait"
        ),
        check=False,
        verify_stderr=False,
    )

    managed_cluster = ManagedCluster(
        client=acm_hub_ocp_client, name=managed_acm_cluster_name
    )
    managed_cluster.wait_for_condition(
        condition="ManagedClusterImportSucceeded",
        status=managed_cluster.Condition.Status.TRUE,
        timeout=timeout_watch.remaining_time(),
    )
    click.secho(
        f"{managed_acm_cluster_name} successfully attached to ACM Cluster"
        f" {hub_cluster_name}",
        fg=SUCCESS_LOG_COLOR,
    )


def install_and_attach_for_acm(
    managed_clusters,
    private_ssh_key_file,
    ssh_key_file,
    registry_config_file,
    clusters_install_data_directory,
):
    for hub_cluster_data in managed_clusters:
        timeout_watch = hub_cluster_data.get(
            "timeout-watch", TimeoutWatch(timeout=tts(ts="15m"))
        )
        ocp_client = hub_cluster_data["ocp-client"]
        acm_cluster_kubeconfig = get_kubeconfig_path(cluster_data=hub_cluster_data)

        if hub_cluster_data.get("acm"):
            install_acm(
                hub_cluster_data=hub_cluster_data,
                ocp_client=ocp_client,
                private_ssh_key_file=private_ssh_key_file,
                public_ssh_key_file=ssh_key_file,
                registry_config_file=registry_config_file,
                timeout_watch=timeout_watch,
                acm_cluster_kubeconfig=acm_cluster_kubeconfig,
            )

        for _managed_acm_clusters in hub_cluster_data.get("acm-clusters", []):
            _managed_cluster_name = _managed_acm_clusters["name"]
            managed_acm_cluster_kubeconfig = get_managed_acm_cluster_kubeconfig(
                managed_acm_cluster_name=_managed_cluster_name,
                managed_cluster_platform=_managed_acm_clusters["platform"],
                clusters_install_data_directory=clusters_install_data_directory,
            )

            attach_cluster_to_acm(
                managed_acm_cluster_name=_managed_cluster_name,
                hub_cluster_name=hub_cluster_data["name"],
                acm_hub_ocp_client=ocp_client,
                acm_cluster_kubeconfig=acm_cluster_kubeconfig,
                managed_acm_cluster_kubeconfig=managed_acm_cluster_kubeconfig,
                timeout_watch=timeout_watch,
            )


def get_managed_acm_cluster_kubeconfig(
    managed_acm_cluster_name,
    managed_cluster_platform,
    clusters_install_data_directory,
):
    managed_acm_cluster_kubeconfig = get_cluster_kubeconfig_from_install_dir(
        clusters_install_data_directory=clusters_install_data_directory,
        cluster_name=managed_acm_cluster_name,
        cluster_platform=managed_cluster_platform,
    )

    if not managed_acm_cluster_kubeconfig:
        click.secho(
            f"No kubeconfig found for {managed_acm_cluster_name}", fg=ERROR_LOG_COLOR
        )
        raise click.Abort()

    return managed_acm_cluster_kubeconfig


def get_cluster_kubeconfig_from_install_dir(
    clusters_install_data_directory, cluster_name, cluster_platform
):
    cluster_install_dir = os.path.join(
        clusters_install_data_directory, cluster_platform, cluster_name
    )
    if not os.path.exists(cluster_install_dir):
        click.secho(
            f"Install dir {cluster_install_dir} not found for {cluster_name}",
            fg=ERROR_LOG_COLOR,
        )
        raise click.Abort()

    return os.path.join(cluster_install_dir, "auth", "kubeconfig")
