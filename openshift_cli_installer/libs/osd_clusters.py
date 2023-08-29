import click
from ocm_python_wrapper.cluster import Cluster, Clusters

from openshift_cli_installer.utils.helpers import (
    add_cluster_info_to_cluster_data,
    dump_cluster_data_to_file,
    get_cluster_object,
)


def osd_check_existing_clusters(clusters):
    clients = {}
    for _cluster in clusters:
        clients.setdefault(_cluster["ocm-env"], _cluster["ocm-client"])

    all_duplicate_cluster_names = []
    for client in clients.values():
        for _cluster in Clusters(client=client).get():
            duplicate_cluster_names = [
                cluster_data["name"]
                for cluster_data in clusters
                if cluster_data["name"] == _cluster.name
            ]
            if duplicate_cluster_names:
                all_duplicate_cluster_names.extend(duplicate_cluster_names)

    if all_duplicate_cluster_names:
        click.secho(
            f"At least one cluster already exists: {all_duplicate_cluster_names}",
            fg="red",
        )
        raise click.Abort()


def osd_create_cluster(cluster_data):
    try:
        Cluster.provision_osd_aws(
            wait_for_ready=True,
            wait_timeout=cluster_data["timeout"],
            client=cluster_data["ocm-client"],
            name=cluster_data["name"],
            region=cluster_data["region"],
            ocp_version=cluster_data["version"],
            access_key_id=cluster_data["aws-access-key-id"],
            account_id=cluster_data["aws-account-id"],
            secret_access_key=cluster_data["aws-secret-access-key"],
            replicas=cluster_data["replicas"],
            compute_machine_type=cluster_data["compute-machine-type"],
            multi_az=cluster_data["multi-az"],
            channel_group=cluster_data["channel-group"],
            expiration_time=cluster_data.get("expiration-time"),
        )
        cluster_data = add_cluster_info_to_cluster_data(
            cluster_data=cluster_data,
            cluster_object=get_cluster_object(cluster_data=cluster_data),
        )
        dump_cluster_data_to_file(cluster_data=cluster_data)

    except Exception as ex:
        click.secho(
            f"Failed to run cluster create for cluster {cluster_data['name']}\n{ex}",
            fg="red",
        )

        osd_delete_cluster(cluster_data=cluster_data)
        raise click.Abort()

    click.echo(f"Cluster {cluster_data['name']} created successfully")


def osd_delete_cluster(cluster_data):
    try:
        Cluster(
            client=cluster_data["ocm-client"],
            name=cluster_data["name"],
        ).delete(wait=True, timeout=cluster_data["timeout"])
    except Exception as ex:
        click.secho(
            f"Failed to run cluster delete cluster {cluster_data['name']}\n{ex}",
            fg="red",
        )
        raise click.Abort()
