import base64
import logging
import os
from pathlib import Path
from typing import Optional
import requests

from ibeam.src.handlers.db_handler import DatabaseHandler

_LOGGER = logging.getLogger('ibeam.' + Path(__file__).stem)

SECRETS_SOURCE_ENV = 'env'
SECRETS_SOURCE_FS = 'fs'
SECRETS_SOURCE_GCP_SECRETS = 'gcp_secrets_manager'

"""If IBEAM_SECRETS_SOURCE is set to
SECRETS_SOURCE_ENV, or if it is not set, then
environment values will be assumed to hold the
secret values directly.

If IBEAM_SECRETS_SOURCE is set to SECRETS_SOURCE_FS
then the environment values are assumed to be file
paths to read for the secret value.

If IBEAM_SECRETS_SOURCE is set to SECRETS_SOURCE_GCP_SECRETS 
then the environment values are assumed to be Google Cloud 
Platform secrets in form of:

[SECRET_NAME]/versions/[SECRET_VERSION] 

In this case IBEAM_GCP_BASE_URL must also be provided in form of:

https://secretmanager.googleapis.com/v1/projects/[PROJECT_ID]/secrets
"""

class SecretsHandler():
    ...
    def __init__(self,
                 secrets_source: str,
                 gcp_base_url: Optional[str] = None,
                 db_host: Optional[str] = None,
                 db_user: Optional[str] = None,
                 db_password: Optional[str] = None,
                 db_name: Optional[str] = None,
                 machine_name: Optional[str] = None,
                 paper_account: Optional[str] = None,
                 paper_password: Optional[str] = None,
                 ):
        self.secrets_source = secrets_source
        self.gcp_base_url = gcp_base_url

        """Character encoding for secret files"""
        self.encoding = os.environ.get(
            'IBEAM_ENCODING', default='UTF-8')

        # Database configuration
        self.db_handler = DatabaseHandler(
            db_host=db_host,
            db_user=db_user,
            db_password=db_password,
            db_name=db_name,
            machine_name=machine_name
        )
        self.paper_account = paper_account
        self.paper_password = paper_password
        self._use_paper_from_db = None
        self._db_check_done = False

    def secret_value(self, encoding, name: str,
                     lstrip=None, rstrip='\r\n') -> Optional[str]:
        """
        secret_value reads secrets from os.environ or from
        the filesystem.

        Given a name, such as 'IBEAM_ACCOUNT', it will
        examine os.environ for a value associated with that
        name.

        If no value has been set, None is returned.
        Otherwise the self.secrets_source will be evaluated
        to determine how to handle the value.

        If self.secrets_source has been set to
        SECRETS_SOURCE_ENV the os.environ value will be
        returned as the secret value.

        If self.secrets_source has been set to
        SECRETS_SOURCE_FS then the os.environ value is
        treated as a filesystem path.  The file will be read
        as text and its contents returned as the secret
        value.

        Parameters:
          name:
            The identifier for the value, e.g.,
            'IBEAM_ACCOUNT', 'IBEAM_PASSWORD', or
            'IBEAM_KEY'.
          lstrip:
            If not None, strip these characters from the
            left of the returned value (default: None).
          rstrip:
            If not None, strip these characters from the
            right of the returned value (default: '\r\n')
        Returns:
          If the name is not defined in os.environ then None
          is returned.

          If self.secrets_source is SECRETS_SOURCE_ENV then
          the os.environ value is returned as the secret
          value.

          If self.secrets_source is SECRETS_SOURCE_FS then
          the os.environ value is treated as file path.  The
          file is read as a text file and its contents
          returned as the secret value.

          If an error is encountered reading the file then
          an error is logged and None is returned.
        """
        # read the environment value for name
        value = os.environ.get(name)
        if value is None:
            # no key for this name, nothing to do
            return None

        if self.secrets_source == SECRETS_SOURCE_ENV:
            # treat environment values as the secrets themselves
            if lstrip is not None:
                value = value.lstrip(lstrip)

            if rstrip is not None:
                value = value.rstrip(rstrip)

            return value
        elif self.secrets_source == SECRETS_SOURCE_FS:
            # treat environment values as filesystem paths to the secrets
            if not os.path.isfile(value):
                _LOGGER.error(
                    f'Unable to read env value for {name}: value is not a file')
                return None

            try:
                with open(value, mode='rt', encoding=encoding) as fh:
                    secret = fh.read()

                    if lstrip is not None:
                        secret = secret.lstrip(lstrip)

                    if rstrip is not None:
                        secret = secret.rstrip(rstrip)

                    return secret
            except IOError:
                _LOGGER.error(
                    f'Unable to read env value for {name} as a file.')
                return None
        elif self.secrets_source == SECRETS_SOURCE_GCP_SECRETS:
            # get authentication token from GCP
            response = requests.get('http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token', headers={'Metadata-Flavor': 'Google'})
            if response.status_code != 200:
                _LOGGER.error(f'Google Metadata request returned status code {response.status_code} :: {response.reason} :: {response.text}')
                return None

            access_token = response.json()['access_token']

            # get secret from GCP
            secret_url = self.gcp_base_url + '/' + value + ':access'
            response2 = requests.get(secret_url, headers={'authorization': f'Bearer {access_token}'})
            if response2.status_code!= 200:
                _LOGGER.error(f'Google Secret Manager request returned status code {response2.status_code} :: {response2.reason} :: {response2.text}')
                return None

            payload_data = response2.json()['payload']['data']
            try:
                base64_data =  base64.b64decode(payload_data)
                decoded_data = base64_data.decode('utf-8')
            except Exception as e:
                _LOGGER.error(f'Unable to decode secret value for {name}: {e}')
                return None
            return decoded_data

        else:
            _LOGGER.error(
                f'Unknown Secrets Source: {self.secrets_source}')
            return None


    def _check_database(self):
        """Check database once to determine if paper account should be used."""
        if not self._db_check_done:
            self._use_paper_from_db = self.db_handler.should_use_paper_account()
            self._db_check_done = True
            _LOGGER.debug(f'Database check result: {self._use_paper_from_db}')

    @property
    def account(self):
        """IBKR account name."""
        self._check_database()

        # If database says use paper account and paper credentials are available
        if self._use_paper_from_db and self.paper_account:
            _LOGGER.info('Using paper account credentials from database configuration')
            # Set environment variable for use_paper_account flag
            os.environ['IBEAM_USE_PAPER_ACCOUNT'] = 'true'
            return self.paper_account

        # Otherwise use regular account
        return self.secret_value(self.encoding, 'IBEAM_ACCOUNT')

    @property
    def password(self):
        """IBKR account password."""
        self._check_database()

        # If database says use paper account and paper credentials are available
        if self._use_paper_from_db and self.paper_password:
            _LOGGER.info('Using paper password from database configuration')
            return self.paper_password

        # Otherwise use regular password
        return self.secret_value(self.encoding, 'IBEAM_PASSWORD')

    @property
    def key(self):
        """Key to the IBKR password."""
        return self.secret_value(self.encoding, 'IBEAM_KEY')