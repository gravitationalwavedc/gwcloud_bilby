FROM python:3.12 as django
ENV PYTHONUNBUFFERED 1

# Update the container and install the required packages
RUN apt-get update
RUN apt-get -y install python3-virtualenv default-libmysqlclient-dev python3-dev build-essential curl

# Copy the source code in to the container
COPY src /src
COPY ./runserver.sh /runserver.sh
RUN chmod +x /runserver.sh

# Create python virtualenv
RUN rm -Rf /src/venv
RUN virtualenv -p python3 /src/venv

# Activate and install the django requirements (mysqlclient requires python3-dev and build-essential)
RUN . /src/venv/bin/activate && pip install -r /src/requirements.txt && pip install mysqlclient && pip install gunicorn && python src/development-manage.py graphql_schema --out /src/schema.json

# Clean up unneeded packages
RUN apt-get remove --purge -y build-essential python3-dev
RUN apt-get autoremove --purge -y

# Don't need any of the javascipt code now
RUN rm -Rf /src/react

# Expose the port and set the run script
EXPOSE 8000

# Set the working directory and start script
WORKDIR /src
CMD [ "/runserver.sh" ]

FROM nginx:latest as static

# Install needed packages
RUN apt-get update
RUN apt-get install -y curl python3.10 python3-pip rsync
RUN apt-get -y upgrade

# Copy the bilby source code in to the container
COPY src /src

# Copy the bilby source in to the container
WORKDIR /

# Copy the generate bilby schema
COPY --from=django /src/schema.json /src/react/data/

# Build webpack bundle
RUN mkdir /src/static
# RUN curl https://raw.githubusercontent.com/creationix/nvm/v0.34.0/install.sh | bash
# RUN . ~/.nvm/nvm.sh && cd /src/react/ && nvm install && nvm use && npm install npm@8.5.5 && npm install && npm run relay && npm run build

RUN curl https://raw.githubusercontent.com/creationix/nvm/master/install.sh | bash
RUN export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" && cd /src/react/ && nvm install && nvm use && npm install --legacy-peer-deps && npm run relay && npm run build

# Copy the javascript bundle
RUN rsync -arv /src/static/ /static/

# Don't need any of the javascipt code now
RUN rm -Rf /src
RUN rm -Rf ~/.nvm/

RUN apt-get remove -y --purge rsync
RUN apt-get autoremove --purge -y

RUN rm -Rf /gwcloud_bilby

ADD ./nginx/static.conf /etc/nginx/conf.d/nginx.conf

EXPOSE 8000

FROM nginx:latest as nginx
ADD ./nginx/nginx.conf /etc/nginx/conf.d/nginx.conf
EXPOSE 8000
