import copy
import json
import multiprocessing
import os
import shlex
from pathlib import Path

import click
import yaml
from click_dict_type import DictParamType
from clouds.aws.aws_utils import set_and_verify_aws_credentials
from ocp_utilities.utils import run_command


def generate_cluster_dir_path(clusters, base_directory):
    for _cluster in clusters:
        cluster_name = _cluster["name"]
        platform = _cluster["platform"]
        _cluster["install-dir"] = os.path.join(base_directory, platform, cluster_name)
    return clusters


def verify_jobs_passed(jobs, action):
    failed_jobs = {}
    for job in jobs:
        job.start()

        for _job in jobs:
            _job.join()
            if _job.exitcode != 0:
                failed_jobs[_job.name] = _job.exitcode

        if failed_jobs:
            click.echo(f"Some jobs failed to {action}: {failed_jobs}\n")
            raise click.Abort()


def update_base_install_config(pull_secret_file):
    base_install_config = get_base_install_config_data()
    base_install_config["pullSecret"] = json.dumps(
        get_pull_secret_data(pull_secret_file=pull_secret_file)
    )
    base_install_config["sshKey"] = get_local_ssh_key()
    return base_install_config


def download_openshift_install(version, pull_secret_file):
    binary_dir = os.path.join("/tmp", version)
    openshift_install_str = "openshift-install"
    run_command(
        command=shlex.split(
            "oc adm release extract "
            f"quay.io/openshift-release-dev/ocp-release:{version}-x86_64 "
            f"--command={openshift_install_str} --to={binary_dir} --registry-config={pull_secret_file}"
        ),
        check=False,
    )
    return os.path.join(binary_dir, openshift_install_str)


def install_openshift(cluster_data, pull_secret_file):
    directory = cluster_data["install-dir"]
    version = cluster_data["version"]
    binary_path = download_openshift_install(
        version=version, pull_secret_file=pull_secret_file
    )
    return run_command(
        command=shlex.split(f"{binary_path} create cluster --dir {directory}"),
        capture_output=False,
    )[0]


def uninstall_openshift(cluster_data, pull_secret_file):
    directory = cluster_data["install-dir"]
    version = cluster_data["version"]
    binary_path = download_openshift_install(
        version=version, pull_secret_file=pull_secret_file
    )
    return run_command(
        command=shlex.split(f"{binary_path} destroy cluster --dir {directory}"),
        capture_output=False,
    )[0]


def create_install_config_file(
    clusters, base_install_config, clusters_install_data_directory
):
    for _cluster in clusters:
        base_install_config_copy = copy.deepcopy(base_install_config)
        cluster_name = _cluster["name"]
        install_dir = _cluster["install-dir"]

        base_install_config_copy["metadata"]["name"] = cluster_name
        base_install_config_copy["baseDomain"] = _cluster["baseDomain"]
        base_install_config_copy["platform"] = {
            _cluster["platform"]: {"region": _cluster["region"]}
        }
        Path(install_dir).mkdir(parents=True, exist_ok=True)
        with open(os.path.join(install_dir, "install-config.yaml"), "w") as fd:
            fd.write(yaml.dump(base_install_config_copy))

    return clusters


def get_pull_secret_data(pull_secret_file):
    with open(pull_secret_file) as fd:
        return json.load(fd)


def get_base_install_config_data():
    with open("app/manifests/install-config.yaml") as fd:
        return yaml.safe_load(fd)


def set_debug_os_flags():
    os.environ["OCM_PYTHON_WRAPPER_LOG_LEVEL"] = "DEBUG"
    os.environ["OPENSHIFT_PYTHON_WRAPPER_LOG_LEVEL"] = "DEBUG"


def get_local_ssh_key():
    with open(os.path.expanduser("~/.ssh/id_rsa.pub")) as fd:
        return fd.read().strip()


@click.command()
@click.option("-i", "--install", is_flag=True, help="Install Openshift cluster/s")
@click.option("-u", "--uninstall", is_flag=True, help="Uninstall Openshift cluster/s")
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
Path to cluster install data
    For install this will be used to store the install data.
    For uninstall this will be used to uninstall the cluster and must be provided.
""",
    default=os.environ.get(
        "CLUSTER_INSTALL_DATA_DIRECTORY",
        "/openshift-cli-installer/clusters-install-data",
    ),
    type=click.Path(exists=True),
    show_default=True,
)
@click.option(
    "--pull-secret-file",
    help="Path to pull secret json file, can be obtained from console.redhat.com",
    required=True,
    default=os.environ.get("PULL_SECRET"),
    type=click.Path(exists=True),
    show_default=True,
)
@click.option(
    "-c",
    "--cluster",
    type=DictParamType(),
    help="""
\b
Cluster/s to install.
Format to pass is:
    'name=cluster1;baseDomain=aws.domain.com;platform=aws;region=us-east-2;version=4.14.0-ec.2'
Required parameters:
    name: Cluster name.
    baseDomain: Base domain for the cluster.
    platform: Cloud platform to install the cluster on. (Currently only AWS supported).
    region: Region to use for the cloud platform.
    version: Openshift cluster version to install

Every parameter in install-config.yaml can be override by the user.
For example:
    fips=true
    compute_platform_aws_type=m5.xlarge
    """,
    required=True,
    multiple=True,
)
@click.option("--debug", help="Enable debug logs", is_flag=True)
def main(
    install,
    uninstall,
    pull_secret_file,
    parallel,
    cluster,
    debug,
    clusters_install_data_directory,
):
    """
    Install/Uninstall Openshift cluster/s
    """
    set_and_verify_aws_credentials()
    if not (install or uninstall):
        raise ValueError("One of install/uninstall must be specified")

    if debug:
        set_debug_os_flags()

    base_install_config = update_base_install_config(pull_secret_file=pull_secret_file)
    clusters = generate_cluster_dir_path(
        clusters=cluster, base_directory=clusters_install_data_directory
    )
    if install:
        clusters = create_install_config_file(
            clusters=cluster,
            base_install_config=base_install_config,
            clusters_install_data_directory=clusters_install_data_directory,
        )

    jobs = []
    action = "install" if install else "uninstall"

    for _cluster in clusters:
        kwargs = {"cluster_data": _cluster, "pull_secret_file": pull_secret_file}
        if parallel:
            job = multiprocessing.Process(
                name=f"{_cluster['name']}---{action}",
                target=install_openshift if install else uninstall_openshift,
                kwargs=kwargs,
            )
            jobs.append(job)
            job.start()

        else:
            install_openshift(**kwargs) if install else uninstall_openshift(**kwargs)

    verify_jobs_passed(jobs=jobs, action=action)


if __name__ == "__main__":
    main()
