import json
import os
import re
import shlex

import click
import semantic_version
import yaml
from jinja2 import DebugUndefined, Environment, FileSystemLoader, meta
from ocp_utilities.utils import run_command

from openshift_cli_installer.utils.const import CREATE_STR, DESTROY_STR
from openshift_cli_installer.utils.helpers import (
    bucket_object_name,
    cluster_shortuuid,
    dump_cluster_data_to_file,
    zip_and_upload_to_s3,
)

# TODO: enable spot
"""
function inject_spot_instance_config() {
  local dir=${1}

  if [ ! -f /tmp/yq ]; then
    curl -L https://github.com/mikefarah/yq/releases/download/3.3.0/yq_linux_amd64 -o /tmp/yq && chmod +x /tmp/yq
  fi

  PATCH="${SHARED_DIR}/machinesets-spot-instances.yaml.patch"
  cat > "${PATCH}" << EOF
spec:
  template:
    spec:
      providerSpec:
        value:
          spotMarketOptions: {}
EOF

  for MACHINESET in $dir/openshift/99_openshift-cluster-api_worker-machineset-*.yaml; do
    /tmp/yq m -x -i "${MACHINESET}" "${PATCH}"
    echo "Patched spotMarketOptions into ${MACHINESET}"
  done

  echo "Enabled AWS Spot instances for worker nodes"
}
"""


def prepare_pull_secret(clusters, pull_secret):
    for cluster in clusters:
        pull_secret_file = os.path.join(cluster["auth-dir"], "pull-secret.json")
        with open(pull_secret_file, "w") as fd:
            fd.write(json.dumps(pull_secret))

        cluster["registry_config"] = pull_secret
        cluster["pull-secret-file"] = pull_secret_file


def create_install_config_file(clusters, registry_config_file, ssh_key_file):
    pull_secret = json.dumps(
        get_pull_secret_data(registry_config_file=registry_config_file)
    )
    for _cluster in clusters:
        install_dir = _cluster["install-dir"]
        _cluster["ssh_key"] = get_local_ssh_key(ssh_key_file=ssh_key_file)
        _cluster["pull_secret"] = pull_secret
        cluster_install_config = get_install_config_j2_template(cluster_dict=_cluster)

        with open(os.path.join(install_dir, "install-config.yaml"), "w") as fd:
            fd.write(yaml.dump(cluster_install_config))

    return clusters


def get_pull_secret_data(registry_config_file):
    with open(registry_config_file) as fd:
        return json.load(fd)


def get_local_ssh_key(ssh_key_file):
    with open(ssh_key_file) as fd:
        return fd.read().strip()


def get_install_config_j2_template(cluster_dict):
    template_file = "install-config-template.j2"
    env = Environment(
        loader=FileSystemLoader("openshift_cli_installer/manifests/"),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=DebugUndefined,
    )

    template = env.get_template(name=template_file)
    rendered = template.render(cluster_dict)
    undefined_variables = meta.find_undeclared_variables(env.parse(rendered))
    if undefined_variables:
        click.secho(
            f"The following variables are undefined: {undefined_variables}", fg="red"
        )
        raise click.Abort()

    return yaml.safe_load(rendered)


def download_openshift_install_binary(clusters, registry_config_file):
    versions = set()
    openshift_install_str = "openshift-install"

    for cluster in clusters:
        # TODO: get install url
        versions.add(cluster["version"])

    for version in versions:
        binary_dir = os.path.join("/tmp", version)
        clusters = [_cluster for _cluster in clusters if _cluster["version"] == version]
        for cluster in clusters:
            cluster["openshift-install-binary"] = os.path.join(
                binary_dir, openshift_install_str
            )

        rc, _, err = run_command(
            command=shlex.split(
                "oc adm release extract "
                f"quay.io/openshift-release-dev/ocp-release:{version}-x86_64 "
                f"--command={openshift_install_str} --to={binary_dir} --registry-config={registry_config_file}"
            ),
            check=False,
        )
        if not rc:
            click.secho(
                f"Failed to get {openshift_install_str} for version {version}, error: {err}",
                fg="red",
            )
            raise click.Abort()

    return clusters


