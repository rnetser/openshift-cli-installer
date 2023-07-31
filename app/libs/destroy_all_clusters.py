import multiprocessing
import os
import re
import shutil
from pathlib import Path

import click
import yaml
from clouds.aws.session_clients import s3_client
from libs.aws_ipi_clusters import create_or_destroy_aws_ipi_cluster
from libs.rosa_clusters import rosa_delete_cluster
from utils.const import AWS_STR


def download_and_extract_s3_file(
    client, bucket, bucket_filepath, target_dir, target_filename, extracted_target_dir
):
    target_file_path = os.path.join(target_dir, target_filename)
    client.download_file(Bucket=bucket, Key=bucket_filepath, Filename=target_file_path)

    shutil.unpack_archive(
        filename=target_file_path,
        extract_dir=os.path.join(extracted_target_dir, target_filename),
        format="zip",
    )


def get_clusters_data_dict(cluster_dirs, extracted_target_dir):
    clusters_dict = {"aws": [], "rosa": [], "hypershift": []}
    for cluster_dir in cluster_dirs:
        try:
            with open(os.path.join(cluster_dir, "cluster_data.yaml")) as fd:
                data = yaml.safe_load(fd.read())
            data["install-dir"] = cluster_dir
            data["bucket_filepath"] = re.match(
                rf".*{extracted_target_dir}/(.*)", cluster_dirs[0]
            ).group(1)
            clusters_dict[data["platform"]].append(data)
        except FileNotFoundError:
            clusters_dict["aws"].append(cluster_dir)

    return clusters_dict


def destroy_all_clusters_from_s3_bucket(s3_bucket_name, s3_bucket_path=None):
    extracted_target_dir, target_dir = prepare_cluster_directories(
        s3_bucket_path=s3_bucket_path
    )

    get_all_files_from_s3_bucket(
        extracted_target_dir=extracted_target_dir,
        s3_bucket_name=s3_bucket_name,
        s3_bucket_path=s3_bucket_path,
        target_dir=target_dir,
    )

    cluster_dirs = get_extracted_clusters_dir_paths(
        extracted_target_dir=extracted_target_dir
    )
    cluster_data_dict = get_clusters_data_dict(
        cluster_dirs=cluster_dirs, extracted_target_dir=extracted_target_dir
    )

    processes = []
    for cluster_type, cluster_data in cluster_data_dict.items():
        if cluster_type == AWS_STR:
            proc = multiprocessing.Process(
                target=create_or_destroy_aws_ipi_cluster,
                kwargs={"cluster_data": cluster_data, "action": "destroy"},
            )
        else:
            proc = multiprocessing.Process(
                target=_destroy_cluster,
                kwargs={"cluster_data": cluster_data, "s3_bucket_name": s3_bucket_name},
            )

        processes.append(proc)
        proc.start()

    for proc in processes:
        proc.join()

    shutil.rmtree(path=target_dir, ignore_errors=True)


def _destroy_cluster(cluster_data, s3_bucket_name):
    try:
        rosa_delete_cluster(cluster_data=cluster_data)
        s3_client().delete_object(
            Bucket=s3_bucket_name, Key=cluster_data["bucket_filepath"]
        )
    except click.exceptions.Abort:
        click.echo(f"Cannot delete cluster {cluster_data['cluster-name']}")
        # TODO: Delete S3 file is a cluster is not found; need to add more exception logic to know when to delete.
        # s3_client().delete_object(Bucket=s3_bucket_name, Key=cluster_data["bucket_filepath"])


def get_extracted_clusters_dir_paths(extracted_target_dir):
    cluster_dirs = []
    for root, dirs, files in os.walk(extracted_target_dir):
        for _dir in dirs:
            if _dir.endswith(".zip"):
                cluster_dirs.append(os.path.join(root, _dir))
    return cluster_dirs


def get_all_files_from_s3_bucket(
    extracted_target_dir, s3_bucket_name, s3_bucket_path, target_dir
):
    client = s3_client()
    kwargs = {"Bucket": s3_bucket_name}
    if s3_bucket_path:
        kwargs["Prefix"] = s3_bucket_path
    clusters_files = client.list_objects(**kwargs)
    processes = []
    for cluster_file in clusters_files["Contents"]:
        name = cluster_file["Key"]
        proc = multiprocessing.Process(
            target=download_and_extract_s3_file,
            kwargs={
                "client": client,
                "bucket": s3_bucket_name,
                "bucket_filepath": name,
                "target_dir": target_dir,
                "target_filename": name,
                "extracted_target_dir": extracted_target_dir,
            },
        )
        processes.append(proc)
        proc.start()
    for proc in processes:
        proc.join()


def prepare_cluster_directories(s3_bucket_path):
    target_dir = "/tmp/destroy-all-clusters-from-s3-bucket"
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    if s3_bucket_path:
        Path(os.path.join(target_dir, s3_bucket_path)).mkdir(
            parents=True, exist_ok=True
        )
    extracted_target_dir = os.path.join(target_dir, "extracted_clusters_files")
    Path(extracted_target_dir).mkdir(parents=True, exist_ok=True)
    return extracted_target_dir, target_dir


def _destroy_all_clusters(
    s3_bucket_name=None, s3_bucket_path=None, clusters_install_data_directory=None
):
    if clusters_install_data_directory:
        pass
        # destroy_all_clusters_from_local_diretroy(clusters_install_data_directory=clusters_install_data_directory)

    if s3_bucket_name:
        destroy_all_clusters_from_s3_bucket(
            s3_bucket_name=s3_bucket_name, s3_bucket_path=s3_bucket_path
        )
