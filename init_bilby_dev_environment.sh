export NVM_DIR="$([ -z "${XDG_CONFIG_HOME-}" ] && printf %s "${HOME}/.nvm" || printf %s "${XDG_CONFIG_HOME}/nvm")"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" # This loads nvm

echo Set up npm for the bilby module
cd ./src/react
nvm install $(cat .nvmrc)
nvm use $(cat .nvmrc)
npm install

echo Set up python virtual env for bilby module
cd ..
virtualenv -p python3.8 venv

venv/bin/pip install -r requirements.txt

venv/bin/python development-manage.py migrate

echo Creating auth superuser \(CTRL+C if you\'ve already created a superuser\)
venv/bin/python development-manage.py createsuperuser

