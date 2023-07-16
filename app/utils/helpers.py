class RunInstallUninstallCommandError(Exception):
    def __init__(self, action, out, err):
        self.action = action
        self.out = out
        self.err = err

    def __str__(self):
        return f"Failed to run cluster {self.action}\nERR: {self.err}\nOUT: {self.out}"
