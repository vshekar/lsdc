import os, sys
from daq_utils import getBlConfig, beamline
import logging

logger = logging.getLogger()


def perform_runtime_checks():
    # This function ideally should be called ever n seconds when the GUI is running
    # Hopefully this is a temporary fix which will be replaced with a more robust solution

    if os.getcwd() != getBlConfig("basePath", beamline):
        print(
            "Error: Server and GUI are running in separate directories. Please restart GUI in the correct location"
        )
        logger.error(
            "Server and GUI are running in separate directories. Please restart GUI in the correct location"
        )
        sys.exit(0)
