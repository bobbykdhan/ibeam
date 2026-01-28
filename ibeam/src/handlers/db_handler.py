import logging
import os
from pathlib import Path
from typing import Optional

_LOGGER = logging.getLogger('ibeam.' + Path(__file__).stem)


class DatabaseHandler:
    """Handler for querying database to check machine status for paper account usage."""

    def __init__(self, db_host: Optional[str], db_user: Optional[str],
                 db_password: Optional[str], db_name: Optional[str],
                 machine_name: Optional[str]):
        self.db_host = db_host
        self.db_user = db_user
        self.db_password = db_password
        self.db_name = db_name
        self.machine_name = machine_name
        self._connection = None

    def _connect(self):
        """Establish connection to the database."""
        if not all([self.db_host, self.db_user, self.db_password, self.db_name]):
            _LOGGER.debug('Database credentials not fully configured, skipping database check.')
            return None

        try:
            import pymysql
            self._connection = pymysql.connect(
                host=self.db_host,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
                cursorclass=pymysql.cursors.DictCursor
            )
            _LOGGER.info(f'Successfully connected to database at {self.db_host}')
            return self._connection
        except ImportError:
            _LOGGER.warning('pymysql not installed. Install with: pip install pymysql')
            return None
        except Exception as e:
            _LOGGER.error(f'Failed to connect to database: {e}')
            return None

    def should_use_paper_account(self) -> Optional[bool]:
        """
        Query the database to check if this machine should use paper account.

        Returns:
            True if paper account should be used
            False if live account should be used
            None if database check is not configured or failed
        """
        if not self.machine_name:
            _LOGGER.debug('Machine name not configured, skipping database check.')
            return None

        connection = self._connect()
        if not connection:
            return None

        try:
            with connection.cursor() as cursor:
                # Query the IBEAM table for the machine name
                sql = "SELECT * FROM IBEAM WHERE machine_name = %s"
                cursor.execute(sql, (self.machine_name,))
                result = cursor.fetchone()

                if result:
                    # Check if the value is true (could be stored as boolean, int, or string)
                    use_paper = result.get('use_paper_account') or result.get('value')

                    # Handle different types: boolean, int (1/0), or string ('true'/'false')
                    if isinstance(use_paper, bool):
                        _LOGGER.info(f'Database check: machine {self.machine_name} should {"" if use_paper else "NOT "}use paper account')
                        return use_paper
                    elif isinstance(use_paper, int):
                        use_paper_bool = bool(use_paper)
                        _LOGGER.info(f'Database check: machine {self.machine_name} should {"" if use_paper_bool else "NOT "}use paper account')
                        return use_paper_bool
                    elif isinstance(use_paper, str):
                        use_paper_bool = use_paper.lower() in ('true', '1', 'yes')
                        _LOGGER.info(f'Database check: machine {self.machine_name} should {"" if use_paper_bool else "NOT "}use paper account')
                        return use_paper_bool
                    else:
                        _LOGGER.warning(f'Unknown value type for use_paper_account: {type(use_paper)}')
                        return None
                else:
                    _LOGGER.info(f'No database entry found for machine {self.machine_name}, using default configuration')
                    return None

        except Exception as e:
            _LOGGER.error(f'Error querying database: {e}')
            return None
        finally:
            connection.close()