def create_or_destroy_aws_ipi_cluster(
    cluster_data, action, s3_bucket_name=None, s3_bucket_path=None, cleanup=False
):
    install_dir = cluster_data["install-dir"]
    binary_path = cluster_data["openshift-install-binary"]
    res, out, err = run_command(
        command=shlex.split(f"{binary_path} {action} cluster --dir {install_dir}"),
        capture_output=False,
        check=False,
    )

    if action == CREATE_STR:
        _shortuuid = cluster_shortuuid()
        cluster_data["s3_object_name"] = bucket_object_name(
            cluster_data=cluster_data,
            _shortuuid=_shortuuid,
            s3_bucket_path=s3_bucket_path,
        )
        dump_cluster_data_to_file(cluster_data=cluster_data)

        if s3_bucket_name:
            zip_and_upload_to_s3(
                install_dir=install_dir,
                s3_bucket_name=s3_bucket_name,
                s3_bucket_path=s3_bucket_path,
                uuid=_shortuuid,
            )

    if not res and not cleanup:
        click.secho(
            f"Failed to run cluster {action}\n\tERR: {err}\n\tOUT: {out}.", fg="red"
        )
        if action == CREATE_STR:
            click.echo("Cleaning leftovers.")
            create_or_destroy_aws_ipi_cluster(
                cluster_data=cluster_data, action=DESTROY_STR, cleanup=True
            )

    if not res:
        raise click.Abort()


def get_aws_versions(docker_config_json_dir_path):
    # If running on openshift-ci we need to set `DOCKER_CONFIG`
    if os.environ.get("OPENSHIFT_CI") == "true":
        click.echo("Running in openshift ci")
        os.environ["DOCKER_CONFIG"] = docker_config_json_dir_path

    versions_dict = {}
    for source_repo in [
        "quay.io/openshift-release-dev/ocp-release",
        "registry.ci.openshift.org/ocp/release",
    ]:
        versions_dict[source_repo] = run_command(
            command=shlex.split(f"regctl tag ls {source_repo}"),
            check=False,
        )[1].splitlines()

    return versions_dict


def update_aws_clusters_versions(clusters, docker_config_json_dir_path):
    base_available_versions = get_aws_versions(
        docker_config_json_dir_path=docker_config_json_dir_path
    )
    available_versions = []
    orig_clusters_versions = [cluster_data["version"] for cluster_data in clusters]

    # Extract only available versions which are relevant to the requested clusters versions
    all_versions = []
    # Currently only using X86 installation
    architectures = ["-s390x", "-aarch64", "-ppc64le", "-multi"]
    for versions in base_available_versions.values():
        all_versions.extend(versions)

    for version in all_versions:
        if re.match(rf".*({'|'.join(architectures)})", version):
            continue
        if re.match(rf"({'|'.join(orig_clusters_versions)}(.\d+)?)", version):
            available_versions.append(version)

    if not available_versions:
        click.secho(
            f"Clusters versions {orig_clusters_versions} are not available in {base_available_versions}",
            fg="red",
        )
        raise click.Abort()

    for cluster_data in clusters:
        target_version = get_aws_cluster_version(
            cluster_version=cluster_data["version"],
            available_versions=available_versions,
            stream=cluster_data.get("stream", "stable"),
        )
        cluster_data["version"] = target_version
        cluster_data["version_url"] = [
            url
            for url, versions in base_available_versions.items()
            if target_version in versions
        ][0]

    return clusters


def get_aws_cluster_version(cluster_version, available_versions, stream):
    # Example: 4.12.0-0.nightly-multi-2022-08-24-183128
    nightly_ci_pattern = re.compile(
        rf"(?P<version>{cluster_version}(.\d+)?)(?P<variant>-\d+.({stream}).*)"
    )

    # Examples: 4.12, 4.13.4
    stable_pattern = re.compile(rf"(?P<version>{cluster_version}(.\d+)?).*")
    versions_set = set()

    for version in available_versions:
        version_match = (
            nightly_ci_pattern.match(version)
            if stream in ["nightly", "ci"]
            else stable_pattern.match(version)
        )
        if version_match:
            target_version = "".join(
                val for val in version_match.groupdict().values() if val is not None
            ).replace("-x86_64", "")

            versions_set.add(target_version)

    if not versions_set:
        click.secho(
            f"Version {cluster_version} is not listed in available versions {available_versions}",
            fg="red",
        )
        raise click.Abort()

    target_version = str(max([semantic_version.Version(ver) for ver in versions_set]))
    click.echo(f"Cluster version set to {target_version}")

    return target_version
