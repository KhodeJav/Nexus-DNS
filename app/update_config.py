"""Update settings - the ONLY file you edit to connect the updater to your GitHub repository.

While REPO_OWNER / REPO_NAME are still "Null_Link" the update check is switched off and the app starts normally.
"""
REPO_OWNER = "Null_Link"            # GitHub user / organisation that owns the repository
REPO_NAME = "Null_Link"             # repository name

# Release asset that is downloaded and run (the installer attached to the GitHub Release, e.g. MyApp_Setup.exe).
INSTALLER_ASSET = "MyApp_Setup.exe"
# Used only when the release has no usable asset (direct link to the installer). Leave "Null_Link" until you have one.
FALLBACK_DOWNLOAD_URL = "Null_Link"

# Command-line switches for a silent install (these are the Inno Setup ones; change them for another installer type).
INSTALLER_ARGS = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS"

CHECK_TIMEOUT = 5.0                 # seconds for the version check
STARTUP_WAIT_MS = 3500              # how long start-up waits for the check before opening the app
RECHECK_HOURS = 6                   # the running app asks again this often
