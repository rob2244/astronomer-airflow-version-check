import functools
import logging

from airflow.plugins_manager import AirflowPlugin
from airflow.utils.db import create_session

from .update_checks import UpdateAvailableBlueprint

__version__ = "1.0.1"

log = logging.getLogger(__name__)


class AstronomerVersionCheckPlugin(AirflowPlugin):
    name = "astronomer_version_check"

    flask_blueprints = [UpdateAvailableBlueprint()]

    @staticmethod
    def add_before_call(mod_or_cls, target, pre_fn):
        fn = getattr(mod_or_cls, target)

        @functools.wraps(fn)
        def run_before(*args, **kwargs):
            pre_fn()
            fn(*args, **kwargs)

        setattr(mod_or_cls, target, run_before)

    @classmethod
    def on_load(cls, *args, **kwargs):
        # Hook in to various places in Airflow in a slightly horrible way -- by
        # using functools.wraps and replacing the function.

        import airflow.utils.db
        import airflow.jobs.scheduler_job
        cls.add_before_call(airflow.utils.db, 'upgradedb', cls.create_db_tables)
        cls.add_before_call(airflow.jobs.scheduler_job.SchedulerJob, '_execute_helper', cls.start_update_thread)

    @classmethod
    def start_update_thread(cls):
        from .models import AstronomerVersionCheck
        from .update_checks import CheckThread

        with create_session() as session:
            engine = session.get_bind(mapper=None, clause=None)
            if not engine.has_table(AstronomerVersionCheck.__tablename__):
                log.warning("AstronomerVersionCheck tables are missing (plugin not installed at upgradedb "
                            "time?). No update checks will be performed")
                return

        AstronomerVersionCheck.ensure_singleton()
        CheckThread().start()

    @classmethod
    def create_db_tables(cls):
        from .models import AstronomerAvailableVersion, AstronomerVersionCheck
        with create_session() as session:
            try:
                engine = session.get_bind(mapper=None, clause=None)
                if not engine.has_table(AstronomerVersionCheck.__tablename__):
                    log.info("Creating DB tables for %s", __name__)
                    metadata = AstronomerVersionCheck.metadata
                    metadata.create_all(bind=engine, tables=[
                        metadata.tables[c.__tablename__] for c in [AstronomerVersionCheck, AstronomerAvailableVersion]
                    ])
                    log.info("Created")
            except Exception:
                log.exception("Error creating tables")
                exit(1)
