import re

import click
import semver

from openshift_cli_installer.utils.const import AWS_STR


def set_clusters_versions(clusters, all_versions, base_available_versions=None):
    all_available_versions = {}
    for _cluster_data in clusters:
        all_available_versions.update(
            filter_versions(
                version=_cluster_data["version"],
                stream=_cluster_data.get("stream", "stable"),
                all_versions=all_versions,
                platform=_cluster_data["platform"],
            )
        )

    for cluster_data in clusters:
        cluster_version = cluster_data["version"]
        stream = cluster_data.get("stream", "stable")
        platform = cluster_data["platform"]
        version_key = get_split_version(version=cluster_version)
        all_stream_versions = all_available_versions[version_key][stream]
        err_msg = (
            f"Cluster version {cluster_version} not found in {all_stream_versions}"
        )
        if len(cluster_version.split(".")) == 3:
            for _ver in all_stream_versions["versions"]:
                if cluster_version in _ver:
                    cluster_data["version"] = _ver
                    break
            else:
                click.secho(f"{err_msg}", fg="red")
                raise click.Abort()
        else:
            try:
                cluster_data["version"] = all_stream_versions["latest"]
            except KeyError:
                click.secho(f"{err_msg}", fg="red")
                raise click.Abort()

        if platform == AWS_STR:
            version_url = [
                url
                for url, versions in base_available_versions.items()
                if cluster_data["version"] in versions
            ]
            if version_url:
                cluster_data["version_url"] = version_url[0]
            else:
                click.secho(
                    f"Cluster version url not found for {cluster_version} in {base_available_versions.keys()}",
                    fg="red",
                )
                raise click.Abort()

        click.echo(f"Cluster version set to {cluster_data['version']}")

    return clusters


def filter_versions(version, stream, all_versions, platform):
    versions_dict = {}
    reg_stream = ""
    version_key = get_split_version(version=version)
    x86_64_str = "-x86_64"

    versions_dict[version_key] = {}
    versions_dict[version_key][stream] = {"versions": set(), "latest": ""}
    if platform == AWS_STR:
        reg_stream = stream
        if stream == "stable":
            reg_stream = "x86_64"

        elif stream != "nightly":
            reg_stream = rf"{stream}.\d+{x86_64_str}"

    match = re.findall(
        rf"(?P<stream>{re.escape(version)}(.\d+)?(-)?(\d+.)?{reg_stream}.*)",
        "\n".join(all_versions),
    )
    if match:
        versions_dict[version_key][stream]["versions"] = set(
            [_match[0] for _match in match]
        )

    all_semver_versions = set()
    for available_version in versions_dict[version_key][stream]["versions"]:
        stripped = False
        if x86_64_str in available_version:
            stripped = True
            available_version = available_version.replace(x86_64_str, "")
        try:
            all_semver_versions.add((semver.Version.parse(available_version), stripped))
        except ValueError:
            continue

    if not all_semver_versions:
        click.secho(
            f"Cluster version {version} for stream {stream} not found", fg="red"
        )
        raise click.Abort()

    max_version = max([str(ver[0]) for ver in all_semver_versions])
    add_x86_64 = [ver[1] for ver in all_semver_versions if str(ver[0]) == max_version][
        0
    ]
    versions_dict[version_key][stream][
        "latest"
    ] = f"{max_version}{x86_64_str if add_x86_64 else ''}"

    return versions_dict


def get_split_version(version):
    split_version = version.split(".")
    if len(split_version) > 2:
        version = ".".join(split_version[:-1])

    return version
