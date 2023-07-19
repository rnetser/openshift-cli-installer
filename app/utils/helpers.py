import os
import shutil

import shortuuid
from clouds.aws.session_clients import s3_client
from ocm_python_wrapper.ocm_client import OCMPythonClient


def remove_terraform_folder_from_install_dir(install_dir):
    """
    .terraform folder created when call terraform.init() and it's take more space.
    """
    folders_to_remove = []
    for root, dirs, files in os.walk(install_dir):
        for _dir in dirs:
            if _dir == ".terraform":
                folders_to_remove.append(os.path.join(root, _dir))

    for folder in folders_to_remove:
        shutil.rmtree(folder)


def get_ocm_client(ocm_token, ocm_env):
    return OCMPythonClient(
        token=ocm_token,
        endpoint="https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token",
        api_host=ocm_env,
        discard_unknown_keys=True,
    ).client


def zip_and_upload_to_s3(install_dir, s3_bucket_name, s3_bucket_path, base_name=None):
    remove_terraform_folder_from_install_dir(install_dir=install_dir)

    zip_file = shutil.make_archive(
        base_name=base_name or f"{install_dir}-{shortuuid.uuid()}",
        format="zip",
        root_dir=install_dir,
    )
    s3_client().upload_file(
        Filename=zip_file,
        Bucket=s3_bucket_name,
        Key=os.path.join(s3_bucket_path or "", os.path.split(zip_file)[-1]),
    )

    return base_name
