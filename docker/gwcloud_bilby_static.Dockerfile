FROM nginx:latest

# Install needed packages
RUN apt-get update
RUN apt-get install -y curl git python3 python3-virtualenv rsync gcc python3-dev

# Copy the bilby source code in to the container
COPY src /src

# Pull down and set up the bilby repo
RUN cd /tmp && git clone https://github.com/gravitationalwavedc/gwcloud_bilby.git
WORKDIR /tmp/gwcloud_bilby/src
RUN virtualenv -p python3 venv
RUN venv/bin/pip install -r requirements.txt
RUN mkdir -p logs
# Build the graphql schema from the bilby repo
RUN venv/bin/python development-manage.py graphql_schema

# Copy the bilby source in to the container
WORKDIR /

# Copy the generate bilby schema
RUN mkdir -p /gwcloud_bilby/src/react/data/
RUN mv /tmp/gwcloud_bilby/src/react/data/schema.json /src/react/data/

# Don't need the bilby project now
RUN rm -Rf /tmp/gwcloud_bilby

# Build webpack bundle
RUN mkdir /src/static
RUN curl https://raw.githubusercontent.com/creationix/nvm/v0.34.0/install.sh | bash
RUN . ~/.nvm/nvm.sh && cd /src/react/ && nvm install && nvm use && npm install npm@8.5.5 && npm install && npm run relay && npm run build

# Copy the javascript bundle
RUN rsync -arv /src/static/ /static/

# Don't need any of the javascipt code now
RUN rm -Rf /src
RUN rm -Rf ~/.nvm/

RUN apt-get remove -y --purge python3 python-virtualenv rsync
RUN apt-get autoremove --purge -y

RUN rm -Rf /gwcloud_bilby

ADD ./nginx/static.conf /etc/nginx/conf.d/nginx.conf

EXPOSE 8000
