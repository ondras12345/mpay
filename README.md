# mpay
TODO description

## Features
TODO


## Installation
It is recommended to install via [`pipx`](https://github.com/pypa/pipx):
```sh
pipx install git+https://github.com/ondras12345/mpay.git
```

Optional: register tab completion
```sh
eval "$(register-python-argcomplete mpay)"
```

### Setup
You need to create a config file in `$XDG_CONFIG_HOME/mpay/config.yaml`
on GNU/Linux, or `%APPDATA%\mpay\config.yaml` on Windows:
```yaml
user: your_username  # optional, will use $USER if omitted
db_url: "sqlite:////home/user/path/to/mpay.db"
```

Alternatively, you can use a MySQL / mariadb database:
```yaml
db_url: "mysql+pymysql://user:password@host/database"
```

If you don't want to store your database credentials in a text config file,
you can also specify a command to retrieve it from a password manager:
```yaml
db_url:
  # secret-tool store --label="mpay_test" mpay-db mpay_test
  command: secret-tool lookup mpay-db mpay_test
```

This project uses SQLAlchemy to access the database, so other RDBMSs might work
too, but I haven't tested them.
It is a good idea to at least run the tests located in `tests/` directory
against your database. You should also `grep` the source codes for `dialect`
and review what RDBMS-specific tweaks there are.

Create the database tables:
```sh
mpay admin init
```

To execute standing orders, it is recommended to set up your cron to run the
following command periodically:
```
mpay admin cron
```

You can also use cron to run consistency checks:
```
# exit status will be non-zero on failure
mpay admin check
```


## Development
Install in a venv:
```
pip3 install --editable '.[dev]'
```

Set up pre-commit:
```
pre-commit install
```
