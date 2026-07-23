Do not use a python venv with this bundle. Instead, create a
new micromamba environment in a directory called `venv` in this
bundle directory. Use the `conda-environment.yml` file.

### Install micromamba (if not already installed)

```bash
"${SHELL}" <(curl -L micro.mamba.pm)
```

### Create the environment

```bash
micromamba env create -f conda-environment.yml -p ./venv
```

### Save the environment

```bash
micromamba env export > conda-environment.yml
```

### Update the environment (exact match to `conda-environment.yml`)

```bash
micromamba env update --file conda-environment.yml --prune -p venv
```

### Key packages

```
python-ldas-tools-al
python-ldas-tools-framecpp
python-nds2-client
pip
bilby-pipe
coverage
htcondor
testfixtures
responses
unittest-xml-reporting
```

### Running tests

```bash
source venv/bin/activate
pytest tests/
```

### Ruff Lint

```bash
# Check for auto-fixable issues (CI check)
micromamba run -p venv --root-prefix ~/.local/share/mamba ruff check --select ALL --fix --exit-non-zero-on-fix --ignore PT009 --ignore PT027 .

# Auto-fix
micromamba run -p venv --root-prefix ~/.local/share/mamba ruff check --select ALL --fix --ignore PT009 --ignore PT027 .
```

### Pip packages

```
None yet
```