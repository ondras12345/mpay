# mpay
Mpay is a self-hosted system that keeps track of financial transactions in a
home environment.
One or more clients (command-line only for now) connect to a central database.

The system assumes all users trust each other. No authentication / permission
system is implemented besides what the database management system itself can
do. At most, you could configure the database to only allow a certain user
to insert new transactions and disallow deletion or updating of existing ones
(and thus, prevent them from rewriting history), but that still won't prevent
them from stealing money from another user. This system does not try to
prevent that.

On the contrary, mpay actually makes it easy to pay someone a negative amount
of money. I find this quite useful in a home setting. For example, if I
pay the cash-on-delivery for a package that is addressed to my brother, I
want to be able to just log the transaction in mpay without his interaction.


## Features
- Command-line available for GNU/Linux and Windows (and probably
  other UNIX operating systems like mac, but I'm not using that).
- Transactions can easily be created by scripts (and the script's name can be
  logged, see `--agent`)
- [RRULE](https://dateutil.readthedocs.io/en/stable/rrule.html)-based standing
  orders can be used to create transactions periodically.
- The CLI is easy to interact with programmatically, offering things like JSON
  output format.
- The python package can be imported and used directly in more complex
  scripts.
- A rudimentary GUI can be used to view the transaction history
  (see `--format gui`).


### Demo
In this terminal session, we will create an sqlite database and populate it
with example data to show what's possible.
```console
$ ed demo.yaml
demo.yaml: No such file or directory
a
user: johndoe
db_url: "sqlite:///demo.db"
.
w
42
q

$ mpay -c demo.yaml admin init

$ mpay -c demo.yaml user create johndoe

$ mpay -c demo.yaml user create bob

$ mpay -c demo.yaml user create alice

$ mpay -c demo.yaml user list
 id    name  balance
  1 johndoe      0.0
  2     bob      0.0
  3   alice      0.0

$ mpay -c demo.yaml --format json user list
[
  {
    "id":1,
    "name":"johndoe",
    "balance":0.0
  },
  {
    "id":2,
    "name":"bob",
    "balance":0.0
  },
  {
    "id":3,
    "name":"alice",
    "balance":0.0
  }
]

$ mpay -c demo.yaml pay --to bob --amount 123.4 \
  --note "first payment from johndoe to bob"
created transaction with id=1

$ mpay -c demo.yaml pay --to alice --amount -100 \
  --note "let's steal from alice"
created transaction with id=2

$ mpay -c demo.yaml user list
 id    name  balance
  1 johndoe    -23.4
  2     bob    123.4
  3   alice   -100.0


$ date -I
2024-11-08

$ mpay -c demo.yaml order create --to alice --amount 1.0 \
  --rrule "DTSTART:2024-11-04 RRULE:FREQ=DAILY;COUNT=2" \
  --note "recurring daily payment from johndoe to alice with expiry after 2 occurences" \
  order1

$ mpay -c demo.yaml order list
 id   name user_from user_to  amount                                                                         note                                        rrule_str dt_next_utc             dt_created_utc
  1 order1   johndoe   alice     1.0 recurring daily payment from johndoe to alice with expiry after 2 occurences DTSTART:20241104T000000 RRULE:FREQ=DAILY;COUNT=2  2024-11-04 2024-11-08 06:09:25.100187

$ mpay -c demo.yaml --format json order list
[
  {
    "id":1,
    "name":"order1",
    "user_from":"johndoe",
    "user_to":"alice",
    "amount":1.0,
    "note":"recurring daily payment from johndoe to alice with expiry after 2 occurences",
    "rrule_str":"DTSTART:20241104T000000\nRRULE:FREQ=DAILY;COUNT=2",
    "dt_next_utc":1730678400000,
    "dt_created_utc":1731046165100
  }
]

$ mpay -c demo.yaml admin cron  # execute standing orders

$ mpay -c demo.yaml history
 id    from      to  amount                              note orig. currency orig. amount agent  order tags                    due_utc                created_utc created by
  3 johndoe   alice     1.0                              <NA>           <NA>         <NA>  <NA> order1 <NA> 2024-11-04 00:00:00.000000 2024-11-08 06:10:08.733953    johndoe
  4 johndoe   alice     1.0                              <NA>           <NA>         <NA>  <NA> order1 <NA> 2024-11-05 00:00:00.000000 2024-11-08 06:10:08.733958    johndoe
  1 johndoe     bob   123.4 first payment from johndoe to bob           <NA>         <NA>  <NA>   <NA> <NA> 2024-11-08 06:03:27.376332 2024-11-08 06:03:27.412567    johndoe
  2   alice johndoe   100.0            let's steal from alice           <NA>         <NA>  <NA>   <NA> <NA> 2024-11-08 06:04:05.596912 2024-11-08 06:04:05.632928    johndoe

$ mpay -c demo.yaml -f gui history
# see screenshot below

$ # each user only sees transactions involving them
$ mpay -c demo.yaml --override-user bob -f json history
WARNING:mpay.cli:override user: bob
[
  {
    "id":1,
    "from":"johndoe",
    "to":"bob",
    "amount":123.4,
    "note":"first payment from johndoe to bob",
    "orig. currency":null,
    "orig. amount":null,
    "agent":null,
    "order":null,
    "tags":null,
    "due_utc":1731045807376,
    "created_utc":1731045807412,
    "created by":"johndoe"
  }
]
```
![A GUI window showing transaction history](doc/demo-history.png)

To see all available commands and options, run `mpay --help`.


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

Create the database tables (or upgrade to a newer database schema - always
make a backup of the database before doing that):
```
mpay admin init
```

To execute standing orders, it is recommended to set up your cron to run the
following command periodically:
```
mpay admin cron
```

You can also use cron to run consistency checks (although those shouldn't be
necessary if you don't mess with the database directly - don't do things
like `PRAGMA foreign_keys=OFF` or `UPDATE users SET balance ...`).
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


### Database schema revisions
Create a new revision:
```sh
rm schema_test.db
alembic -c mpay/alembic.ini upgrade head
alembic -c mpay/alembic.ini revision --autogenerate -m "create example table"
```

To actually apply the revision to a production database,
run `mpay admin init`.

The database schema as of alembic revision `931cbe1524ae` is shown below
(exported from phpmyadmin):
![database schema](doc/mpay_schema_931cbe1524ae.svg)
