from __future__ import with_statement

from logging.config import fileConfig
import sys, os
from urllib.parse import quote_plus



sys.path.append('/home/barry/PycharmProjects/RedditRepostSleuth')
sys.path.append(r'C:\Users\mcare\PycharmProjects\RedditRepostSleuth')

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Base

from sqlalchemy import engine_from_config, create_engine
from sqlalchemy import pool


from alembic import context

# Load bot config
if not os.getenv('bot_config', None):
    print('No bot config provided, aborting')
    sys.exit()



# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
bot_config = Config(os.getenv('bot_config'))
# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

def get_conn_string():
    return f'mysql+pymysql://{bot_config.db_user}:{quote_plus(bot_config.db_password)}@{bot_config.db_host}/{bot_config.db_name}'


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=get_conn_string(), target_metadata=target_metadata, literal_binds=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(get_conn_string(), echo=False, )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
