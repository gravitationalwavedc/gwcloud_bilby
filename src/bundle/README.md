Do not use a python venv with this bundle. Instead, create a
new mini/conda environment in a directory called venv in this
bundle directory. Use the `conda-environment.yml` file.

* `conda env create -f conda-environment.yml -p ./venv`

  

To save the environment:-
* `conda env export > conda-environment.yml`


To update the environment exactly as is in the conda-environment.yml:-
* `conda env update --file conda-environment.yml --prune -p venv`

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
```

Pip packages:

```
None yet
```