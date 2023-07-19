import os
import shutil
from functools import wraps
from time import sleep

import shortuuid
from clouds.aws.session_clients import s3_client
from ocm_python_wrapper.ocm_client import OCMPythonClient


# TODO: Move to own repository.
def ignore_exceptions(logger=None, retry=None):
    def wrapper(func):
        @wraps(func)
        def inner(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as ex:
                if retry:
                    for _ in range(0, retry):
                        try:
                            return func(*args, **kwargs)
                        except Exception:
                            sleep(1)

                if logger:
                    logger.info(ex)
                return None

        return inner

    return wrapper


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


@ignore_exceptions()
def zip_and_upload_to_s3(install_dir, s3_bucket_name, s3_bucket_path, base_name=None):
    remove_terraform_folder_from_install_dir(install_dir=install_dir)

    _base_name = base_name or f"{install_dir}-{shortuuid.uuid()}"
    zip_file = shutil.make_archive(
        base_name=_base_name,
        format="zip",
        root_dir=install_dir,
    )
    s3_client().upload_file(
        Filename=zip_file,
        Bucket=s3_bucket_name,
        Key=os.path.join(s3_bucket_path or "", os.path.split(zip_file)[-1]),
    )

    return _base_name
