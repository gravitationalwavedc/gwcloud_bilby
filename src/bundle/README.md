Do not use a python venv with this bundle. Instead, create a
new mini/conda environment in a directory called venv in this
bundle directory. Use the `conda-environment.yml` file.

* `conda env create -f conda-environment.yml -p ./venv`

  

To save the environment:-
* `conda env export > conda-environment.yml`

  


Conda packages:
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
diskcache
aiohttp
aiosignal
async-timeout
frozenlist
lxml
multidict
yarl
```

Pip packages:

```
aiohttp-xmlrpc
```