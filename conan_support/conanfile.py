from conan import ConanFile
from conan.tools.files import copy, save
import os
import pathlib
from rules_support import PluginBranchInfo

def _read(filename):
    return open(os.path.join(os.path.dirname(__file__), filename)).read().strip()

class StagingConan(ConanFile):
    """Class to stage and pack a ManiVaultStudio componen in the CI

    Uses rules_support (github.com/ManiVaultStudio/rulessupport) to derive
    versioninfo based on the branch naming convention
    as described in https://github.com/ManiVaultStudio/core/wiki/Branch-naming-rules
    """

    name = _read("conan_name.txt")
    description = "Perform Mean Shift Clustering in ManiVault"
    topics = ("hdps", "plugin")

    # Options may need to change depending on the packaged library
    settings = {"os": None, "build_type": None, "compiler": None, "arch": None}
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": True, "fPIC": True}

    scm = {
        "type": "git",
        "subfolder": "hdps/MeanShiftClustering",
        "url": "auto",
        "revision": "auto",
    }

    def export(self):
        print("In export")
        # save the original source path to the directory used to build the package
        save(
            pathlib.Path(self.export_folder, "__gitpath.txt"),
            str(pathlib.Path(__file__).parent.resolve()),
        )

    def set_version(self):
        # Assign a version from the branch name
        branch_info = PluginBranchInfo(self.recipe_folder)
        self.version = branch_info.version    

    def package(self):
        copy(self, "*",
             src=os.environ["CONAN_STAGE_DIR"],
             dst=self.package_folder)