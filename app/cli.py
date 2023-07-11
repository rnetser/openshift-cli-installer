import multiprocessing
import os

import click
from clouds.aws.aws_utils import set_and_verify_aws_credentials
from libs.aws_ipi_clusters import (
    create_install_config_file,
    create_or_destroy_aws_ipi_cluster,
    download_openshift_install_binary,
    generate_cluster_dir_path,
)
from libs.rosa_clusters import (
    prepare_clusters_data,
    rosa_create_cluster,
    rosa_delete_cluster,
)
from utils.click_dict_type import DictParamType
from utils.const import AWS_MANAGED_STR, AWS_STR, HYPERSHIFT_STR


def abort_no_ocm_token(ocm_token):
    if not ocm_token:
        click.echo("--ocm-token is required for managed cluster")
        raise click.Abort()


def verify_processes_passed(processes, action):
    failed_processes = {}

    for _proc in processes:
        _proc.join()
        if _proc.exitcode != 0:
            failed_processes[_proc.name] = _proc.exitcode

    if failed_processes:
        click.echo(f"Some jobs failed to {action}: {failed_processes}\n")
        raise click.Abort()


def create_openshift_cluster(cluster_data, s3_bucket_name=None, s3_bucket_path=None):
    cluster_platform = cluster_data["platform"]
    if cluster_platform == AWS_STR:
        create_or_destroy_aws_ipi_cluster(
            cluster_data=cluster_data,
            action="create",
            s3_bucket_name=s3_bucket_name,
            s3_bucket_path=s3_bucket_path,
        )

    elif cluster_platform in (AWS_MANAGED_STR, HYPERSHIFT_STR):
        rosa_create_cluster(cluster_data=cluster_data)


def destroy_openshift_cluster(cluster_data):
    cluster_platform = cluster_data["platform"]
    if cluster_platform == AWS_STR:
        create_or_destroy_aws_ipi_cluster(cluster_data=cluster_data, action="destroy")

    elif cluster_platform in (AWS_MANAGED_STR, HYPERSHIFT_STR):
        rosa_delete_cluster(cluster_data=cluster_data)


@click.command()
@click.option(
    "-a",
    "--action",
    type=click.Choice(["create", "destroy"]),
    help="Action to perform Openshift cluster/s",
    required=True,
)
@click.option(
    "-p",
    "--parallel",
    help="Run clusters install/uninstall in parallel",
    is_flag=True,
    show_default=True,
)
@click.option(
    "--clusters-install-data-directory",
    help="""
\b
Path to cluster install data.
    For install this will be used to store the install data.
    For uninstall this will be used to uninstall the cluster.
    Also used to store clusters kubeconfig
""",
    default=os.environ.get(
        "CLUSTER_INSTALL_DATA_DIRECTORY",
        "/openshift-cli-installer/clusters-install-data",
    ),
    type=click.Path(),
    show_default=True,
    required=True,
)
@click.option(
    "--pull-secret-file",
    help="""
    \b
Path to pull secret json file, can be obtained from console.redhat.com.
(Needed only for AWS IPI clusters)
    """,
    default=os.environ.get("PULL_SECRET"),
    type=click.Path(exists=True),
    show_default=True,
)
@click.option(
    "--s3-bucket-name",
    help="S3 bucket name to store install folder backups",
    show_default=True,
)
@click.option(
    "--s3-bucket-path",
    help="S3 bucket path to store the backups",
    show_default=True,
)
@click.option(
    "--ocm-env",
    help="OCM env to log in into. needed for managed AWS cluster",
    type=click.Choice(["stage", "production"]),
    default="stage",
    show_default=True,
)
@click.option(
    "--ocm-token",
    help="OCM token, needed for managed AWS cluster.",
    default=os.environ.get("OCM_TOKEN"),
)
@click.option(
    "-c",
    "--cluster",
    type=DictParamType(),
    help="""
\b
Cluster/s to install.
Format to pass is:
    'name=cluster1;base_domain=aws.domain.com;platform=aws;region=us-east-2;version=4.14.0-ec.2'
Required parameters:
    name: Cluster name.
    base_domain: Base domain for the cluster.
    platform: Cloud platform to install the cluster on. (Currently only AWS IPI supported).
    region: Region to use for the cloud platform.
    version: Openshift cluster version to install

Check install-config-template.j2 for variables that can be overwritten by the user.
For example:
    fips=true
    worker_flavor=m5.xlarge
    worker_replicas=6
    """,
    required=True,
    multiple=True,
)
def main(
    action,
    pull_secret_file,
    parallel,
    cluster,
    clusters_install_data_directory,
    s3_bucket_name,
    s3_bucket_path,
    ocm_token,
    ocm_env,
):
    """
    Create/Destroy Openshift cluster/s
    """
    clusters = []
    kwargs = {}
    create = action == "create"
    aws_ipi_clusters = [
        _cluster for _cluster in cluster if _cluster["platform"] == AWS_STR
    ]
    aws_managed_clusters = [
        _cluster
        for _cluster in cluster
        if _cluster["platform"] in (AWS_MANAGED_STR, HYPERSHIFT_STR)
    ]
    if aws_ipi_clusters or aws_managed_clusters:
        set_and_verify_aws_credentials()

    if aws_ipi_clusters:
        clusters = generate_cluster_dir_path(
            clusters=aws_ipi_clusters, base_directory=clusters_install_data_directory
        )
        clusters = download_openshift_install_binary(
            clusters=clusters, pull_secret_file=pull_secret_file
        )
        if create:
            kwargs.update(
                {"s3_bucket_name": s3_bucket_name, "s3_bucket_path": s3_bucket_path}
            )
            clusters = create_install_config_file(
                clusters=cluster, pull_secret_file=pull_secret_file
            )

    if aws_managed_clusters:
        abort_no_ocm_token(ocm_token)
        clusters = generate_cluster_dir_path(
            clusters=aws_managed_clusters,
            base_directory=clusters_install_data_directory,
        )
        clusters = prepare_clusters_data(
            clusters=clusters,
            ocm_token=ocm_token,
            ocm_env=ocm_env,
        )

    processes = []
    action_func = create_openshift_cluster if create else destroy_openshift_cluster

    for _cluster in clusters:
        kwargs["cluster_data"] = _cluster
        if parallel:
            proc = multiprocessing.Process(
                name=f"{_cluster['name']}---{action}",
                target=action_func,
                kwargs=kwargs,
            )
            processes.append(proc)
            proc.start()

        else:
            action_func(**kwargs)

    if processes:
        verify_processes_passed(processes=processes, action=action)


if __name__ == "__main__":
    main()
