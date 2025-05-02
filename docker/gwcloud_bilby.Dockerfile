FROM python:3.12.6 AS base
# Deliberately pinned to 3.12.6 due to a breaking change
# See https://gitlab.com/CAS-eResearch/GWDC/gwcloud_bilby/-/merge_requests/142 to discover the true meaning of suffering
ENV PYTHONUNBUFFERED 1

# Update the container and install the required packages
RUN apt-get update \
  && apt-get install --no-install-recommends -y \
  curl netcat-traditional\
  && apt-get clean \
  && rm -rf /var/lib/apt-lists/* \
  && apt-get autoremove --purge -y


FROM base AS django-builder

RUN apt-get update \
  && apt-get install --no-install-recommends -y \
  python3-virtualenv default-libmysqlclient-dev python3-dev build-essential git pkg-config \
  && apt-get clean \
  && rm -rf /var/lib/apt-lists/* \
  && apt-get autoremove --purge -y


RUN virtualenv -p python3.12 /venv
COPY ./src/requirements.txt /requirements.txt

# Activate and install the django requirements (mysqlclient requires python3-dev and build-essential)
RUN . /venv/bin/activate \
  && pip install -r /requirements.txt \
  && pip install mysqlclient gunicorn

# Copy the source code in to the container
COPY ./src /src

WORKDIR /src

# Generate the graphql schema
RUN . /venv/bin/activate \
  && python development-manage.py graphql_schema


FROM base as django-runner

COPY --from=django-builder /src /src
COPY --from=django-builder /venv /venv

COPY ./runserver.sh /runserver.sh
RUN chmod +x /runserver.sh

# Expose the port and set the run script
EXPOSE 8000

# Set the working directory and start script
WORKDIR /src
CMD [ "/runserver.sh" ]

FROM node:23.6.1 as static-builder

# Copy the bilby source code in to the container
COPY ./src/react /react

# Copy the bilby source in to the container
WORKDIR /react

# Copy the generate bilby schema
COPY --from=django-builder /src/react/data/schema.graphql /react/data/schema.graphql

RUN npm install --legacy-peer-deps \
  && npm run relay \
  && npm run build


FROM nginx:latest as static-runner

COPY --from=static-builder /react/dist /static

COPY ./nginx/nginx.conf /etc/nginx/conf.d/nginx.conf

EXPOSE 8000

