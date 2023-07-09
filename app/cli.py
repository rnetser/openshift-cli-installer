import json
import multiprocessing
import os
import shlex
from pathlib import Path

import click
import yaml
from click_dict_type import DictParamType
from clouds.aws.aws_utils import set_and_verify_aws_credentials
from jinja2 import DebugUndefined, Environment, FileSystemLoader, meta
from ocp_utilities.utils import run_command


def get_install_config_j2_template(cluster_dict):
    template_file = "install-config-template.j2"
    env = Environment(
        loader=FileSystemLoader("app/manifests/"),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=DebugUndefined,
    )

    template = env.get_template(name=template_file)
    rendered = template.render(cluster_dict)
    undefined_variables = meta.find_undeclared_variables(env.parse(rendered))
    if undefined_variables:
        click.echo(f"The following variables are undefined: {undefined_variables}")
        raise click.Abort()

    return yaml.safe_load(rendered)


def generate_cluster_dir_path(clusters, base_directory):
    for _cluster in clusters:
        _cluster["install-dir"] = os.path.join(
            base_directory, _cluster["platform"], _cluster["name"]
        )
    return clusters


def verify_processes_passed(processes, action):
    failed_processes = {}

    for _proc in processes:
        _proc.join()
        if _proc.exitcode != 0:
            failed_processes[_proc.name] = _proc.exitcode

    if failed_processes:
        click.echo(f"Some jobs failed to {action}: {failed_processes}\n")
        raise click.Abort()


def download_openshift_install_binary(clusters, pull_secret_file):
    versions = set()
    openshift_install_str = "openshift-install"

    for cluster in clusters:
        versions.add(cluster["version"])

    for version in versions:
        binary_dir = os.path.join("/tmp", version)
        clusters = [_cluster for _cluster in clusters if _cluster["version"] == version]
        for cluster in clusters:
            cluster["openshift-install-binary"] = os.path.join(
                binary_dir, openshift_install_str
            )

        run_command(
            command=shlex.split(
                "oc adm release extract "
                f"quay.io/openshift-release-dev/ocp-release:{version}-x86_64 "
                f"--command={openshift_install_str} --to={binary_dir} --registry-config={pull_secret_file}"
            ),
            check=False,
        )

    return clusters


def create_or_destroy_cluster(cluster_data, action):
    directory = cluster_data["install-dir"]
    binary_path = cluster_data["openshift-install-binary"]
    return run_command(
        command=shlex.split(f"{binary_path} {action} cluster --dir {directory}"),
        capture_output=False,
    )[0]


def install_openshift(cluster_data):
    create_or_destroy_cluster(cluster_data=cluster_data, action="create")


def uninstall_openshift(cluster_data):
    create_or_destroy_cluster(cluster_data=cluster_data, action="destroy")


def create_install_config_file(clusters, pull_secret_file):
    ssh_key = get_local_ssh_key()
    pull_secret = json.dumps(get_pull_secret_data(pull_secret_file=pull_secret_file))
    for _cluster in clusters:
        install_dir = _cluster["install-dir"]
        _cluster["pull_secret"] = pull_secret
        _cluster["ssh_key"] = ssh_key

        cluster_install_config = get_install_config_j2_template(cluster_dict=_cluster)
        Path(install_dir).mkdir(parents=True, exist_ok=True)

        with open(os.path.join(install_dir, "install-config.yaml"), "w") as fd:
            fd.write(yaml.dump(cluster_install_config))

    return clusters


def get_pull_secret_data(pull_secret_file):
    with open(pull_secret_file) as fd:
        return json.load(fd)


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
    For uninstall this will be used to uninstall the cluster.
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
    'name=cluster1;base_domain=aws.domain.com;platform=aws;region=us-east-2;version=4.14.0-ec.2'
Required parameters:
    name: Cluster name.
    base_domain: Base domain for the cluster.
    platform: Cloud platform to install the cluster on. (Currently only AWS supported).
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
    install,
    uninstall,
    pull_secret_file,
    parallel,
    cluster,
    clusters_install_data_directory,
):
    """
    Install/Uninstall Openshift cluster/s
    """
    set_and_verify_aws_credentials()
    if not (install or uninstall):
        raise ValueError("One of install/uninstall must be specified")

    clusters = generate_cluster_dir_path(
        clusters=cluster, base_directory=clusters_install_data_directory
    )

    clusters = download_openshift_install_binary(
        clusters=clusters, pull_secret_file=pull_secret_file
    )

    if install:
        clusters = create_install_config_file(
            clusters=cluster, pull_secret_file=pull_secret_file
        )

    processes = []
    action_str = "install" if install else "uninstall"
    action_func = install_openshift if install else uninstall_openshift

    for _cluster in clusters:
        kwargs = {"cluster_data": _cluster}
        if parallel:
            proc = multiprocessing.Process(
                name=f"{_cluster['name']}---{action_str}",
                target=action_func,
                kwargs=kwargs,
            )
            processes.append(proc)
            proc.start()

        else:
            action_func(**kwargs)

    if processes:
        verify_processes_passed(processes=processes, action=action_str)


if __name__ == "__main__":
    main()
