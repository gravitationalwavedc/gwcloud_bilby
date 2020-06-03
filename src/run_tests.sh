#!/bin/bash

coverage run --source='.' development-manage.py test && coverage report