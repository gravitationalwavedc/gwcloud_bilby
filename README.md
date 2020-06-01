# GW Cloud - Bilby module
GW Cloud module template



Creating a new module:-

* Clone the repo and rename it to your new module name
* In the `react` directory:
  * Change the `name` field in `package.json`
  * Change the webpack `devServer` port in `webpack.config.js`
* In the root Django project:
  * Rename the root project `gw_template` to something meaningful.
  * Rename the real Django app `template` to your module name.
  * Update the `DJANGO_SETTINGS_MODULE` in `development-manage.py` to match your root project name.
  * Update `TemplateApp` in your project module `app.py`
  * Update the `INSTALLED_APPS` to match the new project module name.
  * Update `ROOT_URLCONF` and `WSGI_APPLICATION` in the root project`base.py`
  * Update the `GRAPHENE -> SCHEMA` setting in the root project `base.py`
  * ???
