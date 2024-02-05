import os


def main():
    clusters = ""
    cmd = "poetry run python openshift_cli_installer/cli.py"
    os_env = os.environ
    cmd += f" --action={os_env['ACTION']}"
    cmd += f" --clusters-install-data-directory={os_env['CLUSTERS_INSTALL_DATA_DIRECTORY']}"
    if cluster_yaml_config_file := os_env.get("CLUSTERS_YAML_CONFIG_FILE"):
        cmd += f" --clusters-yaml-config-file={cluster_yaml_config_file}"
    if os_env.get("PARALLEL") == "true":
        cmd += " --parallel"

    if cluster1 := os_env.get("CLUSTER1"):
        clusters += f" --cluster '{cluster1}'"
    if cluster2 := os_env.get("CLUSTER2"):
        clusters += f" --cluster '{cluster2}'"
    if cluster3 := os_env.get("CLUSTER3"):
        clusters += f" --cluster '{cluster3}'"

    cmd += f" {clusters}"

    if registry_config_file := os_env.get("REGISTRY_CONFIG_FILE"):
        cmd += f" --registry-config-file={registry_config_file}"
    if ocm_token := os_env.get("OCM_TOKEN"):
        cmd += f" --ocm-token={ocm_token}"
    if ssh_key_file := os_env.get("SSH_KEY_FILE"):
        cmd += f" --ssh-key-file={ssh_key_file}"
    if docker_config_file := os_env.get("DOCKER_CONFIG_FILE"):
        cmd += f" --docker-config-file={docker_config_file}"
    if s3_bucket_name := os_env.get("S3_BUCKET_NAME"):
        cmd += f" --s3-bucket-name={s3_bucket_name}"
    if s3_bucket_path := os_env.get("S3_BUCKET_PATH"):
        cmd += f" --s3-bucket-path={s3_bucket_path}"
    if s3_bucket_path_uuid := os_env.get("S3_BUCKET_PATH_UUID"):
        cmd += f" --s3-bucket-path-uuid={s3_bucket_path_uuid}"
    if s3_bucket_object_name := os_env.get("S3_BUCKET_OBJECT_NAME"):
        cmd += f" --s3-bucket-object-name={s3_bucket_object_name}"
    if aws_access_key_id := os_env.get("AWS_ACCESS_KEY_ID"):
        cmd += f" --aws-access-key-id={aws_access_key_id}"
    if aws_secret_access_key := os_env.get("AWS_SECRET_ACCESS_KEY"):
        cmd += f" --aws-secret-access-key={aws_secret_access_key}"
    if aws_account_id := os_env.get("AWS_ACCOUNT_ID"):
        cmd += f" --aws-account-id={aws_account_id}"
    if gcp_service_account_file := os_env.get("GCP_SERVICE_ACCOUNT_FILE"):
        cmd += f" --gcp-service-account-file={gcp_service_account_file}"
    if must_gather_output_dir := os_env.get("MUST_GATHER_OUTPUT_DIR"):
        cmd += f" --must-gather-output-dir={must_gather_output_dir}"
    if os_env.get("DESTROY_CLUSTERS_FROM_S3_BUCKET") == "true":
        cmd += " --destroy-clusters-from-s3-bucket"
    if destroy_clusters_from_s3_bucket_query := os_env.get("DESTROY_CLUSTERS_FROM_S3_BUCKET_QUERY"):
        cmd += f" --destroy-clusters-from-s3-bucket-query={destroy_clusters_from_s3_bucket_query}"
    if os_env.get("DESTROY_CLUSTERS_FROM_INSTALL_DATA_DIRECTORY") == "true":
        cmd += " --destroy-clusters-from-install-data-directory"
    if os_env.get("DESTROY_CLUSTERS_FROM_INSTALL_DATA_DIRECTORY_USING_S3_BUCKET") == "true":
        cmd += " --destroy-clusters-from-install-data-directory-using-s3-bucket"

    print(cmd)


if __name__ == "__main__":
    main()
