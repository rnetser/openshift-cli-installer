from ocm_python_wrapper.ocm_client import OCMPythonClient


class RunInstallUninstallCommandError(Exception):
    def __init__(self, action, out, err):
        self.action = action
        self.out = out
        self.err = err

    def __str__(self):
        return f"Failed to run cluster {self.action}\nERR: {self.err}\nOUT: {self.out}"


def get_ocm_client(ocm_token, ocm_env):
    return OCMPythonClient(
        token=ocm_token,
        endpoint="https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token",
        api_host=ocm_env,
        discard_unknown_keys=True,
    ).client
