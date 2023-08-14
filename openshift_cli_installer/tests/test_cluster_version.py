import click
import pytest

from openshift_cli_installer.libs.aws_ipi_clusters import update_aws_clusters_versions


@pytest.mark.parametrize(
    "clusters, expected",
    [
        ([{"version": "4.13", "stream": "stable", "platform": "aws"}], "4.13.9-x86_64"),
        (
            [{"version": "4.13", "stream": "nightly", "platform": "aws"}],
            "4.13.0-0.nightly-2023-08-11-101506",
        ),
        (
            [{"version": "4.13", "stream": "ec", "platform": "aws"}],
            "4.13.0-ec.4-x86_64",
        ),
        (
            [{"version": "4.13", "stream": "rc", "platform": "aws"}],
            "4.13.0-rc.8-x86_64",
        ),
        (
            [{"version": "4.13.9", "stream": "stable", "platform": "aws"}],
            "4.13.9-x86_64",
        ),
        ([{"version": "4", "stream": "stable", "platform": "aws"}], "error"),
        ([{"version": "100.5.1", "stream": "stable", "platform": "aws"}], "error"),
        ([{"version": "100.5", "stream": "stable", "platform": "aws"}], "error"),
        ([{"version": "4.13.40", "stream": "stable", "platform": "aws"}], "error"),
    ],
)
def test_aws_cluster_version(clusters, expected):
    try:
        res = update_aws_clusters_versions(clusters=clusters, _test=True)[0]
        assert res["version"] == expected
        assert res["version_url"] == "for/test/"
    except click.Abort:
        if expected == "error":
            return
        else:
            raise
