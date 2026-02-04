import logging
import os
from pathlib import Path
from typing import Optional

_LOGGER = logging.getLogger('ibeam.' + Path(__file__).stem)

class DatabaseHandler:
    """
    Handler for querying the database to determine machine status
    and conditionally set paper account credentials.
    """

    def __init__(self, db_host: Optional[str], db_user: Optional[str],
                 db_password: Optional[str], db_name: Optional[str],
                 machine_name: Optional[str]):
        self.db_host = db_host
        self.db_user = db_user
        self.db_password = db_password
        self.db_name = db_name
        self.machine_name = machine_name
        self._use_paper = None

    def should_use_paper_account(self) -> bool:
        """
        Query the database to check if this machine should use paper account.

        Returns:
            bool: True if paper account should be used, False otherwise.
        """
        # Check if we've already queried the database
        if self._use_paper is not None:
            return self._use_paper

        # DBPASSWORD is intentionally excluded — it is valid for it to be
        # None or empty (e.g. root with no password).  Only the other four
        # are required.
        required = {
            'DBHOST': self.db_host,
            'DBUSER': self.db_user,
            'DBNAME': self.db_name,
            'MACHINE_NAME': self.machine_name,
        }
        missing = [k for k, v in required.items() if v is None]
        if missing:
            _LOGGER.info(f'Skipping database check, missing env vars: {missing}')
            return False

        try:
            import pymysql

            _LOGGER.info(f'Connecting to database {self.db_name} at {self.db_host} to check machine status for {self.machine_name}')

            # Connect to the database
            connection = pymysql.connect(
                host=self.db_host,
                user=self.db_user,
                password=self.db_password or '',
                database=self.db_name,
                cursorclass=pymysql.cursors.DictCursor
            )

            try:
                with connection.cursor() as cursor:
                    # Query the IBEAM table for the machine name
                    sql = "SELECT `value` FROM `IBEAM` WHERE `machine_name` = %s"
                    cursor.execute(sql, (self.machine_name,))
                    result = cursor.fetchone()

                    if result is None:
                        _LOGGER.warning(f'Machine name {self.machine_name} not found in IBEAM table')
                        self._use_paper = False
                        return False

                    # Check if the value is true/1
                    value = result['value']
                    _LOGGER.info(f'Database returned value: {value} for machine {self.machine_name}')

                    # Handle various truthy values
                    if isinstance(value, bool):
                        self._use_paper = value
                    elif isinstance(value, int):
                        self._use_paper = bool(value)
                    elif isinstance(value, str):
                        self._use_paper = value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        self._use_paper = False

                    _LOGGER.info(f'Machine {self.machine_name} should use paper account: {self._use_paper}')
                    return self._use_paper

            finally:
                connection.close()

        except ImportError:
            _LOGGER.error('pymysql module not found. Please install it: pip install pymysql')
            self._use_paper = False
            return False
        except Exception as e:
            _LOGGER.error(f'Error querying database: {e}')
            self._use_paper = False
            return False

    def configure_paper_account_env(self, paper_account: Optional[str],
                                    paper_password: Optional[str]) -> None:
        """
        If database indicates paper account should be used, set environment variables
        to override the regular account credentials.

        Args:
            paper_account: The paper account username
            paper_password: The paper account password
        """
        if not self.should_use_paper_account():
            _LOGGER.info('Live account will be used')
            return

        if not paper_account or not paper_password:
            _LOGGER.warning('Paper account credentials not provided, cannot switch to paper account')
            return

        _LOGGER.info('Configuring paper account credentials')

        # Set IBEAM_USE_PAPER_ACCOUNT to true
        os.environ['IBEAM_USE_PAPER_ACCOUNT'] = 'true'

        # Override IBEAM_ACCOUNT and IBEAM_PASSWORD with paper credentials
        os.environ['IBEAM_ACCOUNT'] = paper_account
        os.environ['IBEAM_PASSWORD'] = paper_password

        _LOGGER.info('Paper account credentials configured successfully')
